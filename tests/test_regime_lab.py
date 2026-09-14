import unittest
from pathlib import Path

from tradesync_core.market_features import load_catalog
from tradesync_core import regime_lab
from tradesync_core.regime_lab import (
    RegimeLabValidationError,
    aggregate_feature_evidence,
    build_challenger_rulebook,
    challenger_rulebook,
)
from tradesync_core.regime_weights import load_rulebook


ROOT = Path(__file__).resolve().parents[1]
REPLAY_WEIGHTS = {
    "price_volatility": 0.40,
    "liquidity": 0.15,
    "positioning": 0.20,
    "spot_premium": 0.15,
    "macro_flows": 0.10,
}


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

    def test_a_replay_challenger_needs_weights_and_a_version_but_no_hypothesis(self):
        challenger = challenger_rulebook(self.baseline, REPLAY_WEIGHTS, "replay-1")
        self.assertEqual(challenger.weights["price_volatility"], 0.40)
        self.assertEqual(challenger.data["status"], "draft")
        self.assertEqual(challenger.data["purpose"], self.baseline.data["purpose"])
        partial = {k: v for k, v in REPLAY_WEIGHTS.items() if k != "macro_flows"}
        with self.assertRaisesRegex(RegimeLabValidationError, "missing blocks: macro_flows"):
            challenger_rulebook(self.baseline, partial, "replay-1")
        with self.assertRaisesRegex(RegimeLabValidationError, "version is required"):
            challenger_rulebook(self.baseline, REPLAY_WEIGHTS, " ")

    def test_a_saved_challenger_still_needs_a_hypothesis(self):
        with self.assertRaisesRegex(RegimeLabValidationError, "hypothesis"):
            build_challenger_rulebook(self.baseline, REPLAY_WEIGHTS, "saved-1", "too short")
        saved = build_challenger_rulebook(
            self.baseline, REPLAY_WEIGHTS, "saved-1", "More price weight should admit more trending setups."
        )
        self.assertEqual(saved.data["purpose"], "More price weight should admit more trending setups.")

    def test_challengers_are_judged_by_replay_not_a_snapshot_comparison(self):
        self.assertFalse(hasattr(regime_lab, "assess_learning_gate"))
        self.assertFalse(hasattr(regime_lab, "compare_experiment"))


if __name__ == "__main__":
    unittest.main()
