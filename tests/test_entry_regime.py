"""The entry-time regime must be knowable when the signal fires."""

from __future__ import annotations

import pytest

from tradesync_core.entry_regime import EntryRegimeError, classify_entry_regime

ENTRY = 10_000_000  # seconds; a multiple of 60 keeps the arithmetic readable
MIN = 60


def candles(start_s: int, count: int, first_open: float, step: float, interval: int = MIN):
    """``count`` one-interval candles from ``start_s``, each moving by ``step``."""
    out, price = [], first_open
    for i in range(count):
        out.append({"time": start_s + i * interval, "open": price, "close": price + step})
        price += step
    return out


def test_a_rising_hour_before_entry_is_labelled_rising() -> None:
    result = classify_entry_regime(candles(ENTRY - 60 * MIN, 60, 100.0, 0.1), ENTRY, MIN)
    assert result.regime == "rising"
    assert result.candles_used == 60
    assert result.trailing_return_pct == pytest.approx(6.0)
    assert result.window_end_s == ENTRY


def test_a_falling_hour_before_entry_is_labelled_falling() -> None:
    result = classify_entry_regime(candles(ENTRY - 60 * MIN, 60, 100.0, -0.1), ENTRY, MIN)
    assert result.regime == "falling"


def test_a_candle_still_open_at_entry_is_never_used() -> None:
    """Opened before the signal, closed after it: its close is a future price.

    The hour before entry falls gently. A candle opening 30 seconds before
    entry spikes hard. If it were used, the label would flip to rising using a
    price nobody had seen when the signal fired.
    """
    history = candles(ENTRY - 60 * MIN, 60, 100.0, -0.01)
    straddling = {"time": ENTRY - 30, "open": 99.4, "close": 150.0}
    result = classify_entry_regime(history + [straddling], ENTRY, MIN)
    assert result.regime == "falling"
    assert result.candles_used == 60


def test_candles_after_entry_are_ignored() -> None:
    before = candles(ENTRY - 60 * MIN, 60, 100.0, -0.01)
    after = candles(ENTRY, 60, 100.0, 5.0)
    assert classify_entry_regime(before + after, ENTRY, MIN).regime == "falling"


def test_a_hole_in_the_middle_is_reported_not_bridged() -> None:
    """Candles at both ends of the window with nothing between them.

    The span looks complete; the count does not. Checking only the span would
    have classified this from two prices an hour apart.
    """
    ends = candles(ENTRY - 60 * MIN, 3, 100.0, 0.1) + candles(ENTRY - 3 * MIN, 3, 100.0, 0.1)
    result = classify_entry_regime(ends, ENTRY, MIN)
    assert result.regime == "unknown"
    assert "gap" in result.reason


def test_no_candles_is_unknown_rather_than_flat() -> None:
    result = classify_entry_regime([], ENTRY, MIN)
    assert result.regime == "unknown"
    assert result.trailing_return_pct is None


def test_a_flat_band_sets_aside_near_zero_moves() -> None:
    quiet = candles(ENTRY - 60 * MIN, 60, 100.0, 0.001)  # +0.06% over the hour
    assert classify_entry_regime(quiet, ENTRY, MIN).regime == "rising"
    assert classify_entry_regime(quiet, ENTRY, MIN, flat_band_pct=0.1).regime == "flat"


def test_input_order_does_not_matter() -> None:
    rising = candles(ENTRY - 60 * MIN, 60, 100.0, 0.1)
    assert classify_entry_regime(list(reversed(rising)), ENTRY, MIN).regime == "rising"


def test_malformed_parameters_are_refused() -> None:
    with pytest.raises(EntryRegimeError):
        classify_entry_regime([], ENTRY, 0)
    with pytest.raises(EntryRegimeError):
        classify_entry_regime([], ENTRY, MIN, lookback_minutes=0)
    with pytest.raises(EntryRegimeError):
        classify_entry_regime([], ENTRY, MIN, flat_band_pct=-1)
