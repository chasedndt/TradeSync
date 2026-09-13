"""Funding history covers the whole window despite the venue's 500-row pages, and repeat requests are cheap."""

from __future__ import annotations

import asyncio

from app.providers.funding_history import HOUR_MS, PAGE_ROWS, FundingHistoryCache, merge, page_range, to_row

T0 = 1_700_000_000_000 - (1_700_000_000_000 % HOUR_MS)


class FakeVenue:
    """Hourly funding rows between ``first`` and ``last``, served the way Hyperliquid pages them."""

    def __init__(self, first: int, last: int) -> None:
        self.first, self.last, self.calls = first, last, []

    async def __call__(self, payload: dict) -> list[dict]:
        self.calls.append(payload)
        start = max(payload["startTime"], self.first)
        end = min(payload.get("endTime", self.last), self.last)
        t = start + (-start % HOUR_MS)
        out = []
        while t <= end and len(out) < PAGE_ROWS:
            out.append({"coin": payload["coin"], "fundingRate": "0.0000125", "premium": "-0.0004", "time": t})
            t += HOUR_MS
        return out


def test_a_long_window_is_paged_to_the_end_and_keeps_the_premium() -> None:
    venue = FakeVenue(T0, T0 + 1199 * HOUR_MS)
    rows = asyncio.run(page_range(venue, "BTC", "hyperliquid", "BTC-PERP", T0, T0 + 1199 * HOUR_MS))
    assert len(rows) == 1200 and len(venue.calls) == 3
    assert rows[0]["ts"] == T0 and rows[-1]["ts"] == T0 + 1199 * HOUR_MS
    assert rows[0]["premium"] == -0.0004 and rows[0]["rate"] == 0.0000125


def test_paging_stops_on_a_short_or_empty_page() -> None:
    short = FakeVenue(T0, T0 + 10 * HOUR_MS)
    assert len(asyncio.run(page_range(short, "BTC", "hyperliquid", "BTC-PERP", T0, T0 + 5000 * HOUR_MS))) == 11
    assert len(short.calls) == 1
    empty = FakeVenue(T0 + 10_000 * HOUR_MS, T0 + 10_001 * HOUR_MS)
    assert asyncio.run(page_range(empty, "BTC", "hyperliquid", "BTC-PERP", T0, T0 + 5 * HOUR_MS)) == []


def test_repeats_cost_nothing_and_new_hours_cost_one_request() -> None:
    now = {"ms": T0 + 999 * HOUR_MS + 60_000}
    venue = FakeVenue(T0, T0 + 999 * HOUR_MS)
    cache = FundingHistoryCache(venue, "hyperliquid", now_ms=lambda: now["ms"])
    first = asyncio.run(cache.history("BTC-PERP", "BTC", T0))
    assert len(first) == 1000 and len(venue.calls) == 2
    again = asyncio.run(cache.history("BTC-PERP", "BTC", T0))
    assert len(again) == 1000 and len(venue.calls) == 2
    venue.last += 2 * HOUR_MS
    now["ms"] += 2 * HOUR_MS
    later = asyncio.run(cache.history("BTC-PERP", "BTC", T0))
    assert len(later) == 1002 and len(venue.calls) == 3 and later[-1]["ts"] == T0 + 1001 * HOUR_MS


def test_an_older_window_backfills_only_what_is_missing() -> None:
    venue = FakeVenue(T0, T0 + 2000 * HOUR_MS)
    now = lambda: T0 + 2000 * HOUR_MS + 1  # noqa: E731
    cache = FundingHistoryCache(venue, "hyperliquid", now_ms=now)
    asyncio.run(cache.history("ETH-PERP", "ETH", T0 + 1500 * HOUR_MS))
    calls_before = len(venue.calls)
    older = asyncio.run(cache.history("ETH-PERP", "ETH", T0 + 1000 * HOUR_MS))
    backfill = venue.calls[calls_before]
    assert backfill["startTime"] == T0 + 1000 * HOUR_MS and backfill["endTime"] == T0 + 1500 * HOUR_MS - 1
    assert len(older) == 1001 and older[0]["ts"] == T0 + 1000 * HOUR_MS


def test_malformed_entries_are_skipped_and_merges_keep_one_row_per_hour() -> None:
    assert to_row("hyperliquid", "BTC-PERP", {"fundingRate": "x", "time": 1}) is None
    assert to_row("hyperliquid", "BTC-PERP", {"fundingRate": "0.1"}) is None
    a = [{"ts": 2, "rate": 1.0}, {"ts": 1, "rate": 1.0}]
    b = [{"ts": 2, "rate": 2.0}]
    assert merge(a, b) == [{"ts": 1, "rate": 1.0}, {"ts": 2, "rate": 2.0}]
