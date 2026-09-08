"""Outcome measurement tests.

The point of this module is to tell the operator whether recorded paper calls
were any good. It must refuse to guess: a window that has not closed, or one
with a hole in its candle coverage, is reported as such rather than scored.
"""

import unittest

from tradesync_core.outcomes import (
    OutcomeError,
    measure_horizon,
    measure_opportunity,
    summarise,
)

OPEN_S = 1_788_800_000
MIN = 60


def _candles(count, start=OPEN_S, step=MIN, open_=100.0, drift=0.0, high_pad=1.0, low_pad=1.0):
    out = []
    price = open_
    for i in range(count):
        out.append(
            {
                "time": start + i * step,
                "open": price,
                "high": price + high_pad,
                "low": price - low_pad,
                "close": price + drift,
                "volume": 1.0,
            }
        )
        price += drift
    return out


class MeasureHorizonTests(unittest.TestCase):
    def test_a_long_that_rose_is_positive(self):
        candles = _candles(16, drift=1.0)
        out = measure_horizon(candles, OPEN_S, "LONG", 15, now_s=OPEN_S + 3600)
        self.assertEqual(out.status, "measured")
        self.assertGreater(out.signed_return_pct, 0)
        self.assertEqual(out.forward_return_pct, out.signed_return_pct)

    def test_a_short_that_fell_is_positive(self):
        """A SHORT is right when price falls, so its signed return is positive."""
        candles = _candles(16, drift=-1.0)
        out = measure_horizon(candles, OPEN_S, "SHORT", 15, now_s=OPEN_S + 3600)
        self.assertEqual(out.status, "measured")
        self.assertLess(out.forward_return_pct, 0)
        self.assertGreater(out.signed_return_pct, 0)

    def test_a_short_that_rose_is_negative(self):
        candles = _candles(16, drift=1.0)
        out = measure_horizon(candles, OPEN_S, "SHORT", 15, now_s=OPEN_S + 3600)
        self.assertLess(out.signed_return_pct, 0)

    def test_excursions_are_relative_to_the_side_called(self):
        candles = _candles(16, drift=0.0, high_pad=5.0, low_pad=3.0)
        long_out = measure_horizon(candles, OPEN_S, "LONG", 15, now_s=OPEN_S + 3600)
        short_out = measure_horizon(candles, OPEN_S, "SHORT", 15, now_s=OPEN_S + 3600)
        # A rise favours the long and hurts the short.
        self.assertAlmostEqual(long_out.max_favourable_pct, 5.0, places=4)
        self.assertAlmostEqual(long_out.max_adverse_pct, 3.0, places=4)
        self.assertAlmostEqual(short_out.max_favourable_pct, 3.0, places=4)
        self.assertAlmostEqual(short_out.max_adverse_pct, 5.0, places=4)

    def test_an_open_horizon_is_pending_not_measured_early(self):
        candles = _candles(5)
        out = measure_horizon(candles, OPEN_S, "LONG", 60, now_s=OPEN_S + 300)
        self.assertEqual(out.status, "pending")
        self.assertIsNone(out.signed_return_pct)
        self.assertIn("not measured early", out.reason)

    def test_a_gap_is_reported_not_interpolated(self):
        # Two candles an hour apart: the window is not actually covered.
        candles = [
            {"time": OPEN_S, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
            {"time": OPEN_S + 120, "open": 100.0, "high": 101.0, "low": 99.0, "close": 105.0},
        ]
        out = measure_horizon(candles, OPEN_S, "LONG", 60, now_s=OPEN_S + 7200)
        self.assertEqual(out.status, "insufficient_candles")
        self.assertIn("interpolated", out.reason)

    def test_no_candles_is_reported(self):
        out = measure_horizon([], OPEN_S, "LONG", 15, now_s=OPEN_S + 3600)
        self.assertEqual(out.status, "insufficient_candles")

    def test_candles_before_the_decision_are_never_used(self):
        """The entry must not be a price that existed before the call."""
        before = _candles(10, start=OPEN_S - 10 * MIN, open_=500.0)
        after = _candles(16, start=OPEN_S, open_=100.0, drift=1.0)
        out = measure_horizon(before + after, OPEN_S, "LONG", 15, now_s=OPEN_S + 3600)
        self.assertEqual(out.entry_price, 100.0)

    def test_a_direction_of_none_has_no_measurable_side(self):
        with self.assertRaises(OutcomeError):
            measure_horizon(_candles(16), OPEN_S, "NONE", 15, now_s=OPEN_S + 3600)

    def test_non_positive_horizon_is_rejected(self):
        with self.assertRaises(OutcomeError):
            measure_horizon(_candles(16), OPEN_S, "LONG", 0, now_s=OPEN_S + 3600)


class MeasureOpportunityTests(unittest.TestCase):
    def test_every_horizon_is_reported_even_when_pending(self):
        candles = _candles(20, drift=1.0)
        outcome = measure_opportunity(
            "opp-1", "BTC-PERP", "LONG", OPEN_S, candles, now_s=OPEN_S + 20 * MIN
        )
        statuses = {h.horizon_minutes: h.status for h in outcome.horizons}
        self.assertEqual(statuses[15], "measured")
        self.assertEqual(statuses[60], "pending")
        self.assertEqual(statuses[240], "pending")

    def test_payload_states_that_no_position_existed(self):
        outcome = measure_opportunity(
            "opp-1", "BTC-PERP", "LONG", OPEN_S, _candles(20), now_s=OPEN_S + 7200
        )
        self.assertIn("No order was placed", outcome.to_dict()["note"])

    def test_missing_id_is_rejected(self):
        with self.assertRaises(OutcomeError):
            measure_opportunity("", "BTC-PERP", "LONG", OPEN_S, [], now_s=OPEN_S)


class SummariseTests(unittest.TestCase):
    def _make(self, direction, drift):
        return measure_opportunity(
            f"opp-{direction}-{drift}", "BTC-PERP", direction, OPEN_S,
            _candles(16, drift=drift), now_s=OPEN_S + 7200,
        )

    def test_hit_rate_counts_measured_calls_only(self):
        outcomes = [
            self._make("LONG", 1.0),    # right
            self._make("LONG", -1.0),   # wrong
            self._make("SHORT", -1.0),  # right
        ]
        summary = summarise(outcomes, 15)
        self.assertEqual(summary["measured"], 3)
        self.assertAlmostEqual(summary["hit_rate"], 2 / 3, places=6)

    def test_an_empty_sample_reports_none_rather_than_zero(self):
        summary = summarise([], 15)
        self.assertEqual(summary["measured"], 0)
        self.assertIsNone(summary["hit_rate"])

    def test_summary_refuses_to_imply_an_edge(self):
        summary = summarise([self._make("LONG", 1.0)], 15)
        note = summary["note"].lower()
        self.assertIn("cannot demonstrate skill", note)
        self.assertIn("expected_hit_rate", note)

    def test_pending_horizons_are_excluded_from_the_record(self):
        partial = measure_opportunity(
            "opp-x", "BTC-PERP", "LONG", OPEN_S, _candles(20, drift=1.0),
            now_s=OPEN_S + 20 * MIN,
        )
        self.assertEqual(summarise([partial], 240)["measured"], 0)


if __name__ == "__main__":
    unittest.main()


class BaselineTests(unittest.TestCase):
    """A hit rate means nothing without the base rate the market set."""

    def test_always_long_in_a_rising_market_shows_no_skill(self):
        from tradesync_core.outcomes import expected_hit_rate

        # Market rose in 100% of windows; a permanent LONG "wins" every time.
        self.assertEqual(expected_hit_rate(market_up_rate=1.0, long_share=1.0), 1.0)

    def test_always_short_in_a_falling_market_shows_no_skill(self):
        from tradesync_core.outcomes import expected_hit_rate

        # This is the trap the 2026-09-08 sample fell into: 66.7% for SHORT
        # calls looked like ability and was only the market falling.
        self.assertEqual(expected_hit_rate(market_up_rate=0.0, long_share=0.0), 1.0)

    def test_a_coin_flip_market_gives_a_coin_flip_baseline(self):
        from tradesync_core.outcomes import expected_hit_rate

        self.assertAlmostEqual(
            expected_hit_rate(market_up_rate=0.5, long_share=0.7), 0.5, places=9
        )

    def test_summary_reports_skill_as_hit_rate_minus_baseline(self):
        # Every call LONG, market rose every time: hit rate 100%, but the
        # baseline is also 100%, so skill is zero.
        outcomes = [
            measure_opportunity(
                f"opp-{i}", "BTC-PERP", "LONG", OPEN_S,
                _candles(16, drift=1.0), now_s=OPEN_S + 7200,
            )
            for i in range(4)
        ]
        summary = summarise(outcomes, 15)
        self.assertEqual(summary["hit_rate"], 1.0)
        self.assertEqual(summary["market_up_rate"], 1.0)
        self.assertEqual(summary["expected_hit_rate"], 1.0)
        self.assertEqual(summary["skill_vs_baseline"], 0.0)

    def test_summary_warns_that_hit_rate_alone_is_not_interpretable(self):
        summary = summarise(
            [measure_opportunity("o", "BTC-PERP", "LONG", OPEN_S,
                                 _candles(16, drift=1.0), now_s=OPEN_S + 7200)],
            15,
        )
        self.assertIn("not interpretable alone", summary["note"])

    def test_empty_sample_reports_no_baseline_rather_than_zero(self):
        summary = summarise([], 60)
        self.assertIsNone(summary["expected_hit_rate"])
        self.assertIsNone(summary["skill_vs_baseline"])
