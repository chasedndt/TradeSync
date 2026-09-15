"""Keep the timeframe outlook warm for the markets pages open first.

Every minute, each warm market's short-term and daily measurements are measured
again shortly before they expire (``horizons.PART_TTL_S``), so a page is served
from the cache instead of waiting for candles. A request still measures on
demand when this loop is behind or down. Each pass is kept on a heartbeat for
the integration pipeline page, with the time of every warm measurement.
"""

from __future__ import annotations

import asyncio
import time

from app import background, horizons
from app.feed_heartbeats import feed
from tradesync_core.feed_heartbeat import describe_error, iso

HEARTBEAT = feed("horizons_warm", label="Timeframes warm loop", kind="loop", authority="display_only",
                 influence="Keeps the Timeframes measurements fresh: records and out-of-sample weights on that page, and the "
                           "numbers Hermes readings read; no influence on opportunity scoring.",
                 counts=("passes", "measurements"))


async def warm_pass(market_data_url: str) -> None:
    """Measure every warm part that is about to expire, and keep the pass on the heartbeat."""
    done = failures = 0
    for symbol in horizons.WARM_SYMBOLS:
        for part in horizons.PARTS:
            entry = horizons._cache.get((symbol, part))
            if entry is None or time.time() - entry["at"] >= horizons.PART_TTL_S[part] - 30:
                try:
                    await horizons.measured(market_data_url, symbol, part, force=True)
                    done += 1
                except Exception as exc:  # the next pass retries; a request still measures on demand
                    failures += 1
                    HEARTBEAT.error(f"{symbol} {part}: {describe_error(exc)}")
                    print(f"[Horizons] {symbol} {part} not measured: {type(exc).__name__}")
    HEARTBEAT.detail["measured_at"] = {f"{symbol} {part}": iso(horizons._cache[(symbol, part)]["at"])
                                       for symbol in horizons.WARM_SYMBOLS for part in horizons.PARTS
                                       if (symbol, part) in horizons._cache}
    if failures and not done:
        HEARTBEAT.failed("no warm measurement succeeded this pass")
    else:
        HEARTBEAT.succeeded(passes=1, measurements=done)


def register(*, market_data_url: str) -> None:
    async def warm() -> None:
        await asyncio.sleep(120)  # let market-data settle after a restart
        while True:
            await warm_pass(market_data_url)
            await asyncio.sleep(60)

    background.add("horizons_warm", warm)
