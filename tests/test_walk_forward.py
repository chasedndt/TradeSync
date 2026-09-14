"""Walk-forward learning: chronological split, scoring on newer decisions, deterministic results."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from learning_fixtures import stored_decision  # noqa: E402

from tradesync_core.attribution import MeasuredHorizon  # noqa: E402
from tradesync_core.regime_weights import load_rulebook, validate_rulebook  # noqa: E402
from tradesync_core.walk_forward import (  # noqa: E402
    DecisionRecord,
    WalkForwardConfig,
    chronological_split,
    run_walk_forward,
)
from tradesync_core.walk_forward_replay import replay_metrics  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BASELINE = load_rulebook(ROOT / "config" / "regime" / "regime-rulebook-v1.json")


def rulebook_with(feature_weights):
    data = json.loads(json.dumps(BASELINE.data))
    data["feature_weights"] = feature_weights
    data["version"] = "test-weights"
    return validate_rulebook(data)


def record(i, market_up, horizon=60, spacing_s=3600):
    """CVD always points with the market, the 1h return always against it."""
    cvd, ret = (0.7, -0.3) if market_up else (-0.7, 0.3)
    direction = "LONG" if market_up else "SHORT"
    return DecisionRecord(
        opportunity_id=f"opp-{i:04d}", symbol="BTC-PERP", direction=direction,
        opened_at_s=1_788_800_400 + i * spacing_s,
        decision=stored_decision(direction=direction, ret=ret, cvd=cvd, liquidity=False),
        entry_regime="rising", horizons={horizon: MeasuredHorizon(horizon, 0.5, 0.6, 0.05)},
    )


def test_the_split_is_chronological_and_purges_overlapping_windows() -> None:
    records = [record(i, i % 2 == 0, spacing_s=600) for i in range(10)]
    learn, test, purged = chronological_split(list(reversed(records)), WalkForwardConfig(horizon_minutes=60))
    assert [r.opportunity_id for r in test] == [f"opp-{i:04d}" for i in range(7, 10)]
    assert [r.opportunity_id for r in learn] == ["opp-0000", "opp-0001"]
    assert purged == 5


def test_without_a_verdict_nothing_is_proposed() -> None:
    result = run_walk_forward([record(i, i % 2 == 0) for i in range(20)], BASELINE, "1.0.0-learn.t")
    assert result.proposal is None
    assert "no feature or block has a verdict" in result.reason
    assert result.evidence["window"]["test"]["decisions"] == 6


def test_walk_forward_learns_on_old_decisions_tests_on_new_and_is_deterministic() -> None:
    records = [record(i, i % 2 == 0) for i in range(300)]
    first = run_walk_forward(records, BASELINE, "1.0.0-learn.t")
    second = run_walk_forward(list(reversed(records)), BASELINE, "1.0.0-learn.t")
    assert first.proposal is not None
    assert first.proposal.digest == second.proposal.digest
    assert json.dumps(first.replay, sort_keys=True) == json.dumps(second.replay, sort_keys=True)
    assert json.dumps(first.evidence, sort_keys=True) == json.dumps(second.evidence, sort_keys=True)
    window = first.evidence["window"]
    assert window["test"]["first_opened_at_s"] > window["learn"]["last_opened_at_s"]
    assert first.proposal.feature_weights == {"hl_direct_cvd": 1.2, "hl_return_1h_pct": 0.8}
    assert first.replay["baseline"]["decisions"] == first.replay["proposal"]["decisions"] == 90
    assert first.replay["baseline"]["reproduced_share"] == 1.0
    assert first.evidence["guardrails"]["risk_caps_unchanged"] is True
    assert first.proposal.data["lineage"]["parent_digest"] == BASELINE.digest


def test_replay_metrics_flip_the_measured_move_with_the_side() -> None:
    long_call = record(0, True)  # stored LONG, market +0.5%
    inside_deadband = rulebook_with({"hl_return_1h_pct": 4.0})  # (-1.2 + 0.7) / 5 = -0.1
    assert replay_metrics([long_call], inside_deadband, 60, 0.12)["refused"] == 1
    short_book = rulebook_with({"hl_direct_cvd": 0.25, "hl_return_1h_pct": 4.0})  # (-1.2 + 0.175) / 4.25
    metrics = replay_metrics([long_call], short_book, 60, 0.12)
    assert metrics["flipped"] == 1
    assert metrics["mean_net_return_pct"] == pytest.approx(-0.62)
