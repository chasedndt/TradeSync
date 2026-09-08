import copy
import json
import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_LIBRARY = REPO_ROOT / "libs" / "tradesync_core"
sys.path.insert(0, os.fspath(CORE_LIBRARY))

from tradesync_core.market_features import (  # noqa: E402
    FeatureValidationError,
    freshness_factor,
    load_catalog,
    normalize_feature,
    ordinary_statistics,
    robust_statistics,
    validate_catalog,
    validate_rulebook_compatibility,
)
from tradesync_core.regime_weights import load_rulebook  # noqa: E402


CATALOG_PATH = REPO_ROOT / "config" / "features" / "market-feature-catalog-v1.json"
FIXTURE_PATH = REPO_ROOT / "fixtures" / "features" / "spread-robust-normalization.json"
RULEBOOK_PATH = REPO_ROOT / "config" / "regime" / "regime-rulebook-v1.json"


class MarketFeatureTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(CATALOG_PATH)

    def test_catalog_preserves_hyperliquid_and_paper_shadow_boundaries(self):
        self.assertEqual(self.catalog.data["venue"], "hyperliquid")
        self.assertEqual(self.catalog.data["status"], "paper_shadow")
        # A proxy may never score, whatever else changes.
        self.assertFalse(
            self.catalog.features["hl_liquidation_total_proxy_usd"][
                "scoring_eligible"
            ]
        )

    def test_an_external_venue_scores_only_as_a_price_reference(self):
        """Coinbase premium was admitted to scoring by operator decision.

        The boundary that must hold is narrower than "may it score": an
        external venue is a price reference, never the trading venue, and its
        authority must say so rather than borrowing the authoritative label.
        """
        feature = self.catalog.features["coinbase_premium_bps"]
        self.assertTrue(feature["scoring_eligible"])
        self.assertEqual(feature["source_authority"], "external_reference_venue")
        self.assertNotEqual(feature["source_authority"], "authoritative_market")
        # The catalog remains Hyperliquid's; Coinbase does not become a venue.
        self.assertEqual(self.catalog.data["venue"], "hyperliquid")

    def test_an_external_venue_still_cannot_score_on_proxy_provenance(self):
        invalid = copy.deepcopy(self.catalog.data)
        invalid["features"]["coinbase_premium_bps"]["provenance"] = "proxy"
        with self.assertRaisesRegex(FeatureValidationError, "scoring provenance"):
            validate_catalog(invalid)

    def test_scoring_proxy_is_rejected_by_catalog_validation(self):
        invalid = copy.deepcopy(self.catalog.data)
        invalid["features"]["hl_liquidation_total_proxy_usd"][
            "scoring_eligible"
        ] = True
        with self.assertRaisesRegex(FeatureValidationError, "scoring provenance"):
            validate_catalog(invalid)

    def test_catalog_is_compatible_and_exposes_uncovered_blocks(self):
        result = validate_rulebook_compatibility(
            self.catalog, load_rulebook(RULEBOOK_PATH)
        )
        self.assertTrue(result["compatible"])
        # spot_premium gained its first admitted feature on 2026-09-08, so the
        # only block still carrying weight with nothing behind it is macro_flows.
        self.assertEqual(result["uncovered_blocks"], ["macro_flows"])

    def test_ordinary_zscore_uses_sample_standard_deviation(self):
        result = ordinary_statistics([2.0, 4.0, 6.0], 8.0)
        self.assertAlmostEqual(result["center"], 4.0)
        self.assertAlmostEqual(result["dispersion"], 2.0)
        self.assertAlmostEqual(result["z_score"], 2.0)

    def test_robust_zscore_uses_scaled_mad(self):
        result = robust_statistics([1, 2, 3, 4, 5], 6)
        self.assertEqual(result["center"], 3)
        self.assertEqual(result["mad"], 1)
        self.assertAlmostEqual(result["dispersion"], 1.4826)
        self.assertAlmostEqual(result["z_score"], 3 / 1.4826)

    def test_freshness_factor_is_piecewise_linear(self):
        self.assertEqual(freshness_factor(1000, 2000, 5000), 1.0)
        self.assertEqual(freshness_factor(5000, 2000, 5000), 0.0)
        self.assertAlmostEqual(freshness_factor(3500, 2000, 5000), 0.5)

    def test_robust_spread_normalization_inverts_wider_spread(self):
        request = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        result = normalize_feature(self.catalog, request)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["normalization"]["method"], "robust_zscore")
        self.assertGreater(result["normalized_value"], 0)
        self.assertLess(result["score"], 0)
        self.assertTrue(result["scoring_allowed"])
        self.assertAlmostEqual(result["data_quality"], 20 / 120)

    def test_playbook_specific_feature_does_not_emit_generic_score(self):
        request = {
            "feature_id": "hl_funding_hourly_rate",
            "symbol": "BTC-PERP",
            "timeframe": "1h",
            "evaluated_at_ms": 101000,
            "current": {
                "ts": 100000,
                "value": 0.0002,
                "source_event_id": "evt-funding",
            },
            "history": [
                {"ts": index + 1, "value": 0.00001 * ((index % 7) - 3)}
                for index in range(30)
            ],
        }
        result = normalize_feature(self.catalog, request)
        self.assertEqual(result["status"], "ready")
        self.assertIsNotNone(result["normalized_value"])
        self.assertIsNone(result["score"])
        self.assertFalse(result["scoring_allowed"])

    def test_planned_feature_is_unavailable_even_with_values(self):
        request = {
            "feature_id": "verified_external_event_risk",
            "symbol": "BTC-PERP",
            "timeframe": "1h",
            "evaluated_at_ms": 1001,
            "current": {"ts": 1000, "value": 1.0, "source_event_id": "evt"},
            "history": [],
        }
        result = normalize_feature(self.catalog, request)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("planned", result["reason"])

    def test_admitted_return_feature_collects_history_instead_of_being_gated(self):
        """The one-hour return was promoted to implemented in catalog 1.1.0.

        It is the only price/volatility input the rulebook admits for a generic
        directional score, so a gated status here would silently cap coverage.
        """
        definition = self.catalog.features["hl_return_1h_pct"]
        self.assertEqual(definition["availability"], "implemented")
        self.assertTrue(definition["scoring_eligible"])
        self.assertEqual(definition["score_mode"], "direct")

        request = {
            "feature_id": "hl_return_1h_pct",
            "symbol": "BTC-PERP",
            "timeframe": "snapshot",
            "evaluated_at_ms": 1001,
            "current": {"ts": 1000, "value": 1.0, "source_event_id": "evt"},
            "history": [],
        }
        result = normalize_feature(self.catalog, request)
        self.assertEqual(result["status"], "collecting_history")
        self.assertFalse(result["scoring_allowed"])

    def test_insufficient_history_reports_collection_progress(self):
        request = {
            "feature_id": "hl_spread_bps",
            "symbol": "BTC-PERP",
            "timeframe": "snapshot",
            "evaluated_at_ms": 1001,
            "current": {"ts": 1000, "value": 1.0, "source_event_id": "evt"},
            "history": [
                {"ts": index + 1, "value": 0.5 + index} for index in range(8)
            ],
        }
        result = normalize_feature(self.catalog, request)
        self.assertEqual(result["status"], "collecting_history")
        self.assertEqual(result["history_count"], 8)
        self.assertFalse(result["scoring_allowed"])

    def test_future_history_is_rejected_to_prevent_lookahead(self):
        request = {
            "feature_id": "hl_spread_bps",
            "symbol": "BTC-PERP",
            "timeframe": "snapshot",
            "evaluated_at_ms": 1001,
            "current": {"ts": 1000, "value": 1.0, "source_event_id": "evt"},
            "history": [{"ts": 1000, "value": 0.5}],
        }
        with self.assertRaisesRegex(FeatureValidationError, "before current"):
            normalize_feature(self.catalog, request)

    def test_zero_dispersion_returns_unavailable_not_zero_score(self):
        request = {
            "feature_id": "hl_spread_bps",
            "symbol": "BTC-PERP",
            "timeframe": "snapshot",
            "evaluated_at_ms": 1001,
            "current": {"ts": 1000, "value": 1.0, "source_event_id": "evt"},
            "history": [{"ts": index, "value": 0.5} for index in range(20)],
        }
        result = normalize_feature(self.catalog, request)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("median absolute deviation is zero", result["reason"])


if __name__ == "__main__":
    unittest.main()
