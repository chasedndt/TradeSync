"""Liquidity and liquidation context for the feature pipeline.

Computed away from the snapshot path and attached to each snapshot's
``derived`` block, so the feature extractor records them like any other
feature and the Regime Lab, the evidence cards and the thesis can measure them:

- from the latest book aggregated to three significant figures: the balance of
  resting bids against asks near price, and the distance to the largest wall
  below and above;
- from liquidations received in the last hour (Bybit, Binance): long and short
  notional and their difference;
- every five minutes, from the estimated liquidation map (Binance open-interest
  changes placed at Hyperliquid prices): the balance of estimated levels within
  3% above and below price, and the distance to the largest cluster each side.

None of them can score until it earns a weight; the catalog marks them context.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence

from tradesync_core.feed_heartbeat import describe_error
from tradesync_core.liquidation_map import Bar, estimate, skew
from tradesync_core.liquidity_heatmap import walls

from . import binance_liquidations, liquidation_context, liquidation_events
from .feed_status import feed

logger = logging.getLogger(__name__)

HEARTBEAT = feed("liquidity_context", label="Liquidity context loop", kind="loop", authority="context_only",
                 influence="Context only: attaches resting liquidity, received liquidations and liquidation-map readings to "
                           "each snapshot as features the feature catalog marks non-scoring.",
                 counts=("passes", "map_passes"))

LIQUIDATIONS_EVERY_S = 30
MAP_EVERY_S = 300
MIN_MAP_BARS = 48
STALE_AFTER_MS = {"book": 120_000, "liquidations": 120_000, "map": 20 * 60_000}

_liquidations: dict[str, dict[str, Any]] = {}
_maps: dict[str, dict[str, Any]] = {}


def book_context(books: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
    """Balance and walls from the three-significant-figure book, when it is fresh."""
    book = books.get("3")
    if not book or book.get("stale") or not book.get("bids") or not book.get("asks"):
        return None
    mid = (float(book["bids"][0][0]) + float(book["asks"][0][0])) / 2
    near = walls(book["bids"], book["asks"], mid)
    return {
        "observed_at_ms": int(book["time_ms"]),
        "imbalance": near["imbalance"],
        "bid_wall_bps": near["below"]["distance_bps"] if near["below"] else None,
        "ask_wall_bps": near["above"]["distance_bps"] if near["above"] else None,
    }


def liquidation_totals(events: Sequence[Mapping[str, Any]], now_s: float, window_s: int = 3600) -> dict[str, Any]:
    recent = [e for e in events if 0 <= now_s - float(e["event_time"]) <= window_s]
    longs = sum(float(e["notional_usd"]) for e in recent if e["position_side"] == "long")
    shorts = sum(float(e["notional_usd"]) for e in recent if e["position_side"] == "short")
    return {"observed_at_ms": int(now_s * 1000), "long_usd": round(longs), "short_usd": round(shorts),
            "net_usd": round(longs - shorts), "events": len(recent)}


def map_context(bars: Sequence[Bar], now_s: float) -> dict[str, Any] | None:
    if len(bars) < MIN_MAP_BARS:
        return None
    result = estimate(bars, output_from=len(bars) - 1)
    above, below = result["clusters"]["above"], result["clusters"]["below"]
    return {
        "observed_at_ms": int(now_s * 1000),
        "skew_3pct": skew(result["profile"]),
        "largest_above_pct": above[0]["distance_pct"] if above else None,
        "largest_below_pct": below[0]["distance_pct"] if below else None,
    }


def _fresh(entry: Mapping[str, Any] | None, kind: str, now_ms: int) -> bool:
    return bool(entry) and now_ms - int(entry["observed_at_ms"]) <= STALE_AFTER_MS[kind]


def attach(payload: dict[str, Any], books: Mapping[str, Mapping[str, Any]], now_ms: int | None = None) -> dict[str, Any]:
    """Write the current liquidity context onto a snapshot; stale or missing parts are left out, not zeroed."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    symbol = str(payload.get("symbol") or "")
    derived = payload.setdefault("derived", {})
    book = book_context(books)
    if book and _fresh(book, "book", now_ms):
        derived["resting_liquidity"] = book
    if _fresh(_liquidations.get(symbol), "liquidations", now_ms):
        derived["cex_liquidations_1h"] = _liquidations[symbol]
    if _fresh(_maps.get(symbol), "map", now_ms):
        derived["liquidation_map"] = _maps[symbol]
    return payload


async def run(redis, symbols: Iterable[str], fetch_bars: Callable[[str], Awaitable[list[Bar]]]) -> None:
    """Keep received-liquidation totals (every 30 s) and liquidation-map context (every 5 min) current per market."""
    markets = list(symbols)
    HEARTBEAT.detail["markets"] = len(markets)
    last_map = 0.0
    while True:
        started = time.monotonic()
        failures = 0
        for symbol in markets:
            try:
                merged = liquidation_events.merged(symbol, await liquidation_context.history(redis, symbol),
                                                   await binance_liquidations.history(redis, symbol))
                _liquidations[symbol] = liquidation_totals(merged["events"], time.time())
            except Exception as exc:  # context only: a failure leaves the value out
                failures += 1
                HEARTBEAT.error(f"{symbol}: {describe_error(exc)}")
                logger.warning(f"liquidation totals unavailable for {symbol}: {type(exc).__name__}")
        if time.monotonic() - last_map >= MAP_EVERY_S:
            last_map = time.monotonic()
            for symbol in markets:
                try:
                    context = map_context(await fetch_bars(symbol), time.time())
                    if context:
                        _maps[symbol] = context
                except Exception as exc:
                    HEARTBEAT.error(f"{symbol} map: {describe_error(exc)}")
                    logger.warning(f"liquidation map unavailable for {symbol}: {type(exc).__name__}")
            HEARTBEAT.count("map_passes")
        if markets and failures == len(markets):
            HEARTBEAT.failed("no market's received liquidations could be read this pass")
        else:
            HEARTBEAT.succeeded(passes=1)
        await asyncio.sleep(max(1.0, LIQUIDATIONS_EVERY_S - (time.monotonic() - started)))
