"""Hourly correlation measurement over the tracked universe, stored for entry admission.

The universe is market-data's own snapshot list. A symbol whose candles cannot be
fetched is stored as unmeasured, which refuses its entries rather than guessing.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app import editions, paper_market
from app import paper_correlation_store as correlations
from tradesync_core.paper_correlation import measure

PERIOD_S = 3600
RETRY_S = 300
SOURCE = "Hyperliquid hourly candles via market-data"

status: dict[str, Any] = {"last_measured_at": None, "last_error": None, "symbols": [], "unmeasured": [], "fetch_failures": []}


async def measure_once(pool, market_data_url: str, now_s: float | None = None) -> dict[str, Any]:
    symbols = await editions.tracked_symbols(market_data_url)
    if not symbols:
        raise RuntimeError("Tracked symbol universe unavailable from market-data")
    candles: dict[str, list[dict[str, Any]]] = {}
    failures = []
    for symbol in symbols:
        try:
            candles[symbol] = await paper_market.hourly_candles(market_data_url, symbol)
        except Exception as exc:  # stored as unmeasured, never filled in
            candles[symbol] = []
            failures.append({"symbol": symbol, "reason": type(exc).__name__})
    measurement = measure(candles, time.time() if now_s is None else now_s)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await correlations.insert(conn, measurement, SOURCE)
            await correlations.prune(conn)
    status.update(last_measured_at=time.time(), last_error=None, symbols=measurement["symbols"],
                  unmeasured=measurement["unmeasured"], fetch_failures=failures)
    return measurement


def loop(state, market_data_url: str):
    async def run() -> None:
        await asyncio.sleep(20)  # let market-data answer first
        while True:
            delay = RETRY_S
            if state.pool is not None:
                try:
                    await measure_once(state.pool, market_data_url)
                    delay = PERIOD_S
                except Exception as exc:  # entries stay refused until a measurement is stored
                    status["last_error"] = type(exc).__name__
            await asyncio.sleep(delay)

    return run
