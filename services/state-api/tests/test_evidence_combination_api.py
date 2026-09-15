"""The evidence-combination endpoint reads attributed outcomes, serves them from the cache and never writes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import background, statistics_cache
from app import evidence_combination as module
from app.main import app, state

client = TestClient(app)
T0 = datetime(2026, 9, 8, tzinfo=timezone.utc)


def opportunity_id(i: int) -> str:
    return f"00000000-0000-0000-0000-{i:012d}"


def decision_row(i, direction="LONG", signed=0.3, regime="rising", score=0.2):
    return {
        "opportunity_id": opportunity_id(i), "symbol": "BTC-PERP", "direction": direction,
        "opened_at": T0 + timedelta(hours=i), "signed_return_pct": signed, "entry_regime": regime,
        "directional_score": score,
    }


def reading_row(i, feature, value):
    return {"opportunity_id": opportunity_id(i), "feature_id": feature, "value": value}


def market(count: int = 240):
    """Rises and falls alternate; the 1h return reads the move right in 80% of rises and 60% of falls."""
    decisions, readings = [], []
    for i in range(count):
        rose, right = i % 2 == 0, i % 10 < 7
        direction = "LONG" if i % 3 else "SHORT"
        forward = 0.3 if rose else -0.3
        decisions.append(decision_row(i, direction, forward if direction == "LONG" else -forward))
        readings.append(reading_row(i, "hl_return_1h_pct", 0.4 * (1 if rose else -1) * (1 if right else -1)))
        readings.append(reading_row(i, "gdelt_news_tone", 0.0))
    return decisions, readings


def _pool(decision_rows, reading_rows):
    conn = MagicMock()
    conn.fetch = AsyncMock(side_effect=[decision_rows, reading_rows])
    conn.execute = AsyncMock()
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire)
    return pool, conn


def test_rows_become_decisions_with_the_market_move_and_signed_calls() -> None:
    decisions = module.rows_to_decisions(
        [decision_row(0, "LONG", 0.3), decision_row(1, "SHORT", 0.3, score=None), decision_row(2, "NONE", 0.1)],
        [reading_row(0, "hl_return_1h_pct", -0.2), reading_row(1, "coinbase_premium_bps", 0.0),
         reading_row(1, "hl_direct_cvd", 5.0)],
    )
    assert [d.key for d in decisions] == [opportunity_id(0), opportunity_id(1)]
    long_call, short_call = decisions
    assert long_call.forward_return_pct == 0.3 and long_call.calls == {"hl_return_1h_pct": -1}
    assert long_call.rulebook_score == 0.2 and long_call.regime == "rising"
    # A SHORT that earned +0.3% means the market fell 0.3%; a zero reading abstains.
    assert short_call.forward_return_pct == -0.3 and short_call.calls == {"hl_direct_cvd": 1}
    assert short_call.rulebook_score is None


def test_response_labels_sources_with_catalog_standing_and_stays_research_only() -> None:
    decisions, readings = market()
    details = {"hl_return_1h_pct": {"scoring_eligible": True, "block": "price_volatility"}}
    body = module.build_response(60, decisions, readings, cost_pct=0.12, days=14, details=details)
    assert body["authority"] == "research_only" and body["promotion_allowed"] is False
    assert body["assessment"] == "measured" and body["days"] == 14 and body["horizon_minutes"] == 60
    sources = {s["source_id"]: s for s in body["sources"]}
    assert set(sources) == {"hl_return_1h_pct"}  # a source that only ever read zero never called
    source = sources["hl_return_1h_pct"]
    assert source["label"] == "1h return" and source["standing"] == "scoring"
    assert source["block"] == "price_volatility" and source["likelihood_ratio"]["up_call"]["estimate"] > 1
    assert body["forecasts"]["combined"]["log_loss"] < body["forecasts"]["base_rate"]["log_loss"]
    assert body["inputs"]["readings"].startswith("opportunity_entry_features")


def test_a_source_missing_from_the_catalog_is_named_as_such() -> None:
    decisions, readings = market(60)
    body = module.build_response(60, decisions, readings, cost_pct=0.12, days=14, details={})
    assert body["sources"][0]["standing"] == "not_in_catalog" and body["sources"][0]["block"] is None


def test_endpoint_serves_the_measured_reading_and_never_writes() -> None:
    decisions, readings = market()
    pool, conn = _pool(decisions, readings)
    cache = module.CACHES[60]
    cache.clear()
    try:
        asyncio.run(cache.refresh(pool, None))
        with patch.object(state, "pool", pool):
            response = client.get("/state/research/evidence-combination?horizon=60")
    finally:
        cache.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready" and body["computed_at"] and body["cache"]["stale"] is False
    assert body["schema_version"] == "evidence_combination_v1" and body["reading"]
    assert len(body["method"]["digest"]) == 64
    conn.execute.assert_not_called()
    fetched = conn.fetch.await_args_list
    assert all(call.args[0].lstrip().upper().startswith("SELECT") for call in fetched)
    assert [call.args[1:] for call in fetched] == [(60, module.learning_job.WINDOW_DAYS)] * 2


def test_a_cold_reading_answers_computing_and_starts_one_measurement() -> None:
    cache = module.CACHES[240]
    cache.clear()
    try:
        with patch.object(state, "pool", MagicMock()), patch.object(cache, "ensure_measuring") as start:
            response = client.get("/state/research/evidence-combination?horizon=240")
    finally:
        cache.clear()
    assert response.status_code == 202 and response.json()["status"] == "computing"
    assert "4h evidence combination" in response.json()["note"]
    start.assert_called_once()


def test_an_unmeasured_horizon_is_refused() -> None:
    with patch.object(state, "pool", MagicMock()):
        response = client.get("/state/research/evidence-combination?horizon=30")
    assert response.status_code == 422 and "15, 60, 240" in response.json()["detail"]


def test_no_database_answers_503() -> None:
    with patch.object(state, "pool", None):
        assert client.get("/state/research/evidence-combination").status_code == 503


def test_compute_runs_the_statistics_off_the_event_loop() -> None:
    decisions, readings = market(40)
    pool, _ = _pool(decisions, readings)
    with patch.object(module.asyncio, "to_thread", wraps=module.asyncio.to_thread) as offload:
        body = asyncio.run(module.compute_evidence_combination(pool, 15))
    offload.assert_called_once()
    assert body["horizon_minutes"] == 15


def test_every_horizon_is_kept_warm_by_the_shared_refresh_loop() -> None:
    assert "outcome_statistics_refresh" in background.registered()
    assert all(cache in statistics_cache._caches for cache in module.CACHES.values())
