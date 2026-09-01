import copy
import math
import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_LIBRARY = REPO_ROOT / "libs" / "tradesync_core"
sys.path.insert(0, os.fspath(CORE_LIBRARY))

from tradesync_core.regime_weights import (  # noqa: E402
    RulebookValidationError,
    bounded_z_score,
    evaluate_blocks,
    load_rulebook,
    validate_rulebook,
)


RULEBOOK_PATH = REPO_ROOT / "config" / "regime" / "regime-rulebook-v1.json"


class RegimeWeightTests(unittest.TestCase):
    def setUp(self):
        self.rulebook = load_rulebook(RULEBOOK_PATH)

    def test_rulebook_is_paper_only_and_weights_sum_to_one(self):
        self.assertEqual(self.rulebook.data["environment"], "paper")
        self.assertAlmostEqual(sum(self.rulebook.weights.values()), 1.0)

    def test_tanh_normalization_is_bounded_and_symmetric(self):
        self.assertEqual(bounded_z_score(0), 0.0)
        self.assertAlmostEqual(bounded_z_score(1), math.tanh(0.5))
        self.assertAlmostEqual(bounded_z_score(-2), -bounded_z_score(2))
        self.assertLess(bounded_z_score(1000), 1.0)
        self.assertGreater(bounded_z_score(-1000), -1.0)

    def test_documented_weight_example_scores_point_two_two(self):
        result = evaluate_blocks(
            self.rulebook,
            {
                "price_volatility": 0.8,
                "liquidity": -0.4,
                "positioning": 0.2,
                "spot_premium": 0.6,
                "macro_flows": -0.5,
            },
            {name: 1.0 for name in self.rulebook.weights},
        )
        self.assertAlmostEqual(result["weighted_score"], 0.22)
        self.assertAlmostEqual(result["data_coverage"], 1.0)
        self.assertAlmostEqual(result["paper_risk_multiplier"], 1.0)

    def test_quality_adjustment_renormalizes_available_evidence(self):
        result = evaluate_blocks(
            self.rulebook,
            {"price_volatility": 1.0, "liquidity": -1.0},
            {"price_volatility": 1.0, "liquidity": 0.5},
        )
        expected = (0.30 - 0.25 * 0.5) / (0.30 + 0.25 * 0.5)
        self.assertAlmostEqual(result["weighted_score"], expected)
        self.assertAlmostEqual(result["data_coverage"], 0.425)
        self.assertEqual(result["paper_risk_multiplier"], 0.5)

    def test_external_risk_caps_paper_budget_at_point_four_five(self):
        result = evaluate_blocks(
            self.rulebook,
            {name: 0.8 for name in self.rulebook.weights},
            {name: 1.0 for name in self.rulebook.weights},
            ["external_risk_high"],
        )
        self.assertAlmostEqual(result["weighted_score"], 0.8)
        self.assertAlmostEqual(result["paper_risk_multiplier"], 0.45)

    def test_unknown_risk_flag_fails_closed(self):
        result = evaluate_blocks(
            self.rulebook,
            {name: 0.0 for name in self.rulebook.weights},
            {name: 1.0 for name in self.rulebook.weights},
            ["not_in_the_rulebook"],
        )
        self.assertEqual(result["paper_risk_multiplier"], 0.0)
        self.assertFalse(result["risk_caps_applied"][0]["known"])

    def test_no_data_coverage_blocks_paper_risk(self):
        result = evaluate_blocks(self.rulebook, {}, {})
        self.assertEqual(result["data_coverage"], 0.0)
        self.assertEqual(result["weighted_score"], 0.0)
        self.assertEqual(result["paper_risk_multiplier"], 0.0)
        self.assertIn(
            "no_data_coverage",
            [item["flag"] for item in result["risk_caps_applied"]],
        )

    def test_invalid_weight_total_is_rejected(self):
        invalid = copy.deepcopy(self.rulebook.data)
        invalid["blocks"]["macro_flows"]["weight"] = 0.2
        with self.assertRaisesRegex(RulebookValidationError, "weights sum"):
            validate_rulebook(invalid)

    def test_scores_outside_minus_one_to_one_are_rejected(self):
        with self.assertRaisesRegex(RulebookValidationError, "between -1.0 and 1.0"):
            evaluate_blocks(self.rulebook, {"price_volatility": 1.1})


if __name__ == "__main__":
    unittest.main()
