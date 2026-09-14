"""Per-feature rulebook weights: absent means unchanged; present moves scores, never coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradesync_core.feature_weights import weighted_mean
from tradesync_core.market_features import load_catalog
from tradesync_core.regime_lab import aggregate_directional_evidence, aggregate_feature_evidence
from tradesync_core.regime_weights import (
    RulebookValidationError,
    diff_rulebooks,
    evaluate_blocks,
    load_rulebook,
    validate_rulebook,
)
from tradesync_core.rulebook_evidence import evaluate_rulebook_evidence

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT / "config" / "features" / "market-feature-catalog-v1.json")
BASELINE = load_rulebook(ROOT / "config" / "regime" / "regime-rulebook-v1.json")
NOW_MS = 1_788_800_000_000
RESULTS = [
    {"feature_id": "hl_return_1h_pct", "block": "price_volatility", "score": 0.4, "data_quality": 1.0,
     "scoring_allowed": True, "provenance": "derived", "observed_at_ms": NOW_MS},
    {"feature_id": "hl_direct_cvd", "block": "price_volatility", "score": 0.3, "data_quality": 1.0,
     "scoring_allowed": True, "provenance": "observed", "observed_at_ms": NOW_MS},
    {"feature_id": "hl_spread_bps", "block": "liquidity", "score": -0.2, "data_quality": 1.0,
     "scoring_allowed": True, "provenance": "derived", "observed_at_ms": NOW_MS},
]


def rulebook_with(feature_weights):
    data = json.loads(json.dumps(BASELINE.data))
    data["feature_weights"] = feature_weights
    data["version"] = "test-weights"
    return validate_rulebook(data)


def test_the_rulebook_file_has_no_feature_weights() -> None:
    assert BASELINE.feature_weights == {}


def test_aggregation_without_feature_weights_is_byte_for_byte_unchanged() -> None:
    plain = aggregate_directional_evidence(CATALOG, RESULTS).to_dict()
    assert aggregate_directional_evidence(CATALOG, RESULTS, {}).to_dict() == plain
    assert all("weight" not in c for c in plain["contributors"])
    assert plain["score"] == pytest.approx(0.35)


def test_feature_weights_move_the_score_but_not_coverage() -> None:
    plain = aggregate_directional_evidence(CATALOG, RESULTS)
    weighted = aggregate_directional_evidence(CATALOG, RESULTS, {"hl_direct_cvd": 3.0})
    assert weighted.score == pytest.approx((0.4 + 3 * 0.3) / 4)
    assert weighted.coverage == plain.coverage
    assert {c["feature_id"]: c.get("weight") for c in weighted.contributors}["hl_direct_cvd"] == 3.0
    blocks = aggregate_feature_evidence(CATALOG, rulebook_with({"hl_direct_cvd": 3.0}), RESULTS)
    assert blocks.block_scores["price_volatility"] == pytest.approx((0.4 + 0.9) / 4)
    assert blocks.data_quality == aggregate_feature_evidence(CATALOG, BASELINE, RESULTS).data_quality


def test_the_shared_evaluation_is_the_regime_lab_composition() -> None:
    evaluation, directional = evaluate_rulebook_evidence(CATALOG, BASELINE, RESULTS)
    evidence = aggregate_feature_evidence(CATALOG, BASELINE, RESULTS)
    assert evaluation == evaluate_blocks(BASELINE, evidence.block_scores, evidence.data_quality, [])
    assert directional == aggregate_directional_evidence(CATALOG, RESULTS).to_dict()


def test_an_adopted_rulebook_is_evaluated_with_its_own_weights() -> None:
    adopted = rulebook_with({"hl_return_1h_pct": 0.5})
    evaluation, directional = evaluate_rulebook_evidence(CATALOG, adopted, RESULTS)
    assert evaluation["config_digest"] == adopted.digest
    assert directional["score"] == pytest.approx((0.5 * 0.4 + 0.3) / 1.5)


def test_rulebook_diffs_report_feature_weight_changes() -> None:
    diff = diff_rulebooks(BASELINE, rulebook_with({"hl_direct_cvd": 1.2}))
    assert diff["feature_weight_changes"] == {"hl_direct_cvd": {"before": 1.0, "after": 1.2}}


def test_a_weighted_mean_with_nothing_weighted_has_no_value() -> None:
    assert weighted_mean([]) is None
    assert weighted_mean([(0.5, 0.0, 1.0)]) is None
    assert weighted_mean([(0.5, 1.0, 1.0), (-0.5, 1.0, 3.0)]) == pytest.approx(-0.25)


@pytest.mark.parametrize("bad", [{"hl_direct_cvd": 0}, {"hl_direct_cvd": -1}, {"hl_direct_cvd": 5}, {"hl_direct_cvd": "2"}, []])
def test_rulebooks_refuse_malformed_feature_weights(bad) -> None:
    data = json.loads(json.dumps(BASELINE.data))
    data["feature_weights"] = bad
    with pytest.raises(RulebookValidationError):
        validate_rulebook(data)
