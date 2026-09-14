"""Saved drafts keep their hypothesis, weights and replay judgement, and list them back."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app, state
from app.regime_lab_experiments import evaluation_plan, experiment_summary

client = TestClient(app)
T0 = datetime(2026, 9, 14, 12, 30, tzinfo=timezone.utc)


def stored_row(**overrides):
    row = {
        "id": "0f3b8a52-8d1e-4c55-9d7e-6c4bd1a1f001",
        "name": "More price weight",
        "status": "draft",
        "hypothesis": "More price weight should admit more trending setups.",
        "evaluation_plan": json.dumps({
            "method": "stored_decision_replay", "window_hours": 168, "horizon_minutes": 60,
            "symbol": None, "mode": "paper_shadow",
        }),
        "results": json.dumps({"replay": {
            "decisions": {"replayed": 1000, "changed": 12},
            "outcomes": {"cases_with_outcome": 40},
            "window": {"hours": 168},
            "changed_examples": [{"signal_id": "x"}],
        }}),
        "created_at": T0,
        "baseline_version": "1.0.0",
        "challenger_version": "1.0.0-c1",
        "challenger_blocks": json.dumps({
            "price_volatility": {"weight": 0.4, "decision_role": "direction_and_state"},
            "liquidity": {"weight": 0.15},
        }),
    }
    row.update(overrides)
    return row


def _pool(fetch):
    conn = MagicMock()
    conn.fetch = fetch
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire)
    return pool, conn


def test_a_draft_lists_its_hypothesis_weights_and_judgement_without_the_examples():
    summary = experiment_summary(stored_row())
    assert summary["hypothesis"].startswith("More price weight")
    assert summary["weights"] == {"price_volatility": 0.4, "liquidity": 0.15}
    assert (summary["window_hours"], summary["horizon_minutes"], summary["symbol"]) == (168, 60, None)
    assert summary["replay"]["decisions"]["changed"] == 12 and "changed_examples" not in summary["replay"]
    assert summary["created_at"] == T0.isoformat()


def test_a_draft_saved_before_replay_judging_lists_without_a_judgement():
    old = stored_row(
        evaluation_plan=json.dumps({"evaluation_window": "current evidence snapshot"}),
        results=json.dumps({"comparison": {}, "source_snapshot_only": True}),
    )
    summary = experiment_summary(old)
    assert summary["replay"] is None and summary["window_hours"] is None


def test_the_plan_records_the_replay_window():
    plan = evaluation_plan({"window": {"hours": 720, "horizon_minutes": 240, "symbol": "SOL-PERP"}})
    assert plan == {
        "method": "stored_decision_replay", "window_hours": 720, "horizon_minutes": 240,
        "symbol": "SOL-PERP", "mode": "paper_shadow",
    }


def test_the_list_route_returns_summaries():
    pool, conn = _pool(AsyncMock(return_value=[stored_row()]))
    with patch.object(state, "pool", pool):
        response = client.get("/state/regime-lab/experiments?limit=8")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1 and body["experiments"][0]["replay"]["outcomes"]["cases_with_outcome"] == 40
    assert conn.fetch.call_args.args[1] == 8


def test_an_unreadable_history_names_the_failure():
    pool, _ = _pool(AsyncMock(side_effect=RuntimeError("relation regime_experiments does not exist")))
    with patch.object(state, "pool", pool):
        response = client.get("/state/regime-lab/experiments")
    assert response.status_code == 503 and "RuntimeError" in response.json()["detail"]
