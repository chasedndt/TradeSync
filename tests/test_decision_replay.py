"""Replaying a stored decision reproduces production and applies a rulebook's feature weights."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from learning_fixtures import POLICY, stored_decision  # noqa: E402

from tradesync_core.decision_replay import policy_from_stored, replay_decision  # noqa: E402
from tradesync_core.market_features import load_catalog  # noqa: E402
from tradesync_core.paper_signal import decide_paper_signal  # noqa: E402
from tradesync_core.regime_weights import load_rulebook, validate_rulebook  # noqa: E402
from tradesync_core.replay import ReplayError  # noqa: E402
from tradesync_core.rulebook_evidence import evaluate_rulebook_evidence  # noqa: E402

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


def test_baseline_replay_reproduces_a_decision_the_live_path_admitted() -> None:
    evaluation, directional = evaluate_rulebook_evidence(CATALOG, BASELINE, RESULTS)
    catalog = {"catalog_id": CATALOG.data["catalog_id"], "version": CATALOG.version, "digest": CATALOG.digest}
    live = decide_paper_signal("BTC-PERP", evaluation, RESULTS, catalog, NOW_MS, directional=directional)
    assert live.admitted and live.direction == "LONG"
    replayed = replay_decision("sig-1", "BTC-PERP", live.to_dict(), BASELINE)
    assert (replayed.admitted, replayed.direction) == (True, "LONG")


def test_a_feature_weight_can_flip_a_replayed_call() -> None:
    stored = stored_decision(ret=0.9, cvd=-0.5)  # (0.9 - 0.5) / 2 = +0.2 -> LONG
    assert replay_decision("opp", "BTC-PERP", stored, BASELINE).direction == "LONG"
    flipped = replay_decision("opp", "BTC-PERP", stored, rulebook_with({"hl_direct_cvd": 4.0}))
    assert flipped.admitted and flipped.direction == "SHORT"  # (0.9 - 2.0) / 5 = -0.22


def test_the_recorded_policy_is_the_one_replayed() -> None:
    strict = {**POLICY, "minimum_coverage_to_emit": 0.9}
    replayed = replay_decision("opp", "BTC-PERP", stored_decision(policy=strict), BASELINE)
    assert not replayed.admitted
    assert "coverage_below_emit_floor" in {reason["code"] for reason in replayed.rejection_reasons}


def test_a_decision_from_before_directional_evidence_is_unreplayable() -> None:
    stored = stored_decision()
    stored["evidence"]["directional"] = None
    with pytest.raises(ReplayError):
        replay_decision("old", "BTC-PERP", stored, BASELINE)


def test_absent_thresholds_replay_as_the_rule_of_that_day() -> None:
    old = {k: v for k, v in POLICY.items() if k not in ("direction_enter_threshold", "minimum_directional_coverage")}
    policy = policy_from_stored(stored_decision(policy=old))
    assert policy.direction_enter_threshold == policy.direction_deadband == 0.05
    assert policy.minimum_directional_coverage == 0.0
