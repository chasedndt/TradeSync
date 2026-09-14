"""Evidence cards report what each feature earned and never touch the catalog."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import evidence_cards as module
from app.main import app, state
from tradesync_core.feature_evidence import FeatureOutcomeRow

client = TestClient(app)
T0 = datetime(2026, 9, 12, tzinfo=timezone.utc)

SPECS = {
    "gdelt_news_tone": {"scoring_eligible": False, "block": "narrative", "unit": "tone_score",
                        "provenance": "context_only", "source_authority": "context_only",
                        "decision_role": "candidate"},
    "coinbase_premium_bps": {"scoring_eligible": True, "block": "flow", "unit": "basis_points",
                             "provenance": "derived", "source_authority": "external_reference_venue",
                             "decision_role": "admitted"},
}


def _pool(rows, coverage, pending):
    conn = MagicMock()
    conn.fetch = AsyncMock(side_effect=[rows, coverage])
    conn.fetchval = AsyncMock(return_value=pending)
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire)
    return pool


def test_rows_become_feature_outcomes() -> None:
    rows = [{"feature_id": "x", "symbol": "BTC-PERP", "opened_at": T0, "horizon_minutes": 15,
             "forward_return_pct": 0.3, "value": -2}]
    out = module.rows_to_feature_outcomes(rows)
    assert out == [FeatureOutcomeRow("x", "BTC-PERP", int(T0.timestamp()), 15, 0.3, -2.0)]


def test_response_has_a_card_per_candidate_with_standing_coverage_and_next_step() -> None:
    resp = module.build_response(
        None, "1.7.0", SPECS, [], {"gdelt_news_tone": {"present": 12, "absent": 3}}, pending=7, draws=10
    )
    assert resp["schema_version"] == "evidence_cards_v1" and resp["entries_pending"] == 7
    by_id = {c["feature_id"]: c for c in resp["cards"]}
    tone, prem = by_id["gdelt_news_tone"], by_id["coinbase_premium_bps"]
    assert tone["standing"] == "context_only" and tone["entries_with_reading"] == 12
    assert tone["entries_without_reading"] == 3 and tone["next_step"].startswith("stays context-only")
    assert prem["standing"] == "scoring" and "NOT yet supported" in prem["next_step"]
    assert not tone["earned"] and not prem["earned"]
    assert resp["costs"]["total_pct"] > 0 and "operator decision" in resp["note"]


def test_an_earned_context_feature_points_at_an_operator_decision_not_a_flag_flip() -> None:
    rows = []
    for i in range(160):
        value = 1.0 if i % 2 else -1.0
        agrees = (i % 10) < 8
        fwd = 0.2 if (value > 0) == agrees else -0.2
        rows.append(FeatureOutcomeRow("gdelt_news_tone", "BTC-PERP", i * 5 * 3600, 60, fwd, value))
    resp = module.build_response(None, "1.7.0", SPECS, rows, {}, pending=0, draws=50)
    tone = next(c for c in resp["cards"] if c["feature_id"] == "gdelt_news_tone")
    assert tone["earned"] and tone["earned_by"] == ["60m as_read"]
    assert "operator may admit" in tone["next_step"]


def test_endpoint_serves_the_measured_reading_with_computed_at_and_filters_by_symbol() -> None:
    pool = _pool([], [{"feature_id": "gdelt_news_tone", "present": 1, "absent": 0}], 4)
    module.CACHE.clear()
    try:
        # What the background measurement does after the first request for a market.
        asyncio.run(module.CACHE.refresh(pool, "ETH-PERP"))
        with patch.object(state, "pool", pool):
            r = client.get("/state/outcomes/evidence-cards?symbol=eth-perp")
    finally:
        module.CACHE.clear()
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready" and body["computed_at"] and body["cache"]["ttl_s"] == 600
    assert body["symbol"] == "ETH-PERP" and body["entries_pending"] == 4
    assert {c["feature_id"] for c in body["cards"]} >= {"gdelt_news_tone", "coinbase_premium_bps",
                                                        "funding_spread_vs_binance_bps"}
    conn = pool.acquire.return_value.__aenter__.return_value
    assert all(call.args[1] == "ETH-PERP" for call in conn.fetch.call_args_list)


def test_a_market_not_yet_measured_answers_computing_without_waiting() -> None:
    module.CACHE.clear()
    try:
        with patch.object(state, "pool", MagicMock()), patch.object(module.CACHE, "ensure_measuring") as start:
            r = client.get("/state/outcomes/evidence-cards?symbol=SOL-PERP")
    finally:
        module.CACHE.clear()
    assert r.status_code == 202
    assert r.json()["status"] == "computing" and r.json()["computed_at"] is None
    start.assert_called_once()


def test_endpoint_rejects_a_malformed_symbol() -> None:
    with patch.object(state, "pool", MagicMock()):
        assert client.get("/state/outcomes/evidence-cards?symbol=ETH;drop").status_code == 400


def test_endpoint_refuses_without_a_pool() -> None:
    with patch.object(state, "pool", None):
        assert client.get("/state/outcomes/evidence-cards").status_code == 503


def test_module_has_no_write_path_to_the_catalog() -> None:
    import inspect

    source = inspect.getsource(module)
    assert "write_text" not in source and "json.dump" not in source
    assert "scoring_eligible\"] =" not in source
