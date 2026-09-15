"""Market-data reads for the paper risk loops: the executable book and closed hourly candles.

The tracked universe comes from market-data's own snapshot list through
``editions.tracked_symbols``; no symbol is named here.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import httpx

from tradesync_core.paper_correlation import BAR_INTERVAL, WINDOW_BARS

BookFetcher = Callable[[str], Awaitable[dict[str, Any]]]


async def _get(url: str, timeout: float) -> Any:
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


def book_fetcher(market_data_url: str) -> BookFetcher:
    async def fetch(symbol: str) -> dict[str, Any]:
        return await _get(f"{market_data_url}/depth/hyperliquid/{symbol}", 8.0)

    return fetch


async def hourly_candles(market_data_url: str, symbol: str) -> list[dict[str, Any]]:
    payload = await _get(f"{market_data_url}/candles/hyperliquid/{symbol}?interval={BAR_INTERVAL}&limit={WINDOW_BARS + 2}", 20.0)
    return payload.get("candles") or []
