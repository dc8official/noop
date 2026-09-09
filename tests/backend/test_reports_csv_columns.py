import pytest
from app.routers.reports import resolve_export_columns, BatchExportRequest


def test_resolve_export_columns_default():
    cols = resolve_export_columns(None)
    assert len(cols) == 9
    assert cols[0] == "Endpoint_ID"
    assert "Hostname" in cols
    assert "IP_Address" in cols


def test_resolve_export_columns_mandatory_hostname_and_ip():
    # User only selected Timestamp and Operational State, leaving out Hostname and IP
    requested = ["Timestamp", "Operational_State"]
    cols = resolve_export_columns(requested)

    # Hostname and IP_Address must be guaranteed!
    assert "Hostname" in cols
    assert "IP_Address" in cols
    assert "Timestamp" in cols
    assert "Operational_State" in cols
    assert "Endpoint_ID" not in cols  # unselected, not mandatory


def test_resolve_export_columns_aliases():
    requested = ["hostname", "ip address", "health score / packet loss %", "avg latency (rtt ms)"]
    cols = resolve_export_columns(requested)
    assert "Hostname" in cols
    assert "IP_Address" in cols
    assert "Packet_Success_Rate" in cols
    assert "Avg_RTT_ms" in cols


def test_batch_export_request_schema():
    req = BatchExportRequest(
        endpoint_ids=[],
        start_time="2026-09-09T00:00:00Z",
        end_time="2026-09-09T01:00:00Z",
        columns=["Hostname", "IP_Address", "Detailed_State"],
    )
    assert req.columns == ["Hostname", "IP_Address", "Detailed_State"]
