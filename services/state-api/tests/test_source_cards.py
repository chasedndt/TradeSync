"""Source cards assess every source together and never grant a weight."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import source_cards as module
from app.main import app, state

client = TestClient(app)
T0 = datetime(2026, 9, 12, tzinfo=timezone.utc)


def row(source_id, i, direction, fwd, horizon=60, source="discord", symbol="BTC-PERP"):
    return {"source": source, "source_id": source_id, "symbol": symbol, "direction": direction, "horizon_minutes": horizon,
            "claimed_at": T0 + timedelta(hours=5 * i), "forward_return_pct": fwd,
            "signed_return_pct": fwd if direction == "LONG" else -fwd}


def _skilled(source_id, n=160, right_share=0.8):
    out = []
    for i in range(n):
        direction = "LONG" if i % 2 else "SHORT"
        right = (i % 10) < int(right_share * 10)
        fwd = (0.2 if direction == "LONG" else -0.2) if right else (-0.2 if direction == "LONG" else 0.2)
        out.append(row(source_id, i, direction, fwd))
    return out


def _coverage(source_id, claims, measured, source="discord"):
    return {"source": source, "source_id": source_id, "claims": claims, "measured": measured, "latest": T0}


EXTRACTION = {"with_claims": 3, "without": 40, "pending": 2}


def test_cells_are_keyed_by_source_horizon_and_both_polarities() -> None:
    cells = module.rows_to_cells([row("a", 0, "LONG", 0.1), row("a", 1, "SHORT", 0.1, horizon=15)])
    assert set(cells) == {("discord", "a", 60, "as_stated"), ("discord", "a", 60, "inverted"),
                          ("discord", "a", 15, "as_stated"), ("discord", "a", 15, "inverted")}
    inv = cells[("discord", "a", 60, "inverted")][0]
    assert inv.direction == "SHORT" and inv.signed_return_pct == -0.1


def test_a_skilled_source_earns_and_a_coin_flip_does_not() -> None:
    rows = _skilled("thesis-desk") + _skilled("noise", right_share=0.5)
    resp = module.build_response(None, rows, [_coverage("thesis-desk", 160, 160), _coverage("noise", 160, 160)], EXTRACTION, draws=60)
    by = {c["source_id"]: c for c in resp["cards"]}
    assert by["thesis-desk"]["earned"] and by["thesis-desk"]["earned_by"] == ["60m as_stated"]
    assert not by["noise"]["earned"] and by["noise"]["next_step"].startswith("keeps recording")
    assert resp["cards"][0]["source_id"] == "thesis-desk"  # earned first
    assert resp["extraction"] == {"rows_with_claims": 3, "rows_without_claims": 40, "rows_pending": 2}
    assert resp["cells_assessed_together"] == 4


def test_a_source_with_claims_but_nothing_measured_still_gets_a_card() -> None:
    resp = module.build_response("BTC-PERP", [], [_coverage("ema-cross", 2, 0, "tradingview")], EXTRACTION, draws=10)
    assert resp["cards"][0]["source_id"] == "ema-cross" and resp["cards"][0]["cells"] == [] and not resp["cards"][0]["earned"]


def test_endpoint_reads_and_filters_by_symbol() -> None:
    conn = MagicMock()
    conn.fetch = AsyncMock(side_effect=[[], [_coverage("x", 1, 0)]])
    conn.fetchrow = AsyncMock(return_value=EXTRACTION)
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire)
    with patch.object(state, "pool", pool):
        r = client.get("/state/outcomes/source-cards?symbol=ETH-PERP")
    assert r.status_code == 200 and r.json()["symbol"] == "ETH-PERP"
    assert all(call.args[1] == "ETH-PERP" for call in conn.fetch.call_args_list)


def test_endpoint_refuses_without_a_pool_and_has_no_write_path() -> None:
    with patch.object(state, "pool", None):
        assert client.get("/state/outcomes/source-cards").status_code == 503
    source = inspect.getsource(module)
    assert "INSERT" not in source and "UPDATE" not in source and "write_text" not in source
