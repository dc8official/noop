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
