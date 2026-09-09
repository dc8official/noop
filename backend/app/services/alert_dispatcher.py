from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import logging
import smtplib
import ssl
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx
from sqlalchemy import select, text

from app.database import AsyncSessionLocal, async_engine
from app.models.alert_channel import AlertChannel

ADVISORY_LOCK_ID = 992817
from app.models.alert_delivery_log import AlertDeliveryLog
from app.models.system_setting import AppSetting
from app.services.alert_formatters import (
    build_discord_payload,
    build_email_mime,
    build_polyglot_payload,
    build_slack_payload,
)
from app.services.crypto_service import decrypt_secret
from app.services.driver_manager import driver_manager
from app.services.ssrf_validator import validate_outbound_url

logger = logging.getLogger(__name__)


class AlertDispatcher:
    """
    Enterprise Alert Dispatcher and Suppression Engine.
    Executes in background tasks within the netmon-api process.
    Completely decoupled from the monitoring probe loop.
    """

    def __init__(self) -> None:
        self._running: bool = False
        self._is_leader: bool = False
        self._lock_conn: Any = None
        self._tasks: List[asyncio.Task] = []
        self._queue: asyncio.Queue[Tuple[str, Dict[str, Any]]] = asyncio.Queue(maxsize=1000)

        # Rate limiting and flapping memory caches
        # key: (channel_id_str, endpoint_id_str, severity) -> last_sent_at
        self._rate_limits: Dict[Tuple[str, str, str], datetime] = {}
        # key: endpoint_id_str -> list of transition timestamps
        self._flapping_tracker: Dict[str, List[datetime]] = {}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        # Start queue consumer worker
        self._tasks.append(asyncio.create_task(self._process_queue(), name="alert_dispatcher_queue"))

        # Attempt Leader Election via PostgreSQL Session Advisory Lock
        try:
            if async_engine.dialect.name == "postgresql":
                self._lock_conn = await async_engine.connect()
                res = await self._lock_conn.execute(text(f"SELECT pg_try_advisory_lock({ADVISORY_LOCK_ID})"))
                acquired = bool(res.scalar())
                if not acquired:
                    logger.info("[AlertDispatcher] Running in standby mode (passive worker).")
                    if self._lock_conn:
                        await self._lock_conn.close()
                        self._lock_conn = None
                    self._is_leader = False
                    return
                self._is_leader = True
            else:
                self._is_leader = True
        except Exception as exc:
            logger.warning("AlertDispatcher: advisory lock election failed: %s. Continuing in leader mode.", exc)
            self._is_leader = True

        if self._is_leader:
            self._tasks.append(asyncio.create_task(self._listen_broker("STATE_TRANSITION"), name="alert_broker_state_trans"))
            self._tasks.append(asyncio.create_task(self._listen_broker("RCA_INCIDENT"), name="alert_broker_rca"))
            logger.info("[AlertDispatcher] Active leader election won. Broker listeners started.")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        if self._is_leader and self._lock_conn:
            try:
                await self._lock_conn.execute(text(f"SELECT pg_advisory_unlock({ADVISORY_LOCK_ID})"))
            except Exception as exc:
                logger.warning("AlertDispatcher: failed to release advisory lock: %s", exc)
            finally:
                try:
                    await self._lock_conn.close()
                except Exception:
                    pass
                self._lock_conn = None

        self._is_leader = False
        logger.info("AlertDispatcher engine stopped.")

    async def enqueue_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Enqueue an event for asynchronous dispatching without blocking caller."""
        if not self._running or not self._is_leader:
            return
        try:
            self._queue.put_nowait((event_type, data))
        except asyncio.QueueFull:
            logger.warning("AlertDispatcher: event queue is full. Dropping alert payload.")

    async def _listen_broker(self, channel: str) -> None:
        """Subscribes to Redis / Postgres LISTEN/NOTIFY channels."""
        while self._running:
            try:
                broker = driver_manager.get_event_broker()
                async for event in broker.subscribe(channel):
                    if not self._running:
                        break
                    await self.enqueue_event(channel, event)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("AlertDispatcher: subscription to '%s' failed: %s. Reconnecting in 3s...", channel, exc)
                await asyncio.sleep(3.0)

    def _prune_memory_caches(self, now: datetime) -> None:
        """
        Evicts stale rate-limit and flapping tracker entries to eliminate memory leaks:
        - Rate limits where last_sent < now - 1 hour.
        - Flapping tracker keys where all timestamps < now - 10 minutes or list is empty.
        """
        rl_cutoff = now - timedelta(hours=1)
        expired_rl = [k for k, last_sent in self._rate_limits.items() if last_sent < rl_cutoff]
        for k in expired_rl:
            del self._rate_limits[k]

        flap_cutoff = now - timedelta(minutes=10)
        expired_flaps = []
        for ep_key, timestamps in list(self._flapping_tracker.items()):
            active_ts = [t for t in timestamps if t >= flap_cutoff]
            if not active_ts:
                expired_flaps.append(ep_key)
            else:
                self._flapping_tracker[ep_key] = active_ts

        for ep_key in expired_flaps:
            del self._flapping_tracker[ep_key]

    async def _process_queue(self) -> None:
        while self._running:
            try:
                event_type, data = await self._queue.get()
                now = datetime.now(timezone.utc)
                self._prune_memory_caches(now)
                try:
                    await self._dispatch_event(event_type, data)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("AlertDispatcher queue processing error: %s", exc, exc_info=True)

    async def _is_alerting_enabled(self) -> bool:
        """Checks master alerting toggle from app_settings (defaults to True)."""
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(AppSetting).where(AppSetting.setting_key == "alerting_enabled")
                res = await db.execute(stmt)
                setting = res.scalar_one_or_none()
                if setting is not None:
                    return setting.setting_value.strip().lower() in ("true", "1", "yes")
            return True
        except Exception as err:
            logger.warning("AlertDispatcher: failed to read master toggle: %s. Defaulting to enabled.", err)
            return True

    async def _dispatch_event(self, event_type: str, data: Dict[str, Any]) -> None:
        # 1. Master Toggle Check
        if not await self._is_alerting_enabled():
            logger.debug("AlertDispatcher: Master alerting is DISABLED. Dropping event.")
            return

        endpoint_id = data.get("endpoint_id") or data.get("node_id")
        endpoint_name = data.get("hostname") or data.get("endpoint_name") or "Unknown Endpoint"
        ip_address = data.get("ip_address") or "0.0.0.0"
        new_state = (
            data.get("operational_state")
            or data.get("current_state")
            or data.get("new_state")
            or "UNKNOWN"
        ).upper()

        # Upstream Root-Cause Incident Suppression
        # If an RCA grouping marks this as downstream symptom, suppress alert
        if data.get("is_symptom") is True or data.get("suppressed_by_upstream") is True:
            logger.info("AlertDispatcher: Suppressing alert for %s due to upstream root cause failure.", endpoint_name)
            return

        # Check Flapping
        now = datetime.now(timezone.utc)
        ep_key = str(endpoint_id) if endpoint_id else endpoint_name
        is_flapping = self._check_flapping(ep_key, now)

        # Retrieve active channels from DB
        async with AsyncSessionLocal() as db:
            stmt = select(AlertChannel).where(AlertChannel.is_enabled == True)
            res = await db.execute(stmt)
            channels = res.scalars().all()

            for channel in channels:
                try:
                    await self._evaluate_and_send_channel(
                        db=db,
                        channel=channel,
                        endpoint_id=endpoint_id,
                        endpoint_name=endpoint_name,
                        ip_address=ip_address,
                        event_type=event_type,
                        severity=new_state,
                        timestamp=now,
                        details=data,
                        is_flapping=is_flapping,
                    )
                except Exception as exc:
                    logger.error("AlertDispatcher: Error dispatching to channel '%s': %s", channel.name, exc)

    def _check_flapping(self, endpoint_key: str, now: datetime) -> bool:
        """Sliding window tracking for endpoint flapping."""
        if endpoint_key not in self._flapping_tracker:
            self._flapping_tracker[endpoint_key] = []
        window = self._flapping_tracker[endpoint_key]
        window.append(now)
        # Keep only events within last 10 minutes
        cutoff = now - timedelta(minutes=10)
        self._flapping_tracker[endpoint_key] = [t for t in window if t >= cutoff]
        return len(self._flapping_tracker[endpoint_key]) >= 4

    async def _evaluate_and_send_channel(
        self,
        db: Any,
        channel: AlertChannel,
        endpoint_id: Any,
        endpoint_name: str,
        ip_address: str,
        event_type: str,
        severity: str,
        timestamp: datetime,
        details: Dict[str, Any],
        is_flapping: bool,
    ) -> None:
        # Check endpoint filter
        if channel.endpoint_ids and len(channel.endpoint_ids) > 0:
            if endpoint_id and str(endpoint_id) not in [str(x) for x in channel.endpoint_ids]:
                return

        # Check subnet filter
        if channel.subnet_filters and len(channel.subnet_filters) > 0:
            try:
                ep_ip = ipaddress.ip_address(ip_address)
                matched = False
                for cidr in channel.subnet_filters:
                    try:
                        network = ipaddress.ip_network(cidr, strict=False)
                        if ep_ip in network:
                            matched = True
                            break
                    except ValueError:
                        continue
                if not matched:
                    return
            except ValueError:
                return

        # Check severity filter
        if channel.severity_filters and len(channel.severity_filters) > 0:
            allowed_sevs = [s.upper() for s in channel.severity_filters]
            if severity.upper() not in allowed_sevs:
                return

        # Check Flapping Suppression
        if is_flapping:
            await self._record_delivery_log(
                db=db,
                channel_id=channel.id,
                channel_name=channel.name,
                endpoint_id=UUID(str(endpoint_id)) if endpoint_id else None,
                endpoint_name=endpoint_name,
                event_type=event_type,
                status="THROTTLED",
                status_code=None,
                response_message="Suppressed: Endpoint is flapping (>= 4 transitions in 10 minutes). Alerts quarantined for 15 minutes.",
            )
            return

        # Check Rate Limit (5 minutes per channel, endpoint, severity)
        rl_key = (str(channel.id), str(endpoint_id), severity)
        last_sent = self._rate_limits.get(rl_key)
        if last_sent and (timestamp - last_sent) < timedelta(minutes=5):
            # Log throttled
            await self._record_delivery_log(
                db=db,
                channel_id=channel.id,
                channel_name=channel.name,
                endpoint_id=UUID(str(endpoint_id)) if endpoint_id else None,
                endpoint_name=endpoint_name,
                event_type=event_type,
                status="THROTTLED",
                status_code=None,
                response_message="Throttled by rate limiter (max 1 alert / 5 minutes per severity).",
            )
            return

        # Mark rate limit
        self._rate_limits[rl_key] = timestamp

        # Decrypt channel config
        config = self._parse_channel_config(channel.config)

        # Dispatch
        try:
            status, status_code, message = await self._send_to_provider(
                channel_type=channel.channel_type,
                config=config,
                endpoint_name=endpoint_name,
                ip_address=ip_address,
                event_type=event_type,
                severity=severity,
                timestamp=timestamp,
                details=details,
            )
            await self._record_delivery_log(
                db=db,
                channel_id=channel.id,
                channel_name=channel.name,
                endpoint_id=UUID(str(endpoint_id)) if endpoint_id else None,
                endpoint_name=endpoint_name,
                event_type=event_type,
                status=status,
                status_code=status_code,
                response_message=message,
            )
        except Exception as exc:
            await self._record_delivery_log(
                db=db,
                channel_id=channel.id,
                channel_name=channel.name,
                endpoint_id=UUID(str(endpoint_id)) if endpoint_id else None,
                endpoint_name=endpoint_name,
                event_type=event_type,
                status="FAILED",
                status_code=None,
                response_message=str(exc),
            )

    def _parse_channel_config(self, raw_config: str) -> Dict[str, Any]:
        decrypted = decrypt_secret(raw_config)
        if isinstance(decrypted, dict):
            return decrypted
        try:
            return json.loads(decrypted)
        except Exception:
            return {}

    async def _send_to_provider(
        self,
        channel_type: str,
        config: Dict[str, Any],
        endpoint_name: str,
        ip_address: str,
        event_type: str,
        severity: str,
        timestamp: datetime,
        details: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Optional[int], Optional[str]]:
        ctype = channel_type.upper()

        if ctype in ("TEAMS", "DISCORD", "SLACK", "GENERIC_WEBHOOK"):
            webhook_url = config.get("webhook_url")
            if not webhook_url:
                raise ValueError(f"Webhook URL missing in {channel_type} configuration.")

            await asyncio.to_thread(validate_outbound_url, webhook_url)

            if ctype == "TEAMS":
                payload = build_polyglot_payload(
                    endpoint_name=endpoint_name,
                    ip_address=ip_address,
                    event_type=event_type,
                    severity=severity,
                    timestamp=timestamp,
                    details=details,
                )
            elif ctype == "DISCORD":
                payload = build_discord_payload(
                    endpoint_name=endpoint_name,
                    ip_address=ip_address,
                    event_type=event_type,
                    severity=severity,
                    timestamp=timestamp,
                    details=details,
                )
            elif ctype == "SLACK":
                payload = build_slack_payload(
                    endpoint_name=endpoint_name,
                    ip_address=ip_address,
                    event_type=event_type,
                    severity=severity,
                    timestamp=timestamp,
                    details=details,
                )
            else:  # GENERIC_WEBHOOK
                payload = build_polyglot_payload(
                    endpoint_name=endpoint_name,
                    ip_address=ip_address,
                    event_type=event_type,
                    severity=severity,
                    timestamp=timestamp,
                    details=details,
                )

            headers = {"Content-Type": "application/json"}
            extra_headers = config.get("headers")
            if isinstance(extra_headers, dict):
                headers.update(extra_headers)

            async with httpx.AsyncClient(timeout=5.0) as client:
                last_exc = None
                for attempt in range(3):
                    try:
                        resp = await client.post(webhook_url, json=payload, headers=headers)
                        if 200 <= resp.status_code < 300:
                            return "DELIVERED", resp.status_code, resp.text[:500]
                        if 400 <= resp.status_code < 500:
                            return "FAILED", resp.status_code, resp.text[:500]
                        # For 5xx status codes, retry with exponential backoff
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)
                    except (httpx.RequestError, httpx.TimeoutException) as exc:
                        last_exc = exc
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)

                if last_exc:
                    raise last_exc
                return "FAILED", resp.status_code, resp.text[:500]

        elif ctype == "EMAIL_SMTP":
            to_emails = config.get("to_emails") or [config.get("to_email")]
            to_emails = [e for e in to_emails if e]
            if not to_emails:
                raise ValueError("No recipient email address specified in SMTP configuration.")

            from_email = config.get("from_email") or "lnmp-alerts@local.network"

            for to_addr in to_emails:
                msg = build_email_mime(
                    to_email=to_addr,
                    from_email=from_email,
                    endpoint_name=endpoint_name,
                    ip_address=ip_address,
                    event_type=event_type,
                    severity=severity,
                    timestamp=timestamp,
                    details=details,
                )
                await asyncio.to_thread(self._sync_send_smtp, config, msg)

            return "DELIVERED", 250, f"Dispatched email to {len(to_emails)} recipients."

        else:
            raise ValueError(f"Unsupported channel type '{channel_type}'.")

    def _sync_send_smtp(self, config: Dict[str, Any], msg: Any) -> None:
        host = config.get("smtp_host", "localhost")
        port = int(config.get("smtp_port", 587))
        use_tls = config.get("use_tls", True)
        use_ssl = config.get("use_ssl", False) or port == 465
        username = config.get("username")
        password = config.get("password")

        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, context=context, timeout=10.0)
        else:
            server = smtplib.SMTP(host, port, timeout=10.0)

        try:
            if use_tls and not use_ssl:
                server.starttls(context=context)
            if username and password:
                server.login(username, password)
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                pass

    async def _record_delivery_log(
        self,
        db: Any,
        channel_id: UUID,
        channel_name: str,
        endpoint_id: Optional[UUID],
        endpoint_name: str,
        event_type: str,
        status: str,
        status_code: Optional[int],
        response_message: Optional[str],
    ) -> None:
        try:
            log_entry = AlertDeliveryLog(
                channel_id=channel_id,
                channel_name=channel_name,
                endpoint_id=endpoint_id,
                endpoint_name=endpoint_name,
                event_type=event_type,
                status=status,
                status_code=status_code,
                response_message=response_message[:1000] if response_message else None,
            )
            db.add(log_entry)
            await db.commit()
        except Exception as exc:
            logger.error("AlertDispatcher: Failed to write delivery log: %s", exc)

    async def send_test_alert(self, channel: Any) -> Dict[str, Any]:
        """
        Sends a live test alert probe to verify channel configuration.
        Returns {'success': bool, 'status_code': int | None, 'message': str}.
        """
        if isinstance(channel, dict):
            ctype = channel.get("channel_type", "GENERIC_WEBHOOK")
            raw_cfg = channel.get("config", {})
            cname = channel.get("name", "Test Channel")
            cid = channel.get("id")
        else:
            ctype = channel.channel_type
            raw_cfg = channel.config
            cname = channel.name
            cid = channel.id

        if isinstance(raw_cfg, str):
            config = self._parse_channel_config(raw_cfg)
        else:
            config = raw_cfg

        now = datetime.now(timezone.utc)
        endpoint_name = "test-probe-gateway"
        ip_addr = "192.168.100.1"

        try:
            webhook_url = config.get("webhook_url")
            if webhook_url:
                await asyncio.to_thread(validate_outbound_url, webhook_url)

            status, code, msg = await self._send_to_provider(
                channel_type=ctype,
                config=config,
                endpoint_name=endpoint_name,
                ip_address=ip_addr,
                event_type="TEST_PROBE",
                severity="RECOVERED",
                timestamp=now,
                details={"diagnostic_test": True, "initiated_by": "LNMP Administrator"},
            )

            # Record in delivery logs if channel exists in DB
            if cid:
                async with AsyncSessionLocal() as db:
                    await self._record_delivery_log(
                        db=db,
                        channel_id=UUID(str(cid)),
                        channel_name=cname,
                        endpoint_id=None,
                        endpoint_name=endpoint_name,
                        event_type="TEST_PROBE",
                        status=status,
                        status_code=code,
                        response_message=msg,
                    )

            is_success = (status == "DELIVERED")
            return {
                "success": is_success,
                "status_code": code or (200 if is_success else 500),
                "message": msg or ("Test alert delivered successfully." if is_success else "Delivery failed."),
            }
        except Exception as exc:
            err_msg = str(exc)
            if cid:
                try:
                    async with AsyncSessionLocal() as db:
                        await self._record_delivery_log(
                            db=db,
                            channel_id=UUID(str(cid)),
                            channel_name=cname,
                            endpoint_id=None,
                            endpoint_name=endpoint_name,
                            event_type="TEST_PROBE",
                            status="FAILED",
                            status_code=400,
                            response_message=err_msg,
                        )
                except Exception:
                    pass

            return {
                "success": False,
                "status_code": 400,
                "message": f"Diagnostic test probe failed: {err_msg}",
            }


# Global singleton instance
alert_dispatcher = AlertDispatcher()
