"""Hyperliquid funding history across a whole window, kept per market.

Hyperliquid answers ``fundingHistory`` with at most 500 rows from
``startTime``, oldest first. One request therefore covered only the first 500
hours of a longer window: a daily canvas asked for 1,000 days and drew three
weeks from the start of the window and nothing since.

This pages forward from the last row until a short page or the end of the
window, and keeps what it fetched per market. A later request for the same
window fetches only the hours published since (usually no request, at most
one), and a request reaching further back fetches only the part not yet held.
Every request still goes through the provider's rate limiter.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

PAGE_ROWS = 500
MAX_PAGES = 60
HOUR_MS = 3_600_000
MAX_ROWS_KEPT = 40_000

Request = Callable[[dict[str, Any]], Awaitable[Any]]


def to_row(venue: str, symbol: str, entry: Any) -> dict[str, Any] | None:
    """One venue entry as the provider's row, keeping the premium; None when malformed."""
    if not isinstance(entry, dict):
        return None
    try:
        return {"venue": venue, "symbol": symbol, "rate": float(entry.get("fundingRate", 0)),
                "premium": float(entry.get("premium", 0)), "ts": int(entry["time"]), "source": "fundingHistory"}
    except (KeyError, TypeError, ValueError):
        return None


def merge(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows from several fetches, one per timestamp, oldest first."""
    by_ts: dict[int, dict[str, Any]] = {}
    for group in groups:
        for row in group:
            by_ts[row["ts"]] = row
    return [by_ts[ts] for ts in sorted(by_ts)]


async def page_range(request: Request, coin: str, venue: str, symbol: str, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    """Every row from ``start_ms`` to ``end_ms``, one 500-row page at a time."""
    rows: list[dict[str, Any]] = []
    cursor = start_ms
    for _ in range(MAX_PAGES):
        if cursor > end_ms:
            break
        page = await request({"type": "fundingHistory", "coin": coin, "startTime": cursor, "endTime": end_ms})
        if not isinstance(page, list) or not page:
            break
        converted = [row for row in (to_row(venue, symbol, entry) for entry in page) if row]
        rows.extend(row for row in converted if start_ms <= row["ts"] <= end_ms)
        last = max((row["ts"] for row in converted), default=cursor - 1)
        # Stop on a short page, or when the next hourly row would fall past the window: no need to ask for nothing.
        if len(page) < PAGE_ROWS or last + HOUR_MS > end_ms or last < cursor:
            break
        cursor = last + 1
    return rows


class FundingHistoryCache:
    """Funding rows per market, fetched once and extended as new hours are published."""

    def __init__(self, request: Request, venue: str, now_ms: Callable[[], int] | None = None) -> None:
        self._request = request
        self._venue = venue
        self._now = now_ms or (lambda: int(time.time() * 1000))
        self._rows: dict[str, list[dict[str, Any]]] = {}
        self._floor: dict[str, int] = {}

    def cached(self, symbol: str, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
        return [row for row in self._rows.get(symbol, []) if start_ms <= row["ts"] <= end_ms]

    async def history(self, symbol: str, coin: str, start_ms: int, end_ms: int | None = None) -> list[dict[str, Any]]:
        end = int(end_ms) if end_ms is not None else self._now()
        start = int(start_ms)
        rows = self._rows.get(symbol, [])
        floor = self._floor.get(symbol)
        if floor is None or start < floor:
            upper = end if floor is None else floor - 1
            rows = merge(await page_range(self._request, coin, self._venue, symbol, start, upper), rows)
            self._floor[symbol] = start if floor is None else min(start, floor)
        if floor is not None:
            newest = rows[-1]["ts"] if rows else start - 1
            # A new funding row is published each hour; ask only once one could exist.
            if newest < end - HOUR_MS:
                rows = merge(rows, await page_range(self._request, coin, self._venue, symbol, max(newest + 1, start), end))
        self._rows[symbol] = rows[-MAX_ROWS_KEPT:]
        return self.cached(symbol, start, end)
