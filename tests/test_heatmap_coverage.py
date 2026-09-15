"""Recorded history fills the resting-liquidity heatmap's 7-day and 30-day windows.

Books are recorded once a minute; retention keeps every minute for three days and
every fifteenth minute to ninety days. Both long windows use the two-significant-
figure book, in two-hour (7 days) and eight-hour (30 days) buckets, so once history
covers a window every bucket holds books, and until then a window is filled exactly
from the bucket in which recording began.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tradesync_core.liquidity_heatmap import WINDOWS, build
from tradesync_core.market_history import DEPTH_FULL_DAYS, DEPTH_KEEP_DAYS, kept_after_downsampling

STARTED = datetime(2026, 9, 14, 11, 38, tzinfo=timezone.utc)  # when recording began


def recorded(now: datetime) -> list[dict]:
    """One book a minute from STARTED to now, as retention leaves them at ``now``."""
    rows, t = [], STARTED
    while t <= now:
        if kept_after_downsampling(t, now, DEPTH_FULL_DAYS, DEPTH_KEEP_DAYS):
            rows.append({"observed_at": t, "mid_price": 100.0, "bids": [[99.0, 1.0]], "asks": [[101.0, 1.0]]})
        t += timedelta(minutes=1)
    return rows


def books_per_bucket(rows: list[dict], now: datetime, window: str) -> tuple[list[int], int]:
    """The heatmap route's own alignment: buckets end at the bucket after now."""
    span, bucket, _ = WINDOWS[window]
    end = int(now.timestamp()) // bucket * bucket + bucket
    return build(rows, bucket, end - span, end)["books_per_bucket"], end


def test_both_long_windows_are_filled_in_every_bucket_once_history_covers_them() -> None:
    assert WINDOWS["7d"][2] == WINDOWS["30d"][2] == 2 and DEPTH_KEEP_DAYS >= 30
    now = STARTED + timedelta(days=31, hours=5)
    rows = recorded(now)
    for window, least in (("7d", 8), ("30d", 32)):  # a book every fifteen minutes after three days
        books, _ = books_per_bucket(rows, now, window)
        assert len(books) == WINDOWS[window][0] // WINDOWS[window][1]
        assert min(books[:-1]) >= least and books[-1] > 0, window  # the newest bucket is still filling


def test_before_then_a_window_is_filled_from_the_bucket_in_which_recording_began() -> None:
    now = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)
    rows = recorded(now)
    for window in ("7d", "30d"):
        books, end = books_per_bucket(rows, now, window)
        bucket = WINDOWS[window][1]
        first_filled = int(STARTED.timestamp()) // bucket * bucket
        assert sum(1 for n in books if n) == (end - first_filled) // bucket < len(books), window
