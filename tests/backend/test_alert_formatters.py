from datetime import datetime, timezone
import pytest
from app.services.alert_formatters import (
    build_discord_payload,
    build_email_mime,
    build_polyglot_payload,
    build_slack_payload,
)


def test_build_polyglot_teams_down():
    now = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)
    payload = build_polyglot_payload(
        endpoint_name="core-router-01",
        ip_address="192.168.10.1",
        event_type="STATE_TRANSITION",
        severity="DOWN",
        timestamp=now,
        details={"avg_rtt_ms": 125.4, "packet_loss_pct": 100},
        portal_url="https://netmon.corp/endpoints/1",
    )
    assert payload["type"] == "message"
    assert "attachments" in payload
    card = payload["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.4"
    assert card["body"][0]["style"] == "attention"
    assert "core-router-01" in payload["text"]
    assert "DOWN" in payload["text"]
    assert "<div" in payload["html_content"]


def test_build_polyglot_teams_recovered():
    payload = build_polyglot_payload(
        endpoint_name="core-router-01",
        ip_address="192.168.10.1",
        event_type="STATE_TRANSITION",
        severity="RECOVERED",
    )
    card = payload["attachments"][0]["content"]
    assert card["body"][0]["style"] == "good"
    assert payload["severity"] == "RECOVERED"


def test_build_discord_payload():
    down_embed = build_discord_payload(
        endpoint_name="edge-fw",
        ip_address="10.0.0.1",
        event_type="STATE_TRANSITION",
        severity="DOWN",
    )
    assert down_embed["embeds"][0]["color"] == 15158332

    up_embed = build_discord_payload(
        endpoint_name="edge-fw",
        ip_address="10.0.0.1",
        event_type="STATE_TRANSITION",
        severity="RECOVERED",
    )
    assert up_embed["embeds"][0]["color"] == 3066993


def test_build_slack_payload():
    payload = build_slack_payload(
        endpoint_name="db-cluster-01",
        ip_address="172.16.0.50",
        event_type="RCA_INCIDENT",
        severity="CRITICAL",
        portal_url="https://netmon.corp",
    )
    assert len(payload["blocks"]) >= 3
    assert payload["blocks"][0]["type"] == "header"
    assert "db-cluster-01" in payload["text"]


def test_build_email_mime_crlf_sanitization():
    # Attempt email header injection
    malicious_from = "alerts@corp.net\r\nBcc: attacker@evil.com\r\nSubject: Injected"
    malicious_subject = "Normal Subject\r\nX-Spam: High"
    msg = build_email_mime(
        to_email="ops-team@corp.net\r\nCc: leaked@corp.net",
        from_email=malicious_from,
        endpoint_name="san-storage-01",
        ip_address="10.20.30.40",
        event_type="STATE_TRANSITION",
        severity="DOWN",
    )
    # Check that headers do not contain literal newlines or carriage returns
    assert "\r" not in msg["From"] and "\n" not in msg["From"]
    assert "\r" not in msg["To"] and "\n" not in msg["To"]
    assert "\r" not in msg["Subject"] and "\n" not in msg["Subject"]
    assert "san-storage-01" in msg["Subject"]
    # Check payload has both plain and html parts
    parts = list(msg.iter_parts())
    assert len(parts) == 2
    assert parts[0].get_content_type() == "text/plain"
    assert parts[1].get_content_type() == "text/html"
