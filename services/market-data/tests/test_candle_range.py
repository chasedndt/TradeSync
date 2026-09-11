"""An explicit candle range, for measurements older than the latest history."""

from __future__ import annotations

import pytest

from app.candles import MAX_LIMIT, CandleRequestError, resolve_window

MIN_MS = 60_000


def test_without_a_range_the_window_is_the_latest_limit() -> None:
    interval, limit, start, end = resolve_window("1m", 30, now_ms=1_000_000)
    assert (interval, limit, start, end) == ("1m", 30, 1_000_000 - 30 * MIN_MS, 1_000_000)


def test_an_explicit_range_is_returned_as_given() -> None:
    interval, limit, start, end = resolve_window("1m", 300, start_ms=5_000_000, end_ms=5_000_000 + 120 * MIN_MS)
    assert (start, end) == (5_000_000, 5_000_000 + 120 * MIN_MS)
    assert limit == 120


def test_a_partial_final_candle_still_counts_toward_the_limit() -> None:
    *_, limit, _, _ = resolve_window("1m", 300, start_ms=0, end_ms=90_500)
    assert limit == 2


def test_half_a_range_is_refused() -> None:
    with pytest.raises(CandleRequestError, match="together"):
        resolve_window("1m", 300, start_ms=0)
    with pytest.raises(CandleRequestError, match="together"):
        resolve_window("1m", 300, end_ms=1)


def test_an_inverted_range_is_refused() -> None:
    with pytest.raises(CandleRequestError, match="after"):
        resolve_window("1m", 300, start_ms=10, end_ms=10)


def test_a_range_over_the_cap_is_refused_rather_than_silently_truncated() -> None:
    """Truncating would hand back a partial window that looks complete."""
    with pytest.raises(CandleRequestError, match="split"):
        resolve_window("1m", 300, start_ms=0, end_ms=(MAX_LIMIT + 1) * MIN_MS)
    assert resolve_window("1m", 300, start_ms=0, end_ms=MAX_LIMIT * MIN_MS)[1] == MAX_LIMIT
