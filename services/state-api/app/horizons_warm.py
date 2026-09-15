"""Keep the timeframe outlook warm for the markets pages open first.

Every minute, each warm market's short-term and daily measurements are measured
again shortly before they expire (``horizons.PART_TTL_S``), so a page is served
from the cache instead of waiting for candles. A request still measures on
demand when this loop is behind or down.
"""

from __future__ import annotations

import asyncio
import time

from app import background, horizons


def register(*, market_data_url: str) -> None:
    async def warm() -> None:
        await asyncio.sleep(120)  # let market-data settle after a restart
        while True:
            for symbol in horizons.WARM_SYMBOLS:
                for part in horizons.PARTS:
                    entry = horizons._cache.get((symbol, part))
                    if entry is None or time.time() - entry["at"] >= horizons.PART_TTL_S[part] - 30:
                        try:
                            await horizons.measured(market_data_url, symbol, part, force=True)
                        except Exception as exc:  # the next pass retries; a request still measures on demand
                            print(f"[Horizons] {symbol} {part} not measured: {type(exc).__name__}")
            await asyncio.sleep(60)

    background.add("horizons_warm", warm)
