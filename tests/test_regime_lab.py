import unittest
from pathlib import Path

from tradesync_core.market_features import load_catalog
from tradesync_core.regime_lab import (
    RegimeLabValidationError,
    aggregate_feature_evidence,
    assess_learning_gate,
    build_challenger_rulebook,
    compare_experiment,
)
from tradesync_core.regime_weights import load_rulebook


ROOT = Path(__file__).resolve().parents[1]


class RegimeLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(
            ROOT / "config/features/market-feature-catalog-v1.json"
        )
        cls.baseline = load_rulebook(ROOT / "config/regime/regime-rulebook-v1.json")

    def test_aggregates_only_admitted_generic_feature_scores(self):
        results = [
            {
                "feature_id": "hl_spread_bps",
                "score": -0.4,
                "data_quality": 0.5,
                "scoring_allowed": True,
            },
            {
                "feature_id": "hl_depth_25bp_usd",
                "score": 0.2,
                "data_quality": 1.0,
                "scoring_allowed": True,
            },
            {
                "feature_id": "hl_funding_hourly_rate",
                "score": 0.9,
                "data_quality": 1.0,
                "scoring_allowed": True,
            },
        ]
        evidence = aggregate_feature_evidence(self.catalog, self.baseline, results)
        self.assertAlmostEqual(evidence.block_scores["liquidity"], 0.0)
        self.assertAlmostEqual(evidence.data_quality["liquidity"], 0.375)
        self.assertNotIn("positioning", evidence.block_scores)
        self.assertEqual(evidence.blocks["positioning"]["status"], "unavailable")

    def test_valid_challenger_is_a_new_draft(self):
        weights = {
            "price_volatility": 0.25,
            "liquidity": 0.35,
            "positioning": 0.20,
            "spot_premium": 0.10,
            "macro_flows": 0.10,
        }
        challenger = build_challenger_rulebook(
            self.baseline,
            weights,
            "1.0.0-test",
            "Increasing liquidity emphasis should reduce fragile paper setups.",
        )
        self.assertEqual(challenger.data["status"], "draft")
        self.assertEqual(challenger.data["environment"], "paper")
        self.assertEqual(challenger.weights["liquidity"], 0.35)
        self.assertNotEqual(challenger.digest, self.baseline.digest)

    def test_invalid_weight_sum_is_rejected(self):
        with self.assertRaises(RegimeLabValidationError):
            build_challenger_rulebook(
                self.baseline,
                {name: 0.1 for name in self.baseline.weights},
                "bad",
                "This hypothesis is long enough but its weights are invalid.",
            )

    def test_learning_gate_checks_math_but_not_prose_correctness(self):
        gate = assess_learning_gate(
            1.0,
            "Coverage measures available evidence, not the chance a trade wins.",
        )
        self.assertTrue(gate["complete"])
        self.assertEqual(gate["reflection_review"], "operator_review_required")
        self.assertFalse(assess_learning_gate(100, "long enough reflection text")["complete"])

    def test_comparison_uses_same_evidence_and_has_no_activation_authority(self):
        challenger = build_challenger_rulebook(
            self.baseline,
            {
                "price_volatility": 0.25,
                "liquidity": 0.35,
                "positioning": 0.20,
                "spot_premium": 0.10,
                "macro_flows": 0.10,
            },
            "1.0.0-test",
            "Increasing liquidity emphasis should reduce fragile paper setups.",
        )
        evidence = aggregate_feature_evidence(
            self.catalog,
            self.baseline,
            [{
                "feature_id": "hl_spread_bps",
                "score": -0.5,
                "data_quality": 1.0,
                "scoring_allowed": True,
            }],
        )
        result = compare_experiment(self.baseline, challenger, evidence)
        self.assertTrue(result["same_market_evidence"])
        self.assertFalse(result["activation_authority"])
        self.assertEqual(result["baseline"]["paper_risk_multiplier"], 0.5)


if __name__ == "__main__":
    unittest.main()
