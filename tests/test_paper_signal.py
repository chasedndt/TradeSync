"""Admission tests for the paper signal decision.

Every case here asserts a deterministic verdict from fixed evidence. A refusal
must explain itself, and identical evidence must produce an identical digest so
a replay cannot create a second opportunity.
"""

import unittest

from tradesync_core.paper_signal import (
    AdmissionPolicy,
    PaperSignalError,
    decide_paper_signal,
)

CATALOG = {
    "catalog_id": "tradesync-hyperliquid-market-features",
    "version": "1.2.0",
    "digest": "catalogdigest",
}

NOW_MS = 1_767_297_600_000


def _evaluation(score=0.42, coverage=0.55, risk=0.5, missing=None):
    return {
        "rulebook_id": "tradesync-intraday-regime",
        "rulebook_version": "1.0.0",
        "config_digest": "rulebookdigest",
        "weighted_score": score,
        "data_coverage": coverage,
        "paper_risk_multiplier": risk,
        "contributions": {"liquidity": {"weight": 0.25}},
        "missing_blocks": missing if missing is not None else ["macro_flows"],
        "risk_caps_applied": [{"flag": "low_data_coverage", "cap": 0.5, "known": True}],
        "calculation": "sum(weight * quality * score) / sum(weight * quality)",
    }


def _feature(
    feature_id="hl_return_1h_pct",
    block="price_volatility",
    provenance="derived",
    observed_at_ms=NOW_MS - 1_000,
    scoring_allowed=True,
    score=0.4,
):
    return {
        "feature_id": feature_id,
        "block": block,
        "provenance": provenance,
        "observed_at_ms": observed_at_ms,
        "scoring_allowed": scoring_allowed,
        "score": score,
        "data_quality": 0.9,
        "history_count": 168,
    }


def _directional(score=0.42, coverage=1.0):
    """Directional evidence, as aggregate_directional_evidence returns it."""
    return {
        "score": score,
        "coverage": coverage,
        "contributors": [
            {"feature_id": "hl_return_1h_pct", "score": score, "quality": coverage}
        ],
        "admitted_feature_ids": ["hl_return_1h_pct"],
        "ready_feature_ids": ["hl_return_1h_pct"],
    }


def _decide(evaluation=None, features=None, policy=None, now=NOW_MS, directional=-1,
            previous=None):
    return decide_paper_signal(
        symbol="BTC-PERP",
        evaluation=evaluation or _evaluation(),
        feature_results=features if features is not None else [_feature()],
        catalog_summary=CATALOG,
        evaluated_at_ms=now,
        policy=policy,
        directional=_directional() if directional == -1 else directional,
        previous_direction=previous,
    )


class PaperSignalAdmissionTests(unittest.TestCase):
    def test_sufficient_evidence_is_admitted_with_a_direction(self):
        decision = _decide()
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.direction, "LONG")
        self.assertEqual(decision.rejection_reasons, [])
        self.assertEqual(len(decision.contributing_features), 1)

    def test_direction_follows_directional_evidence_not_the_blended_score(self):
        """A negative suitability score must not imply SHORT."""
        decision = _decide(_evaluation(score=-0.42), directional=_directional(0.42))
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.direction, "LONG")

    def test_negative_directional_evidence_is_admitted_as_short(self):
        decision = _decide(directional=_directional(-0.42))
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.direction, "SHORT")

    def test_suitability_alone_can_never_set_a_direction(self):
        """Deep books make a market tradeable; they do not make it a buy."""
        decision = _decide(directional=None)
        self.assertFalse(decision.admitted)
        self.assertEqual(decision.direction, "NONE")
        self.assertIn(
            "no_directional_evidence",
            [r["code"] for r in decision.rejection_reasons],
        )

    def test_thin_directional_coverage_is_refused(self):
        decision = _decide(directional=_directional(0.42, coverage=0.2))
        self.assertFalse(decision.admitted)
        reason = next(
            r for r in decision.rejection_reasons
            if r["code"] == "directional_coverage_below_floor"
        )
        self.assertIn("hl_return_1h_pct", reason["detail"])

    def test_admitted_decision_never_claims_execution_authority(self):
        payload = _decide().to_dict()
        self.assertFalse(payload["execution_authority"])
        self.assertEqual(payload["mode"], "paper_shadow")

    def test_coverage_below_the_floor_refuses_and_names_missing_blocks(self):
        decision = _decide(
            _evaluation(coverage=0.0627875, missing=["positioning", "macro_flows"])
        )
        self.assertFalse(decision.admitted)
        self.assertEqual(decision.direction, "NONE")
        codes = [reason["code"] for reason in decision.rejection_reasons]
        self.assertIn("coverage_below_emit_floor", codes)
        detail = next(
            r["detail"]
            for r in decision.rejection_reasons
            if r["code"] == "coverage_below_emit_floor"
        )
        self.assertIn("positioning", detail)
        self.assertIn("macro_flows", detail)

    def test_missing_source_produces_an_explained_refusal_not_an_error(self):
        decision = _decide(_evaluation(score=0.0, coverage=0.0), features=[],
                           directional=None)
        self.assertFalse(decision.admitted)
        codes = [reason["code"] for reason in decision.rejection_reasons]
        self.assertIn("no_admitted_evidence", codes)
        self.assertIn("coverage_below_emit_floor", codes)

    def test_score_inside_the_deadband_is_not_a_weak_direction(self):
        decision = _decide(directional=_directional(0.01))
        self.assertFalse(decision.admitted)
        self.assertEqual(decision.direction, "NONE")
        self.assertIn(
            "score_inside_deadband",
            [reason["code"] for reason in decision.rejection_reasons],
        )

    def test_stale_evidence_is_rejected_with_its_measured_age(self):
        stale = _feature(observed_at_ms=NOW_MS - 600_000)
        decision = _decide(features=[stale])
        self.assertFalse(decision.admitted)
        reason = next(
            r for r in decision.rejection_reasons if r["code"] == "evidence_stale"
        )
        self.assertIn("600000 ms old", reason["detail"])
        self.assertEqual(reason["feature_id"], "hl_return_1h_pct")

    def test_future_timestamped_evidence_is_rejected(self):
        ahead = _feature(observed_at_ms=NOW_MS + 5_000)
        decision = _decide(features=[ahead])
        self.assertFalse(decision.admitted)
        self.assertIn(
            "evidence_timestamped_in_future",
            [reason["code"] for reason in decision.rejection_reasons],
        )

    def test_proxy_and_context_only_provenance_cannot_score(self):
        for provenance in ("proxy", "context_only", "unavailable"):
            with self.subTest(provenance=provenance):
                decision = _decide(features=[_feature(provenance=provenance)])
                self.assertFalse(decision.admitted)
                self.assertIn(
                    "inadmissible_provenance",
                    [r["code"] for r in decision.rejection_reasons],
                )

    def test_features_not_allowed_to_score_are_excluded_from_evidence(self):
        decision = _decide(features=[_feature(scoring_allowed=False)])
        self.assertEqual(decision.contributing_features, [])
        self.assertIn(
            "no_admitted_evidence",
            [reason["code"] for reason in decision.rejection_reasons],
        )

    def test_fully_capped_paper_risk_refuses_to_emit(self):
        decision = _decide(_evaluation(risk=0.0))
        self.assertFalse(decision.admitted)
        self.assertIn(
            "paper_risk_fully_capped",
            [reason["code"] for reason in decision.rejection_reasons],
        )


class PaperSignalReplayTests(unittest.TestCase):
    def test_identical_evidence_produces_an_identical_digest(self):
        first = _decide()
        second = _decide()
        self.assertEqual(first.evidence_digest, second.evidence_digest)

    def test_a_changed_observation_time_changes_the_digest(self):
        first = _decide()
        second = _decide(features=[_feature(observed_at_ms=NOW_MS - 2_000)])
        self.assertNotEqual(first.evidence_digest, second.evidence_digest)

    def test_a_changed_policy_changes_the_digest(self):
        first = _decide()
        second = _decide(policy=AdmissionPolicy(minimum_coverage_to_emit=0.4))
        self.assertNotEqual(first.evidence_digest, second.evidence_digest)

    def test_changed_directional_evidence_changes_the_digest(self):
        first = _decide()
        second = _decide(directional=_directional(0.41))
        self.assertNotEqual(first.evidence_digest, second.evidence_digest)

    def test_feature_order_does_not_change_the_digest(self):
        a = _feature("hl_return_1h_pct")
        b = _feature("hl_depth_25bp_usd", block="liquidity")
        first = _decide(features=[a, b])
        second = _decide(features=[b, a])
        self.assertEqual(first.evidence_digest, second.evidence_digest)


class PaperSignalEvidenceTests(unittest.TestCase):
    def test_evidence_records_both_configuration_versions_and_the_policy(self):
        evidence = _decide().evidence
        self.assertEqual(evidence["catalog_version"], "1.2.0")
        self.assertEqual(evidence["catalog_digest"], "catalogdigest")
        self.assertEqual(evidence["rulebook_digest"], "rulebookdigest")
        self.assertEqual(evidence["rulebook_version"], "1.0.0")
        self.assertEqual(evidence["evaluated_at_ms"], NOW_MS)
        self.assertEqual(evidence["policy"]["minimum_coverage_to_emit"], 0.30)

    def test_evidence_keeps_the_block_contributions_and_risk_caps(self):
        evidence = _decide().evidence
        self.assertIn("liquidity", evidence["contributions"])
        self.assertEqual(evidence["risk_caps_applied"][0]["flag"], "low_data_coverage")
        self.assertIn("sum(weight * quality * score)", evidence["calculation"])


class PaperSignalInputTests(unittest.TestCase):
    def test_missing_symbol_is_a_programming_error_not_a_refusal(self):
        with self.assertRaises(PaperSignalError):
            decide_paper_signal(
                symbol="",
                evaluation=_evaluation(),
                feature_results=[],
                catalog_summary=CATALOG,
                evaluated_at_ms=NOW_MS,
            )

    def test_non_numeric_evaluation_is_rejected(self):
        broken = _evaluation()
        broken["weighted_score"] = "high"
        with self.assertRaises(PaperSignalError):
            _decide(broken)


if __name__ == "__main__":
    unittest.main()


class DirectionHysteresisTests(unittest.TestCase):
    """A held side must be easier to keep than a reversal is to establish."""

    def test_a_new_direction_needs_the_entry_threshold(self):
        # 0.08 clears the 0.05 hold band but not the 0.15 entry band.
        decision = _decide(directional=_directional(0.08), previous=None)
        self.assertFalse(decision.admitted)
        reason = next(
            r for r in decision.rejection_reasons if r["code"] == "score_inside_deadband"
        )
        self.assertIn("entry", reason["detail"])

    def test_the_same_score_is_admitted_when_that_side_is_already_held(self):
        decision = _decide(directional=_directional(0.08), previous="LONG")
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.direction, "LONG")

    def test_a_reversal_must_clear_the_entry_threshold(self):
        """Holding LONG must not flip to SHORT on a marginal negative score."""
        decision = _decide(directional=_directional(-0.08), previous="LONG")
        self.assertFalse(decision.admitted)
        reason = next(
            r for r in decision.rejection_reasons if r["code"] == "score_inside_deadband"
        )
        self.assertIn("entry", reason["detail"])

    def test_a_decisive_reversal_is_still_admitted(self):
        decision = _decide(directional=_directional(-0.42), previous="LONG")
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.direction, "SHORT")

    def test_a_held_side_still_exits_below_the_hold_band(self):
        decision = _decide(directional=_directional(0.01), previous="LONG")
        self.assertFalse(decision.admitted)
        self.assertIn("hold", next(
            r["detail"] for r in decision.rejection_reasons
            if r["code"] == "score_inside_deadband"
        ))

    def test_previous_direction_is_bound_into_the_digest(self):
        a = _decide(directional=_directional(0.42), previous="LONG")
        b = _decide(directional=_directional(0.42), previous=None)
        self.assertNotEqual(a.evidence_digest, b.evidence_digest)


# --- direction hold window ---------------------------------------------------
#
# Loaded under the private alias: core-scorer packages its code as "app" like
# every other service.

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _service_import import load_service_module  # noqa: E402

_producer = load_service_module("core_scorer_app", "core-scorer", "paper_producer")


def test_the_hold_window_is_expressed_in_scoring_cycles() -> None:
    """A fixed duration would silently change stickiness when the cadence does.

    A held side is re-admitted every cycle for as long as it clears the hold
    threshold, so the bound that matters is "how many cycles of silence" — not
    "how many seconds".
    """
    assert _producer.direction_hold_max_age_seconds(60) == 60 * _producer.DIRECTION_HOLD_CYCLES
    assert _producer.direction_hold_max_age_seconds(15) == 15 * _producer.DIRECTION_HOLD_CYCLES
    # Halving the cadence halves the window; the cycle count is what is fixed.
    assert (
        _producer.direction_hold_max_age_seconds(30) * 2
        == _producer.direction_hold_max_age_seconds(60)
    )


def test_a_non_positive_cadence_is_refused() -> None:
    """It would make the hold window zero or negative, disabling hysteresis."""
    import pytest

    with pytest.raises(ValueError):
        _producer.direction_hold_max_age_seconds(0)
    with pytest.raises(ValueError):
        _producer.direction_hold_max_age_seconds(-60)
