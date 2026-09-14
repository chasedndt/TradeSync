"""Proposals move weights by bounded steps, only where there is a verdict, inside the rulebook caps."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradesync_core.learning_aggregate import GroupEvidence
from tradesync_core.learning_proposal import (
    LearningLimits,
    build_challenger,
    capped_normalise,
    proposal_version,
    propose_weight_change,
)
from tradesync_core.regime_weights import load_rulebook, validate_rulebook

ROOT = Path(__file__).resolve().parents[1]
BASELINE = load_rulebook(ROOT / "config" / "regime" / "regime-rulebook-v1.json")


def group(key, verdict, dimension="feature", role="directional", horizon=60):
    return GroupEvidence(
        dimension=dimension, key=key, label=key, role=role, horizon_minutes=horizon, attributions=100,
        decided=100, supported=50, misled=50, neutral=0, misled_rate=0.5, misled_low=0.4, misled_high=0.6,
        chance_misled_rate=0.5, weighted_misled_share=0.5, effective_samples=80.0, mean_net_return_pct=0.0,
        mean_net_agreed_pct=0.0, agreed=50, mean_net_disagreed_pct=0.0, disagreed=50, verdict=verdict,
    )


def with_feature_weights(weights):
    data = json.loads(json.dumps(BASELINE.data))
    data["feature_weights"] = weights
    return validate_rulebook(data)


def test_capped_normalise_keeps_proportions_and_an_exact_sum() -> None:
    weights = capped_normalise({"a": 0.36, "b": 0.2, "c": 0.2, "d": 0.15, "e": 0.1}, cap=0.4)
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)
    assert weights["b"] == pytest.approx(weights["c"])
    assert max(weights.values()) <= 0.4


def test_capped_normalise_redistributes_what_the_cap_holds_back() -> None:
    weights = capped_normalise({"a": 0.468, "b": 0.31, "c": 0.3}, cap=0.4)
    assert weights["a"] == 0.4
    assert weights["b"] == pytest.approx(0.31 / 0.61 * 0.6, abs=1e-6)
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)


def test_a_hurting_block_is_scaled_down_within_the_single_block_cap() -> None:
    change = propose_weight_change(BASELINE, [], [group("liquidity", "hurting", "block", "suitability")], 60)
    after = {name: detail["after"] for name, detail in change.blocks.items()}
    assert change.changed
    assert after["liquidity"] < BASELINE.weights["liquidity"]
    assert after["price_volatility"] > BASELINE.weights["price_volatility"]
    assert sum(after.values()) == pytest.approx(1.0, abs=1e-9)
    assert max(after.values()) <= BASELINE.data["validation"]["max_single_block_weight"]


def test_only_directional_features_with_a_verdict_get_a_multiplier() -> None:
    groups = [
        group("hl_direct_cvd", "helping"),
        group("hl_return_1h_pct", "hurting"),
        group("hl_spread_bps", "hurting", role="suitability"),
        group("coinbase_premium_bps", "no_evidence"),
    ]
    change = propose_weight_change(BASELINE, groups, [], 60, LearningLimits(step=0.2))
    assert change.features == {
        "hl_direct_cvd": {"before": 1.0, "after": 1.2, "verdict": "helping"},
        "hl_return_1h_pct": {"before": 1.0, "after": 0.8, "verdict": "hurting"},
    }
    assert all(d["after"] == d["before"] for d in change.blocks.values())


def test_verdicts_at_another_horizon_are_ignored() -> None:
    change = propose_weight_change(BASELINE, [group("hl_direct_cvd", "helping", horizon=15)], [], 60)
    assert not change.changed


def test_no_verdict_means_no_proposal() -> None:
    assert not propose_weight_change(BASELINE, [group("hl_direct_cvd", "no_evidence")], [], 60).changed


def test_multipliers_are_clamped_to_the_learning_limits() -> None:
    parent = with_feature_weights({"hl_direct_cvd": 1.9, "hl_return_1h_pct": 0.3})
    groups = [group("hl_direct_cvd", "helping"), group("hl_return_1h_pct", "hurting")]
    change = propose_weight_change(parent, groups, [], 60)
    assert change.features["hl_direct_cvd"]["after"] == 2.0
    assert change.features["hl_return_1h_pct"]["after"] == 0.25


def test_the_challenger_is_valid_carries_lineage_and_leaves_risk_alone() -> None:
    groups = [group("hl_direct_cvd", "helping")]
    blocks = [group("liquidity", "hurting", "block", "suitability")]
    change = propose_weight_change(BASELINE, groups, blocks, 60)
    challenger = build_challenger(BASELINE, change, proposal_version(BASELINE.version, "202609141200"), "Trust CVD more.")
    assert challenger.version == "1.0.0-learn.202609141200"
    assert challenger.data["lineage"]["parent_digest"] == BASELINE.digest
    assert challenger.data["paper_risk"] == BASELINE.data["paper_risk"]
    assert challenger.feature_weights == {"hl_direct_cvd": 1.2}
    assert challenger.digest != BASELINE.digest


def test_a_learned_parent_does_not_grow_a_version_chain() -> None:
    assert proposal_version("1.0.0-learn.202609141200", "202609150600") == "1.0.0-learn.202609150600"
