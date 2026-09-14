"""Binance USDT-M open-interest history, the public seed for the estimated liquidation map.

Hyperliquid publishes only the current open interest, so its own history starts
when TradeSync begins recording it. Binance serves the last 30 days of
aggregated open interest per period without a key; it is market-wide leverage
context for the same coins, not Hyperliquid data.
"""

from __future__ import annotations

import math
import time
from typing import Any

import httpx

URL = "https://fapi.binance.com/futures/data/openInterestHist"
PERIODS = ("5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d")
MAX_LIMIT = 500
CACHE_TTL_S = 300


def parse(rows: Any) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    for row in rows if isinstance(rows, list) else []:
        try:
            ts, coins, usd = int(row["timestamp"]), float(row["sumOpenInterest"]), float(row["sumOpenInterestValue"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(coins) and math.isfinite(usd) and coins > 0 and usd > 0:
            out.append({"time": ts // 1000, "oi_coins": coins, "oi_usd": usd})
    out.sort(key=lambda r: r["time"])
    return out


class OpenInterestHistory:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, int], tuple[float, list[dict[str, float]]]] = {}

    async def get(self, symbol: str, period: str, limit: int = MAX_LIMIT) -> dict[str, Any]:
        if period not in PERIODS:
            raise ValueError(f"period must be one of {', '.join(PERIODS)}")
        limit = max(1, min(int(limit), MAX_LIMIT))
        key = (symbol, period, limit)
        cached = self._cache.get(key)
        if cached and time.time() - cached[0] < CACHE_TTL_S:
            rows = cached[1]
        else:
            market = f"{symbol.replace('-PERP', '')}USDT"
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(URL, params={"symbol": market, "period": period, "limit": limit})
            if response.status_code == 400:
                rows = []  # Binance does not list this market
            else:
                response.raise_for_status()
                rows = parse(response.json())
            self._cache[key] = (time.time(), rows)
        return {"source": "binance", "symbol": symbol, "period": period, "rows": rows,
                "authority": "context_only",
                "note": "Binance USDT-M aggregated open interest (last 30 days at most); market-wide leverage context, not Hyperliquid."}
