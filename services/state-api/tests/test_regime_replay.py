"""Evaluate judges a challenger by replaying stored decisions, bounded and named when slow."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import regime_replay as module
from app.main import app, state

client = TestClient(app)
T0 = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)
WEIGHTS = {"price_volatility": 0.30, "liquidity": 0.25, "positioning": 0.20, "spot_premium": 0.15, "macro_flows": 0.10}
EMPTY_BLOCKS = {"price_volatility": 0.10, "liquidity": 0.10, "positioning": 0.40, "spot_premium": 0.30, "macro_flows": 0.10}


def row(signal_id, *, sampled=True, outcome=None, at_ms=1_789_000_000_000, contributions=True):
    return {
        "id": signal_id,
        "symbol": "BTC-PERP",
        "contributions": json.dumps({
            "price_volatility": {"score": 0.5, "quality": 1.0},
            "liquidity": {"score": -0.2, "quality": 0.5},
        }) if contributions else None,
        "directional": json.dumps({
            "score": 0.6, "coverage": 1.0,
            "contributors": [{"feature_id": "hl_return_1h_pct", "score": 0.6, "quality": 1.0}],
        }),
        "evaluated_at_ms": str(at_ms),
        "signed_return_pct": outcome,
        "forward_return_pct": outcome,
        "sampled": sampled,
    }


SUMMARY = {"decisions": 1440, "refusals": 900, "first_at": T0, "first_refusal_at": T0}


def _pool(rows, summary=SUMMARY, fetch_error=None):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=summary)
    conn.fetch = AsyncMock(return_value=rows, side_effect=fetch_error)
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire)
    return pool, conn


def test_replay_counts_what_the_challenger_changes_and_describes_the_window():
    pool, conn = _pool([row("a", outcome=0.4), row("b", sampled=False, outcome=-0.2), row("c")])
    with patch.object(state, "pool", pool):
        r = client.post("/state/regime-lab/replay", json={"hours": 168, "challenger_weights": EMPTY_BLOCKS})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decisions"]["replayed"] == 2 and body["decisions"]["admissions_lost"] == 2
    assert body["outcomes"]["cases_with_outcome"] == 2
    assert body["outcomes"]["baseline"]["admitted_with_outcome"] == 2
    assert body["outcomes"]["challenger"]["admitted_with_outcome"] == 0
    window = body["window"]
    assert window["hours"] == 168 and window["horizon_minutes"] == 60 and window["sample_bucket_seconds"] == 600
    assert window["decisions_in_window"] == 1440 and window["refusals_available_since"] == T0.isoformat()
    assert window["refusal_retention_days"] == 7 and body["execution_authority"] is False
    # The pool's five-second command timeout is replaced, and the bucket and horizon reach the query.
    args, kwargs = conn.fetch.call_args
    assert kwargs["timeout"] == module.QUERY_TIMEOUT_S and args[2:] == (168, None, 600, 60)


def test_rows_that_cannot_be_replayed_are_counted_not_guessed():
    cases, sampled, skipped = module.cases_from_rows([row("good"), row("old", contributions=False)])
    assert [case.signal_id for case in cases] == ["good"] and sampled == {"good"} and skipped == 1


def test_invalid_weights_answer_422_with_the_reason():
    pool, _ = _pool([])
    with patch.object(state, "pool", pool):
        r = client.post("/state/regime-lab/replay", json={"challenger_weights": {**WEIGHTS, "liquidity": 0.5}})
    assert r.status_code == 422 and "liquidity" in r.json()["detail"]


def test_only_the_offered_windows_and_horizons_are_accepted():
    pool, _ = _pool([])
    with patch.object(state, "pool", pool):
        bad_window = client.post("/state/regime-lab/replay", json={"hours": 48, "challenger_weights": WEIGHTS})
        bad_horizon = client.post("/state/regime-lab/replay", json={"horizon_minutes": 30, "challenger_weights": WEIGHTS})
    assert bad_window.status_code == 422 and bad_horizon.status_code == 422


def test_a_slow_query_is_a_named_504_not_an_empty_error():
    pool, _ = _pool([], fetch_error=asyncio.TimeoutError())
    with patch.object(state, "pool", pool):
        r = client.post("/state/regime-lab/replay", json={"hours": 720, "challenger_weights": WEIGHTS})
    assert r.status_code == 504 and "did not finish within 45 s" in r.json()["detail"]


def test_an_empty_window_is_an_answer_with_zero_counts():
    pool, _ = _pool([], summary={"decisions": 0, "refusals": 0, "first_at": None, "first_refusal_at": None})
    with patch.object(state, "pool", pool):
        r = client.post("/state/regime-lab/replay", json={"challenger_weights": WEIGHTS, "symbol": "ETH-PERP"})
    assert r.status_code == 200
    body = r.json()
    assert body["decisions"]["replayed"] == 0 and body["outcomes"]["baseline"]["hit_rate"] is None
    assert body["window"]["symbol"] == "ETH-PERP" and body["window"]["first_decision_at"] is None


def test_replay_refuses_without_a_database():
    with patch.object(state, "pool", None):
        r = client.post("/state/regime-lab/replay", json={"challenger_weights": WEIGHTS})
    assert r.status_code == 503 and "PostgreSQL" in r.json()["detail"]


def test_the_replay_itself_runs_off_the_event_loop():
    pool, _ = _pool([row("a", outcome=0.1)])
    challenger = module.challenger_from_request(module.regime_lab_engine, WEIGHTS, "same")
    with patch.object(module.asyncio, "to_thread", wraps=module.asyncio.to_thread) as offload:
        result = asyncio.run(module.run_replay(
            pool, module.regime_lab_engine, hours=24, horizon_minutes=15, symbol=None, challenger=challenger,
        ))
    offload.assert_called_once()
    assert result["decisions"]["changed"] == 0 and result["window"]["sample_bucket_seconds"] == 60
