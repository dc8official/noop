from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.services.diagnostics import _parse_trace_output, sanitize_traceroute_hops
from app.services.rca_engine import run_differential_rca
from app.services.topology import TopologyGraphManager, generate_unified_topology


def test_parse_traceroute_and_tracepath_formats():
    traceroute_output = """
traceroute to 8.8.8.8 (8.8.8.8), 30 hops max, 60 byte packets
 1  172.30.0.249  0.635 ms
 2  10.100.111.1  0.552 ms
 3  100.64.0.1  31.055 ms
 4  *
 5  8.8.8.8  32.110 ms
"""
    hops = _parse_trace_output(traceroute_output)
    assert len(hops) == 5
    assert hops[0]["hop"] == 1 and hops[0]["ip"] == "172.30.0.249"
    assert hops[1]["hop"] == 2 and hops[1]["ip"] == "10.100.111.1"
    assert hops[2]["hop"] == 3 and hops[2]["ip"] == "100.64.0.1"
    assert hops[3]["hop"] == 4 and hops[3]["ip"] is None
    assert hops[4]["hop"] == 5 and hops[4]["ip"] == "8.8.8.8"

    tracepath_output = """
 1?: [LOCALHOST]                      pmtu 1500
 1:  172.30.0.249                                          1.247ms asymm  2 
 2:  10.100.111.1                                          0.938ms 
 3:  no reply
 4:  8.8.8.8                                              25.408ms reached
"""
    hops_tp = _parse_trace_output(tracepath_output)
    assert len(hops_tp) == 4
    assert hops_tp[0]["hop"] == 1 and hops_tp[0]["ip"] == "172.30.0.249"
    assert hops_tp[1]["hop"] == 2 and hops_tp[1]["ip"] == "10.100.111.1"
    assert hops_tp[2]["hop"] == 3 and hops_tp[2]["ip"] is None
    assert hops_tp[3]["hop"] == 4 and hops_tp[3]["ip"] == "8.8.8.8"


def test_sanitize_traceroute_hops_preserves_target():
    raw_hops = [
        {"hop": 1, "ip": "172.30.0.249", "rtt_ms": 1.0},
        {"hop": 2, "ip": None, "rtt_ms": None},
        {"hop": 3, "ip": None, "rtt_ms": None},
        {"hop": 4, "ip": None, "rtt_ms": None},
    ]
    sanitized = sanitize_traceroute_hops(raw_hops, target_ip="8.8.8.8")
    assert len(sanitized) == 3
    assert sanitized[0]["ip"] == "172.30.0.249"
    assert sanitized[1]["ip"] is None
    assert sanitized[2]["ip"] == "8.8.8.8"


def test_rca_public_ip_wan_vs_l2():
    async def _test():
        public_ep_id = uuid4()
        mock_db = AsyncMock()

        # Mock endpoint query
        ep_row = MagicMock(
            id=public_ep_id,
            ip_address="8.8.8.8",
            enable_rca=True,
            is_l2_segment=False,
        )
        ep_res = MagicMock()
        ep_res.fetchone.return_value = ep_row

        # Mock baseline query
        bl_row = MagicMock(
            total_hops=2,
            hops=[
                {"hop": 1, "ip": "192.168.1.1", "rtt_ms": 1.0},
                {"hop": 2, "ip": "8.8.8.8", "rtt_ms": 20.0},
            ],
        )
        bl_res = MagicMock()
        bl_res.fetchone.return_value = bl_row

        # Mock incident insert and symptom endpoints query
        inc_res = MagicMock()
        sym_res = MagicMock()
        sym_res.fetchall.return_value = []
        mock_db.execute.side_effect = [ep_res, bl_res, inc_res, sym_res]

        rca_res = await run_differential_rca(public_ep_id, db=mock_db)
        assert rca_res is not None
        assert "Direct Layer 2 Attachment" not in rca_res["rca_summary"]
        assert "Remote L3 Routed Destination" in rca_res["rca_summary"] or "Transit failure" in rca_res["rca_summary"] or "Failure at destination" in rca_res["rca_summary"]

    asyncio.run(_test())


def test_topology_dag_scoped_anonymous_nodes():
    async def _test():
        ep1_id = uuid4()
        ep2_id = uuid4()

        ep_rows = [
            MagicMock(
                id=ep1_id,
                hostname="google-dns-1",
                ip_address="8.8.8.8",
                device_type="DNS",
                location="WAN",
                endpoint_status="ACTIVE",
                allow_topology_discovery=True,
                manual_parent_id=None,
                is_l2_segment=False,
                operational_state="UP",
                detailed_state="UP",
            ),
            MagicMock(
                id=ep2_id,
                hostname="cloudflare-dns",
                ip_address="1.1.1.1",
                device_type="DNS",
                location="WAN",
                endpoint_status="ACTIVE",
                allow_topology_discovery=True,
                manual_parent_id=None,
                is_l2_segment=False,
                operational_state="UP",
                detailed_state="UP",
            ),
        ]

        bl_rows = [
            MagicMock(
                endpoint_id=ep1_id,
                total_hops=3,
                hops=[
                    {"hop": 1, "ip": "192.168.1.1", "rtt_ms": 1.0},
                    {"hop": 2, "ip": None, "rtt_ms": None},
                    {"hop": 3, "ip": "8.8.8.8", "rtt_ms": 20.0},
                ],
            ),
            MagicMock(
                endpoint_id=ep2_id,
                total_hops=3,
                hops=[
                    {"hop": 1, "ip": "192.168.1.1", "rtt_ms": 1.0},
                    {"hop": 2, "ip": None, "rtt_ms": None},
                    {"hop": 3, "ip": "1.1.1.1", "rtt_ms": 15.0},
                ],
            ),
        ]

        mock_db = AsyncMock()
        ep_res = MagicMock()
        ep_res.fetchall.return_value = ep_rows
        bl_res = MagicMock()
        bl_res.fetchall.return_value = bl_rows
        tr_res = MagicMock()
        tr_res.fetchall.return_value = []
        inc_res = MagicMock()
        inc_res.fetchall.return_value = []

        mock_db.execute.side_effect = [ep_res, bl_res, tr_res, inc_res]

        graph = await TopologyGraphManager.get_instance().full_rebuild(mock_db)
        node_ids = {n["id"] for n in graph["nodes"]}

        # Verify that anonymous hops are scoped and do not collide
        anon_ep1 = f"anon_192_168_1_1_to_{str(ep1_id)[:8]}"
        anon_ep2 = f"anon_192_168_1_1_to_{str(ep2_id)[:8]}"
        assert anon_ep1 in node_ids
        assert anon_ep2 in node_ids
        assert anon_ep1 != anon_ep2

    asyncio.run(_test())
