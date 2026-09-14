"""A challenger is judged by what it changes on the same recorded decisions."""

import json
import unittest
from pathlib import Path

from tradesync_core.paper_signal import AdmissionPolicy, PaperSignalDecision
from tradesync_core.regime_weights import validate_rulebook
from tradesync_core.replay import case_from_stored_evidence
from tradesync_core.replay_judgement import classify_change, judge_window

ROOT = Path(__file__).resolve().parents[1]
RULEBOOK_PATH = ROOT / "config" / "regime" / "regime-rulebook-v1.json"
CATALOG = {"catalog_id": "tradesync-hyperliquid-market-features", "version": "1.3.0", "digest": "d"}
NOW_MS = 1_788_800_000_000
# Weight moved onto blocks that recorded nothing: coverage falls below the emit floor.
EMPTY_BLOCKS = dict(price_volatility=0.10, liquidity=0.10, positioning=0.40, spot_premium=0.30, macro_flows=0.10)


def _rulebook(**weights):
    data = json.loads(RULEBOOK_PATH.read_text(encoding="utf-8-sig"))
    if weights:
        for block, value in weights.items():
            data["blocks"][block]["weight"] = value
        data["version"] = "test-challenger"
    return validate_rulebook(data)


def _case(signal_id, directional=0.6, price_quality=1.0, liquidity_quality=0.5, outcome=1.0, at_ms=NOW_MS):
    stored = {
        "evidence": {
            "evaluated_at_ms": at_ms,
            "contributions": {
                "price_volatility": {"score": 0.5, "quality": price_quality},
                "liquidity": {"score": -0.2, "quality": liquidity_quality},
            },
            "directional": {
                "score": directional,
                "coverage": 1.0,
                "contributors": [{"feature_id": "hl_return_1h_pct", "score": directional, "quality": 1.0}],
            },
        }
    }
    return case_from_stored_evidence(
        signal_id, "BTC-PERP", stored,
        outcome_signed_return_pct=outcome, market_move_pct=outcome,
    )


def _decision(admitted, direction):
    return PaperSignalDecision(
        admitted=admitted, symbol="BTC-PERP", direction=direction, weighted_score=0.1,
        data_coverage=0.5, directional_score=0.3, directional_coverage=1.0,
        paper_risk_multiplier=1.0, evidence_digest="x",
    )


class ClassifyChangeTests(unittest.TestCase):
    def test_each_kind_of_change_is_named(self):
        self.assertIsNone(classify_change(_decision(True, "LONG"), _decision(True, "LONG")))
        self.assertIsNone(classify_change(_decision(False, "NONE"), _decision(False, "NONE")))
        self.assertEqual(classify_change(_decision(False, "NONE"), _decision(True, "LONG")), "admissions_gained")
        self.assertEqual(classify_change(_decision(True, "SHORT"), _decision(False, "NONE")), "admissions_lost")
        self.assertEqual(classify_change(_decision(True, "LONG"), _decision(True, "SHORT")), "direction_flips")


class JudgeWindowTests(unittest.TestCase):
    def test_identical_rulebooks_change_nothing(self):
        cases = [_case("a"), _case("b", directional=-0.6, outcome=-1.0)]
        result = judge_window(cases, _rulebook(), _rulebook(), AdmissionPolicy(), CATALOG)
        self.assertEqual(result["decisions"], {
            "replayed": 2, "changed": 0, "admissions_gained": 0, "admissions_lost": 0, "direction_flips": 0,
        })
        self.assertEqual(result["baseline"]["admitted"], result["challenger"]["admitted"])
        self.assertEqual(result["outcomes"]["delta"], {"hit_rate": 0.0, "skill": 0.0, "mean_signed_return_pct": 0.0})
        self.assertEqual(result["changed_examples"], [])

    def test_weight_on_empty_blocks_loses_admissions_and_their_outcomes(self):
        # Baseline coverage 0.30 x 1.0 + 0.25 x 0.5 = 0.425; challenger 0.10 + 0.05 = 0.15.
        cases = [_case("a"), _case("b")]
        result = judge_window(cases, _rulebook(), _rulebook(**EMPTY_BLOCKS), AdmissionPolicy(), CATALOG)
        self.assertEqual(result["decisions"]["admissions_lost"], 2)
        self.assertEqual(result["decisions"]["direction_flips"], 0)
        outcomes = result["outcomes"]
        self.assertEqual(outcomes["cases_with_outcome"], 2)
        self.assertEqual(outcomes["baseline"]["admitted_with_outcome"], 2)
        self.assertEqual(outcomes["baseline"]["hit_rate"], 1.0)
        self.assertEqual(outcomes["challenger"]["admitted_with_outcome"], 0)
        self.assertIsNone(outcomes["challenger"]["hit_rate"])
        self.assertIsNone(outcomes["delta"]["hit_rate"])
        example = result["changed_examples"][0]
        self.assertEqual((example["baseline"], example["challenger"]), ("LONG", "NONE"))
        self.assertGreater(example["baseline_coverage"], example["challenger_coverage"])

    def test_a_gained_admission_without_an_outcome_is_counted_but_not_scored(self):
        # Only price_volatility recorded: 0.30 x 0.8 = 0.24 is below the 0.30 emit floor; 0.40 x 0.8 = 0.32 is not.
        case = _case("gain", price_quality=0.8, liquidity_quality=0.0, outcome=None)
        heavier = _rulebook(price_volatility=0.40, liquidity=0.15, positioning=0.20, spot_premium=0.15, macro_flows=0.10)
        result = judge_window([case], _rulebook(), heavier, AdmissionPolicy(), CATALOG)
        self.assertEqual(result["decisions"]["admissions_gained"], 1)
        self.assertEqual((result["baseline"]["admitted"], result["challenger"]["admitted"]), (0, 1))
        self.assertEqual(result["outcomes"]["cases_with_outcome"], 0)
        self.assertEqual(result["outcomes"]["challenger"]["admitted_with_outcome"], 0)
        self.assertFalse(result["changed_examples"][0]["has_outcome"])

    def test_a_sample_limits_decision_counts_but_every_outcome_is_scored(self):
        cases = [_case("sampled"), _case("unsampled")]
        result = judge_window(
            cases, _rulebook(), _rulebook(**EMPTY_BLOCKS), AdmissionPolicy(), CATALOG, sampled_ids={"sampled"},
        )
        self.assertEqual(result["decisions"]["replayed"], 1)
        self.assertEqual(result["decisions"]["admissions_lost"], 1)
        self.assertEqual(result["outcomes"]["cases_with_outcome"], 2)
        self.assertEqual(result["outcomes"]["baseline"]["admitted_with_outcome"], 2)

    def test_examples_are_newest_first_and_capped(self):
        cases = [_case(f"s{i}", at_ms=NOW_MS + i) for i in range(3)]
        result = judge_window(
            cases, _rulebook(), _rulebook(**EMPTY_BLOCKS), AdmissionPolicy(), CATALOG, example_limit=2,
        )
        self.assertEqual([e["signal_id"] for e in result["changed_examples"]], ["s2", "s1"])

    def test_skill_is_hit_rate_minus_what_the_direction_mix_scores_by_luck(self):
        cases = [_case(f"s{i}") for i in range(4)]  # every call LONG in a rising window
        result = judge_window(cases, _rulebook(), _rulebook(), AdmissionPolicy(), CATALOG)
        side = result["outcomes"]["baseline"]
        self.assertEqual((side["hit_rate"], side["expected_hit_rate"], side["skill"]), (1.0, 1.0, 0.0))
        self.assertIn("cannot show", result["note"])

    def test_an_empty_window_has_zero_counts_and_no_rates(self):
        result = judge_window([], _rulebook(), _rulebook(**EMPTY_BLOCKS), AdmissionPolicy(), CATALOG)
        self.assertEqual(result["decisions"]["replayed"], 0)
        self.assertIsNone(result["outcomes"]["challenger"]["hit_rate"])


if __name__ == "__main__":
    unittest.main()
