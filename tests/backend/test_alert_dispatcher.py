import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import pytest

from app.services.alert_dispatcher import AlertDispatcher


@pytest.mark.anyio
async def test_alert_dispatcher_flapping_detection():
    dispatcher = AlertDispatcher()
    now = datetime.now(timezone.utc)
    ep_key = "test-node-1"

    assert dispatcher._check_flapping(ep_key, now) is False
    assert dispatcher._check_flapping(ep_key, now + timedelta(seconds=30)) is False
    assert dispatcher._check_flapping(ep_key, now + timedelta(seconds=60)) is False
    # 4th transition within 10 minutes triggers flapping detection
    assert dispatcher._check_flapping(ep_key, now + timedelta(seconds=90)) is True


@pytest.mark.anyio
async def test_alert_dispatcher_send_test_alert_mock_success():
    dispatcher = AlertDispatcher()
    test_channel = {
        "channel_type": "GENERIC_WEBHOOK",
        "name": "Integration Test Webhook",
        "config": {
            "webhook_url": "https://8.8.8.8/webhook",
        },
    }

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.text = "OK"

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await dispatcher.send_test_alert(test_channel)
        assert res["success"] is True
        assert res["status_code"] == 200


@pytest.mark.anyio
async def test_alert_dispatcher_send_test_alert_ssrf_blocked():
    dispatcher = AlertDispatcher()
    test_channel = {
        "channel_type": "TEAMS",
        "name": "Internal Exploitation Webhook",
        "config": {
            "webhook_url": "http://127.0.0.1:8000/internal",
        },
    }
    res = await dispatcher.send_test_alert(test_channel)
    assert res["success"] is False
    assert res["status_code"] == 400
    assert "loopback" in res["message"].lower() or "ssrf" in res["message"].lower()


@pytest.mark.anyio
async def test_subnet_filter_matching():
    from unittest.mock import MagicMock
    from uuid import uuid4

    dispatcher = AlertDispatcher()
    channel = MagicMock()
    channel.id = uuid4()
    channel.name = "Subnet Filter Channel"
    channel.channel_type = "GENERIC_WEBHOOK"
    channel.endpoint_ids = []
    channel.severity_filters = ["DOWN"]
    channel.subnet_filters = ["192.168.1.0/24", "10.0.0.0/8"]
    channel.config = '{"webhook_url": "https://8.8.8.8/hook"}'

    dispatcher._send_to_provider = AsyncMock(return_value=("DELIVERED", 200, "OK"))
    dispatcher._record_delivery_log = AsyncMock()

    # Case A: Inside subnet -> dispatched
    await dispatcher._evaluate_and_send_channel(
        db=None,
        channel=channel,
        endpoint_id=uuid4(),
        endpoint_name="Node-Inside",
        ip_address="192.168.1.50",
        event_type="STATE_TRANSITION",
        severity="DOWN",
        timestamp=datetime.now(timezone.utc),
        details={},
        is_flapping=False,
    )
    dispatcher._send_to_provider.assert_called_once()

    # Case B: Outside subnet -> suppressed early
    dispatcher._send_to_provider.reset_mock()
    await dispatcher._evaluate_and_send_channel(
        db=None,
        channel=channel,
        endpoint_id=uuid4(),
        endpoint_name="Node-Outside",
        ip_address="172.16.0.1",
        event_type="STATE_TRANSITION",
        severity="DOWN",
        timestamp=datetime.now(timezone.utc),
        details={},
        is_flapping=False,
    )
    dispatcher._send_to_provider.assert_not_called()


@pytest.mark.anyio
async def test_flapping_suppression():
    from unittest.mock import MagicMock
    from uuid import uuid4

    dispatcher = AlertDispatcher()
    channel = MagicMock()
    channel.id = uuid4()
    channel.name = "Flapping Test Channel"
    channel.channel_type = "GENERIC_WEBHOOK"
    channel.endpoint_ids = []
    channel.severity_filters = ["DOWN"]
    channel.subnet_filters = []
    channel.config = '{"webhook_url": "https://8.8.8.8/hook"}'

    dispatcher._send_to_provider = AsyncMock(return_value=("DELIVERED", 200, "OK"))
    dispatcher._record_delivery_log = AsyncMock()

    await dispatcher._evaluate_and_send_channel(
        db=None,
        channel=channel,
        endpoint_id=uuid4(),
        endpoint_name="Flapping-Node",
        ip_address="192.168.1.10",
        event_type="STATE_TRANSITION",
        severity="DOWN",
        timestamp=datetime.now(timezone.utc),
        details={},
        is_flapping=True,
    )
    dispatcher._send_to_provider.assert_not_called()
    dispatcher._record_delivery_log.assert_called_once()
    kwargs = dispatcher._record_delivery_log.call_args[1]
    assert kwargs["status"] == "THROTTLED"
    assert "flapping" in kwargs["response_message"].lower()


def test_cache_pruning():
    dispatcher = AlertDispatcher()
    now = datetime.now(timezone.utc)

    # Setup rate limits
    old_key = ("chan1", "ep1", "DOWN")
    recent_key = ("chan2", "ep2", "DOWN")
    dispatcher._rate_limits[old_key] = now - timedelta(hours=2)
    dispatcher._rate_limits[recent_key] = now - timedelta(minutes=10)

    # Setup flapping tracker
    old_flap_ep = "old-flapper"
    active_flap_ep = "active-flapper"
    empty_flap_ep = "empty-flapper"
    dispatcher._flapping_tracker[old_flap_ep] = [now - timedelta(minutes=20), now - timedelta(minutes=15)]
    dispatcher._flapping_tracker[active_flap_ep] = [now - timedelta(minutes=15), now - timedelta(minutes=2)]
    dispatcher._flapping_tracker[empty_flap_ep] = []

    # Prune
    dispatcher._prune_memory_caches(now)

    # Verify rate limits
    assert old_key not in dispatcher._rate_limits
    assert recent_key in dispatcher._rate_limits

    # Verify flapping tracker
    assert old_flap_ep not in dispatcher._flapping_tracker
    assert empty_flap_ep not in dispatcher._flapping_tracker
    assert active_flap_ep in dispatcher._flapping_tracker
    assert len(dispatcher._flapping_tracker[active_flap_ep]) == 1
    assert dispatcher._flapping_tracker[active_flap_ep][0] == now - timedelta(minutes=2)


@pytest.mark.anyio
async def test_leader_election_passive_standby():
    from unittest.mock import MagicMock

    dispatcher = AlertDispatcher()
    mock_conn = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar.return_value = False  # Lock not acquired
    mock_conn.execute.return_value = mock_res

    with patch("app.services.alert_dispatcher.async_engine") as mock_engine:
        mock_engine.dialect.name = "postgresql"
        mock_engine.connect.return_value = mock_conn

        await dispatcher.start()
        assert dispatcher._is_leader is False
        assert dispatcher._running is True
        task_names = [t.get_name() for t in dispatcher._tasks]
        assert "alert_broker_state_trans" not in task_names
        assert "alert_broker_rca" not in task_names

        await dispatcher.stop()


@pytest.mark.anyio
async def test_leader_election_active_leader():
    from unittest.mock import MagicMock

    dispatcher = AlertDispatcher()
    mock_conn = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar.return_value = True  # Lock acquired
    mock_conn.execute.return_value = mock_res

    with patch("app.services.alert_dispatcher.async_engine") as mock_engine, \
         patch.object(dispatcher, "_listen_broker", return_value=None):
        mock_engine.dialect.name = "postgresql"
        mock_engine.connect.return_value = mock_conn

        await dispatcher.start()
        assert dispatcher._is_leader is True
        assert dispatcher._running is True
        task_names = [t.get_name() for t in dispatcher._tasks]
        assert "alert_broker_state_trans" in task_names
        assert "alert_broker_rca" in task_names

        await dispatcher.stop()
        assert any("pg_advisory_unlock" in str(c) for c in mock_conn.execute.call_args_list)
