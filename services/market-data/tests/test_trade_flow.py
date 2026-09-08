"""Trade flow / CVD tests.

The sign convention here decides the direction of every signal the system
produces, so it is asserted explicitly rather than assumed.
"""

import pytest

from app.trade_flow import (
    TAKER_BUY,
    TAKER_SELL,
    TradeFlowTracker,
    TradeFlowWindow,
    signed_notional,
)

T0 = 1_788_855_000_000


def _trade(side, px="100", sz="2", coin="BTC", time_ms=T0):
    return {"coin": coin, "side": side, "px": px, "sz": sz, "time": time_ms}


class TestSignedNotional:
    """Sign convention determined empirically against the live book, 2026-09-08."""

    def test_side_b_is_an_aggressive_buy_and_counts_positive(self):
        assert signed_notional(_trade(TAKER_BUY)) == pytest.approx(200.0)

    def test_side_a_is_an_aggressive_sell_and_counts_negative(self):
        assert signed_notional(_trade(TAKER_SELL)) == pytest.approx(-200.0)

    def test_an_unknown_side_is_skipped_not_guessed(self):
        assert signed_notional(_trade("X")) is None
        assert signed_notional({"px": "100", "sz": "1"}) is None

    def test_unparseable_numbers_are_skipped(self):
        assert signed_notional(_trade(TAKER_BUY, px="abc")) is None
        assert signed_notional(_trade(TAKER_BUY, sz=None)) is None

    def test_non_positive_values_are_skipped(self):
        assert signed_notional(_trade(TAKER_BUY, px="0")) is None
        assert signed_notional(_trade(TAKER_BUY, sz="-1")) is None


class TestWindow:
    def test_balanced_flow_nets_to_zero(self):
        w = TradeFlowWindow(window_ms=60_000)
        w.add(T0, 500.0)
        w.add(T0, -500.0)
        assert w.value(T0) == pytest.approx(0.0)

    def test_trades_outside_the_window_are_dropped(self):
        w = TradeFlowWindow(window_ms=60_000)
        w.add(T0, 1000.0)
        w.add(T0 + 30_000, 250.0)
        # 90s later the first trade has aged out of a 60s window.
        assert w.value(T0 + 90_000) == pytest.approx(250.0)

    def test_an_entirely_expired_window_reads_zero(self):
        w = TradeFlowWindow(window_ms=60_000)
        w.add(T0, 1000.0)
        assert w.value(T0 + 300_000) == pytest.approx(0.0)
        assert len(w) == 0


class TestTracker:
    def test_buying_pressure_is_positive_and_selling_negative(self):
        tracker = TradeFlowTracker(["BTC"])
        tracker.ingest([_trade(TAKER_BUY, sz="3"), _trade(TAKER_SELL, sz="1")])
        assert tracker.value("BTC", T0) == pytest.approx(200.0)

        selling = TradeFlowTracker(["BTC"])
        selling.ingest([_trade(TAKER_SELL, sz="3"), _trade(TAKER_BUY, sz="1")])
        assert selling.value("BTC", T0) == pytest.approx(-200.0)

    def test_unobserved_symbol_reads_none_not_zero(self):
        """Zero means balanced flow; no observation must not look like balance."""
        tracker = TradeFlowTracker(["BTC", "ETH"])
        tracker.ingest([_trade(TAKER_BUY, coin="BTC")])
        assert tracker.value("BTC", T0) is not None
        assert tracker.value("ETH", T0) is None
        assert tracker.value("SOL", T0) is None

    def test_trades_for_untracked_coins_are_ignored(self):
        tracker = TradeFlowTracker(["BTC"])
        counted = tracker.ingest([_trade(TAKER_BUY, coin="DOGE")])
        assert counted == 0
        assert tracker.value("BTC", T0) is None

    def test_malformed_entries_do_not_break_a_batch(self):
        tracker = TradeFlowTracker(["BTC"])
        counted = tracker.ingest([
            "not-a-trade",
            {"coin": "BTC", "side": "B", "px": "x", "sz": "1", "time": T0},
            {"coin": "BTC", "side": "B", "px": "100", "sz": "1", "time": "bad"},
            _trade(TAKER_BUY, sz="1"),
        ])
        assert counted == 1
        assert tracker.value("BTC", T0) == pytest.approx(100.0)

    def test_observed_count_tracks_admitted_trades(self):
        tracker = TradeFlowTracker(["BTC"])
        tracker.ingest([_trade(TAKER_BUY), _trade(TAKER_SELL), _trade("X")])
        assert tracker.observed("BTC") == 2
