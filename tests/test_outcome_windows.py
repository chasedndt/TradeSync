"""The outcome job must ask for the windows it measures, and say so if it did not."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_service_module  # noqa: E402

_windows = load_service_module("core_scorer_app", "core-scorer", "outcome_windows")
FetchRange = _windows.FetchRange
chunk_ranges = _windows.chunk_ranges
merge_candles = _windows.merge_candles
required_span_s = _windows.required_span_s
window_was_requested = _windows.window_was_requested

MIN = 60
DAY = 86_400


def test_the_span_covers_the_oldest_open_and_the_newest_close() -> None:
    span = required_span_s([1_000, 5_000, 3_000], longest_horizon_minutes=240, candle_s=MIN)
    assert span == (1_000 - MIN, 5_000 + 240 * MIN + MIN)


def test_an_empty_batch_has_no_span() -> None:
    assert required_span_s([], 240, MIN) is None


def test_a_two_day_span_is_split_to_the_venue_cap_with_abutting_chunks() -> None:
    """The old job asked for the last 480 candles. Two days is 2,880."""
    chunks = chunk_ranges(0, 2 * DAY, MIN)
    assert len(chunks) == 3
    assert chunks[0] == FetchRange(0, 1000 * MIN * 1000)
    for earlier, later in zip(chunks, chunks[1:]):
        assert earlier.end_ms == later.start_ms
    assert chunks[-1].end_ms == 2 * DAY * 1000


def test_a_span_inside_the_cap_is_one_chunk() -> None:
    assert chunk_ranges(0, 600 * MIN, MIN) == [FetchRange(0, 600 * MIN * 1000)]


def test_merging_chunks_dedupes_by_open_time_and_sorts() -> None:
    a = [{"time": 120, "open": 1}, {"time": 60, "open": 1}]
    b = [{"time": 120, "open": 2}, {"time": 180, "open": 1}]
    merged = merge_candles([a, b])
    assert [c["time"] for c in merged] == [60, 120, 180]
    assert merged[1]["open"] == 2  # the later batch wins on a shared boundary


def test_a_window_that_was_never_requested_is_not_evidence_of_a_gap() -> None:
    """The defect: eight hours fetched, a window from yesterday judged empty."""
    fetched = [FetchRange((3 * DAY - 8 * 3600) * 1000, 3 * DAY * 1000)]
    yesterday = 2 * DAY
    assert not window_was_requested(fetched, yesterday, 15)
    assert not window_was_requested(fetched, yesterday, 240)


def test_a_window_inside_the_fetched_range_was_requested() -> None:
    fetched = [FetchRange(0, DAY * 1000)]
    assert window_was_requested(fetched, 3600, 240)


def test_a_window_straddling_two_abutting_chunks_was_requested() -> None:
    boundary = 1000 * MIN
    fetched = [FetchRange(0, boundary * 1000), FetchRange(boundary * 1000, 2 * boundary * 1000)]
    assert window_was_requested(fetched, boundary - 30 * MIN, 240)


def test_a_failed_chunk_leaves_a_hole_that_disqualifies_the_window() -> None:
    boundary = 1000 * MIN
    # The middle chunk was not received.
    fetched = [FetchRange(0, boundary * 1000), FetchRange(2 * boundary * 1000, 3 * boundary * 1000)]
    assert not window_was_requested(fetched, boundary - 30 * MIN, 240)
    assert window_was_requested(fetched, 10 * MIN, 240)


def test_a_window_running_past_the_fetched_end_was_not_fully_requested() -> None:
    fetched = [FetchRange(0, 3600 * 1000)]
    assert not window_was_requested(fetched, 3000, 60)
