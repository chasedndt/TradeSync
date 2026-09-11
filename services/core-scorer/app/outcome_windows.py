"""Which candles an outcome pass must fetch, and whether it actually got them.

Two defects lived in the outcome job before this module existed, and both
came from the same shortcut: asking the venue for "the last N candles" instead
of for the windows the pending opportunities actually need.

1. Any opportunity older than N candles found no candles inside its window and
   was stamped ``insufficient_candles`` — a terminal verdict — although the
   venue had the data and had never been asked for it. After a 27-hour outage
   every window that closed during it was written off this way.
2. The selection query treated those rows as still unfinished, so the newest
   forty of them were re-reviewed every pass, forever, and the 824 older
   ``pending`` windows behind them were never reached.

This module keeps the arithmetic separate and testable: the ranges to fetch,
chunked to the venue's per-request cap, and a coverage check so that a verdict
of "no candles" can only be written when the candles were genuinely asked for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

# market-data caps a single candle request at this many candles.
MAX_CANDLES_PER_REQUEST = 1000

# One candle either side, so the entry candle at or after opened_at and the
# last candle of the horizon are both inside the fetched range.
MARGIN_CANDLES = 1


@dataclass(frozen=True)
class FetchRange:
    start_ms: int
    end_ms: int


def required_span_s(
    opened_at_s: Iterable[int], longest_horizon_minutes: int, candle_s: int
) -> tuple[int, int] | None:
    """The one span, in seconds, that covers every window in the batch."""
    opened = list(opened_at_s)
    if not opened:
        return None
    margin = MARGIN_CANDLES * candle_s
    return min(opened) - margin, max(opened) + longest_horizon_minutes * 60 + margin


def chunk_ranges(start_s: int, end_s: int, candle_s: int) -> list[FetchRange]:
    """Split a span into requests the venue will accept, in milliseconds.

    Chunks abut exactly, so a window that straddles a boundary is covered by
    the union of two responses rather than falling into a seam.
    """
    if end_s <= start_s:
        return []
    chunk_s = MAX_CANDLES_PER_REQUEST * candle_s
    out: list[FetchRange] = []
    cursor = start_s
    while cursor < end_s:
        upper = min(cursor + chunk_s, end_s)
        out.append(FetchRange(cursor * 1000, upper * 1000))
        cursor = upper
    return out


def merge_candles(batches: Iterable[Sequence[Mapping[str, object]]]) -> list[dict]:
    """Union of chunk responses, one candle per open time, ascending."""
    by_time: dict[int, dict] = {}
    for batch in batches:
        for candle in batch:
            t = candle.get("time")
            if isinstance(t, int) and not isinstance(t, bool):
                by_time[t] = dict(candle)
    return [by_time[t] for t in sorted(by_time)]


def window_was_requested(
    fetched: Sequence[FetchRange], opened_at_s: int, horizon_minutes: int
) -> bool:
    """True only if every second of the window fell inside a fetched chunk.

    This is the guard that makes ``insufficient_candles`` trustworthy again:
    an empty window that was never requested is not evidence of anything.
    Chunks abut, so a window may span several and still count as requested.
    """
    start_ms = opened_at_s * 1000
    end_ms = (opened_at_s + horizon_minutes * 60) * 1000
    cursor = start_ms
    for chunk in sorted(fetched, key=lambda r: r.start_ms):
        if chunk.start_ms > cursor:
            return False  # a hole before this chunk
        if chunk.end_ms > cursor:
            cursor = chunk.end_ms
        if cursor >= end_ms:
            return True
    return cursor >= end_ms
