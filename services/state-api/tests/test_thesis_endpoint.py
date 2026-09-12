"""The thesis endpoint fetches; the assembler decides. Nothing here can act."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import thesis as module
from app.main import app, state

client = TestClient(app)
T0 = datetime(2026, 9, 12, 17, 0, tzinfo=timezone.utc)


def _pool(signal_row, regime_row, active_row=None):
    """fetchrow is asked, in order: the active opportunity, the latest signal, the entry regime."""
    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=[active_row, signal_row, regime_row] if active_row is None else [active_row, regime_row])
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire)
    return pool


SIGNAL_ROW = {
    "created_at": T0,
    "features": {
        "admitted": True, "direction": "SHORT", "data_coverage": 0.52, "directional_score": -0.34,
        "evidence": {"evaluated_at_ms": int(T0.timestamp() * 1000),
                     "directional": {"contributors": [{"feature_id": "hl_return_1h_pct", "score": -0.8, "quality": 1.0}]}},
    },
}
REGIME_ROW = {"regime": "falling", "trailing_return_pct": -0.2, "lookback_minutes": 60, "computed_at": T0}


def test_endpoint_assembles_a_private_thesis_from_the_gathered_inputs() -> None:
    async def fake_market(client_, base, path):
        if path.startswith("/candles"):
            return {"candles": [{"time": 1_000_000 + i * 900, "open": 100, "high": 101, "low": 99, "close": 100.5} for i in range(8)]}
        return {"snapshots": [{"symbol": "BTC-PERP", "snapshot_age_ms": 3_000}]}

    async def fake_gate(pool, symbol):
        return {"verdict": {"gate": "CLOSED", "any_economic_edge": False}}

    async def fake_cards(pool, symbol):
        return {"cards": [{"feature_id": "hl_return_1h_pct", "standing": "scoring", "earned": False, "earned_by": []}]}

    async def fake_calendar():
        return {"providers": {"calendar": {"data": {"events": [{"impact": "High", "title": "CPI", "minutes_until": 45}]}}}}

    real_gather = module.gather_inputs

    async def fake_evidence(venue, symbol):
        return ([{"feature_id": "hl_direct_cvd", "current_value": 1500.0, "unit": "USD_delta",
                  "observed_at_ms": int(T0.timestamp() * 1000), "status": "ready", "scoring_allowed": True}], {"status": "live"})

    async def gather_with_fake_calendar(pool, symbol, url, calendar, evidence=None):
        return await real_gather(pool, symbol, url, fake_calendar, fake_evidence)

    with (
        patch.object(state, "pool", _pool(SIGNAL_ROW, REGIME_ROW)),
        patch.object(module, "_market", side_effect=fake_market),
        patch.object(module, "compute_skill_gate", side_effect=fake_gate),
        patch.object(module, "compute_evidence_cards", side_effect=fake_cards),
        patch.object(module, "execution_enabled", return_value=False),
        patch.object(module, "gather_inputs", side_effect=gather_with_fake_calendar),
    ):
        r = client.get("/state/thesis?symbol=BTC-PERP")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["visibility"] == "private" and body["verdict"] == "NO TRADE"
    assert body["structure"]["direction"] == "SHORT" and body["structure"]["entry_regime"] == "falling"
    assert body["confirmation_stack"][0]["feature_id"] == "hl_return_1h_pct"
    codes = {c["code"]: c["active"] for c in body["no_trade_conditions"]}
    assert codes["high_impact_event_near"] and codes["no_demonstrated_edge"] and not codes["stale_evidence"]
    assert body["anchors"]["candles"] == 8 and body["freshness"]["observation_age_ms"] == 3_000
    cvd = next(d for d in body["derivatives"] if d["feature_id"] == "hl_direct_cvd")
    assert cvd["value"] == 1500.0 and "CVD +1,500 USD" in body["text"]


def test_a_refused_signal_yields_no_direction() -> None:
    row = {"created_at": T0, "features": {"admitted": False, "direction": "SHORT", "data_coverage": 0.3, "evidence": {}}}

    async def none(*a, **k):
        return None

    async def empty(pool, symbol):
        return {}

    async def cal():
        return {}

    with patch.object(state, "pool", _pool(row, None)), \
         patch.object(module, "_market", side_effect=none), \
         patch.object(module, "compute_skill_gate", side_effect=empty), \
         patch.object(module, "compute_evidence_cards", side_effect=empty):
        import asyncio
        inputs = asyncio.run(module.gather_inputs(state.pool, "BTC-PERP", "http://x", cal))
    assert inputs["signal"]["direction"] == "NONE" and inputs["regime"] is None
    assert inputs["source_status"]["status"] == "unavailable" and inputs["candles"] == []


def test_an_open_opportunity_is_the_current_read_even_when_the_newest_verdict_refused() -> None:
    import asyncio

    active = {
        "snapshot_ts": T0,
        "expires_at": None,
        "confluence": {"admitted": True, "direction": "SHORT", "data_coverage": 0.6, "directional_score": -0.3,
                        "evidence": {"evaluated_at_ms": 5, "directional": {"contributors": []}}},
    }
    pool = _pool(None, None, active_row=active)
    conn = pool.acquire.return_value.__aenter__.return_value
    read = asyncio.run(module._latest_signal(conn, "BTC-PERP"))
    assert read["direction"] == "SHORT" and read["read_source"] == "active paper opportunity"
    assert conn.fetchrow.await_count == 1  # the signal row was not needed


def test_endpoint_refuses_without_a_pool() -> None:
    with patch.object(state, "pool", None):
        assert client.get("/state/thesis").status_code == 503


def test_module_has_no_path_to_execution_or_models() -> None:
    source = inspect.getsource(module)
    for forbidden in ("exec-hl-svc", "/exec/", "openai", "anthropic", "ollama", "signer"):
        assert forbidden not in source
