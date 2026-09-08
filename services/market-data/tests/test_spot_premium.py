"""Spot premium tests.

The premium compares two venues sampled at different moments. Its correctness
rests mostly on refusing to compute one when the comparison is not supportable.
"""

import pytest

from app.spot_premium import (
    MAX_ALIGNMENT_SKEW_MS,
    coinbase_product_for,
    premium_bps,
    spot_mid,
)

T0 = 1_788_855_000_000


class TestSpotMid:
    def test_mid_is_the_midpoint_of_the_book(self):
        assert spot_mid({"bid": "100", "ask": "102"}) == pytest.approx(101.0)

    def test_the_last_trade_is_not_used(self):
        """A single print sits on one side of the spread; the mid does not."""
        mid = spot_mid({"bid": "100", "ask": "102", "price": "100"})
        assert mid == pytest.approx(101.0)

    def test_malformed_or_crossed_books_are_refused(self):
        assert spot_mid({}) is None
        assert spot_mid({"bid": "abc", "ask": "102"}) is None
        assert spot_mid({"bid": "0", "ask": "102"}) is None
        # A crossed book is not a tradeable quote.
        assert spot_mid({"bid": "103", "ask": "102"}) is None


class TestPremium:
    def test_spot_above_perp_is_a_positive_premium(self):
        result = premium_bps(101.0, 100.0, T0, T0)
        assert result["value_bps"] == pytest.approx(100.0)

    def test_spot_below_perp_is_negative(self):
        result = premium_bps(99.0, 100.0, T0, T0)
        assert result["value_bps"] == pytest.approx(-100.0)

    def test_misaligned_samples_are_refused_not_reported(self):
        """Sampling lag must not be presented as market structure."""
        assert premium_bps(101.0, 100.0, T0, T0 + MAX_ALIGNMENT_SKEW_MS + 1) is None

    def test_the_bound_matches_the_catalog_freshness_for_this_feature(self):
        """One standard, not two. A stricter local cutoff made the premium
        vanish from snapshots the catalog would have accepted as fresh."""
        import json
        from pathlib import Path

        catalog = json.loads(
            (Path(__file__).resolve().parents[3]
             / "config" / "features" / "market-feature-catalog-v1.json"
             ).read_text(encoding="utf-8-sig")
        )
        fresh = catalog["features"]["coinbase_premium_bps"]["fresh_after_ms"]
        assert MAX_ALIGNMENT_SKEW_MS == fresh

    def test_alignment_within_tolerance_is_accepted_and_recorded(self):
        result = premium_bps(101.0, 100.0, T0, T0 + 3_000)
        assert result["alignment_skew_ms"] == 3_000

    def test_non_positive_prices_are_refused(self):
        assert premium_bps(0.0, 100.0, T0, T0) is None
        assert premium_bps(101.0, 0.0, T0, T0) is None

    def test_every_observation_restates_that_it_is_context_only(self):
        result = premium_bps(101.0, 100.0, T0, T0)
        assert result["authority"] == "context_only"
        assert result["reference_venue"] == "coinbase"


class TestProductMapping:
    def test_listed_pairs_map_to_a_real_us_spot_product(self):
        assert coinbase_product_for("BTC-PERP") == "BTC-USD"
        assert coinbase_product_for("ETH-PERP") == "ETH-USD"

    def test_an_unlisted_symbol_maps_to_nothing_rather_than_a_guess(self):
        """A synthetic mapping would invent a premium for a pair with no spot."""
        assert coinbase_product_for("DOGE-PERP") is None
        assert coinbase_product_for("") is None
