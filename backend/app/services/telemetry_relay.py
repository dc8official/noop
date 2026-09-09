from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from app.routers.events import broadcast_sse_event
from app.services.alert_dispatcher import alert_dispatcher
from app.services.driver_manager import driver_manager
from app.services.topology import topology_manager

logger = logging.getLogger(__name__)


class TelemetryRelay:
    """
    Inter-process telemetry relay bridge.
    Subscribes to monitoring engine pub/sub channels (STATE_TRANSITION and NODE_STATE_CHANGE)
    via the active EventBroker (PostgreSQL LISTEN/NOTIFY or Redis Pub/Sub),
    updates API server in-memory DAG topology_manager, and broadcasts SSE envelopes
    to connected browser clients.
    """

    def __init__(self) -> None:
        self._running: bool = False
        self._tasks: List[asyncio.Task] = []

    async def start(self) -> None:
        """Starts background listener tasks for telemetry pub/sub channels."""
        if self._running:
            return
        self._running = True
        self._tasks.append(
            asyncio.create_task(
                self._listen_channel("STATE_TRANSITION"),
                name="telemetry_relay_state_transition",
            )
        )
        self._tasks.append(
            asyncio.create_task(
                self._listen_channel("NODE_STATE_CHANGE"),
                name="telemetry_relay_node_state_change",
            )
        )
        self._tasks.append(
            asyncio.create_task(
                self._listen_channel("RCA_INCIDENT"),
                name="telemetry_relay_rca_incident",
            )
        )
        logger.info("TelemetryRelay started listening to inter-process broker channels.")

    async def stop(self) -> None:
        """Stops background listener tasks cleanly."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()
        logger.info("TelemetryRelay stopped.")

    async def _listen_channel(self, channel: str) -> None:
        """Listens to a broker channel with automatic reconnection loop."""
        while self._running:
            try:
                broker = driver_manager.get_event_broker()
                async for event in broker.subscribe(channel):
                    if not self._running:
                        break
                    await self._handle_relayed_event(channel, event)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "TelemetryRelay: subscription to '%s' encountered error: %s. Retrying in 2s...",
                    channel,
                    exc,
                )
                await asyncio.sleep(2.0)

    async def _handle_relayed_event(self, channel: str, data: Dict[str, Any]) -> None:
        """Processes an incoming event from the event broker."""
        try:
            # 1. Synchronize API in-memory topology manager
            if channel == "STATE_TRANSITION":
                endpoint_id = data.get("endpoint_id")
                new_state = data.get("current_state") or data.get("operational_state")
                if endpoint_id and new_state:
                    await topology_manager.update_node_status(
                        str(endpoint_id), str(new_state)
                    )
            elif channel == "NODE_STATE_CHANGE":
                node_id = data.get("node_id") or data.get("endpoint_id")
                new_state = data.get("operational_state") or data.get("new_state")
                if node_id and new_state:
                    await topology_manager.update_node_status(
                        str(node_id), str(new_state)
                    )

            # 2. Push SSE event payload to connected browser streams
            await broadcast_sse_event(channel, data)

            # 3. Asynchronously enqueue to Enterprise Alert Dispatcher
            if channel in ("STATE_TRANSITION", "RCA_INCIDENT", "NODE_STATE_CHANGE"):
                await alert_dispatcher.enqueue_event(channel, data)
        except Exception as exc:
            logger.error(
                "TelemetryRelay: failed to process event on channel '%s': %s",
                channel,
                exc,
            )


# Global singleton instance
telemetry_relay = TelemetryRelay()
