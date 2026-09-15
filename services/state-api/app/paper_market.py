"""Market-data reads for the paper risk loops: executable books, published funding and closed hourly candles.

The tracked universe comes from market-data's own snapshot list through
``editions.tracked_symbols``; no symbol is named here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx

from app import paper_funding_store
from tradesync_core.paper_correlation import BAR_INTERVAL, WINDOW_BARS

BookFetcher = Callable[[str], Awaitable[dict[str, Any]]]
FundingFetcher = Callable[[str, list[int]], Awaitable[tuple[dict[int, dict[str, Any]], float]]]


@dataclass(frozen=True)
class Market:
    """What closing a paper position needs from market-data: a fresh book, and published funding for given hours."""

    book: BookFetcher
    funding: FundingFetcher


async def _get(url: str, timeout: float) -> Any:
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


def market(market_data_url: str) -> Market:
    async def book(symbol: str) -> dict[str, Any]:
        return await _get(f"{market_data_url}/depth/hyperliquid/{symbol}", 8.0)

    async def funding(symbol: str, hours: list[int]) -> tuple[dict[int, dict[str, Any]], float]:
        return await paper_funding_store.published(market_data_url, symbol, hours)

    return Market(book=book, funding=funding)


async def hourly_candles(market_data_url: str, symbol: str) -> list[dict[str, Any]]:
    payload = await _get(f"{market_data_url}/candles/hyperliquid/{symbol}?interval={BAR_INTERVAL}&limit={WINDOW_BARS + 2}", 20.0)
    return payload.get("candles") or []
