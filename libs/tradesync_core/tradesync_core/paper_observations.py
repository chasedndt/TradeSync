"""Validation of what a managed paper position observes: an order book's touch and closed candles.

A book is refused when it is stale or dated in the future, crossed, wider than the
common spread limit, missing a side, or when its touch disagrees with its ladder. A
candle must be internally consistent, and a candle series for the average true range
must be closed, contiguous and recent. Refusing is the answer: nothing is repaired or
assumed.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from .paper_lifecycle_rules import COMMON


def finite(value: Any, positive: bool = False) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError("Invalid numeric input")
    return value


def quote(book: Mapping[str, Any], now_s: float) -> tuple[float, float, float]:
    """The observed touch as (time, bid, ask)."""
    timestamp = finite(book.get("poll_ts"), True) / 1000
    if not -COMMON.max_quote_future_s <= now_s - timestamp <= COMMON.max_quote_age_s:
        raise ValueError("Quote stale or future-dated")
    bid, ask = finite(book.get("best_bid"), True), finite(book.get("best_ask"), True)
    if ask < bid or (ask - bid) / ((ask + bid) / 2) * 10000 > COMMON.max_spread_bps:
        raise ValueError("Crossed or excessively wide book")
    for key, touch in (("bids", bid), ("asks", ask)):
        rows = book.get(key)
        if not isinstance(rows, list) or not rows:
            raise ValueError("Displayed book side missing")
        if not isinstance(rows[0], Mapping) or rows[0].get("price") != touch:
            raise ValueError("Touch and ladder disagree")
    return timestamp, bid, ask


def candle(bar: Mapping[str, Any]) -> Mapping[str, Any]:
    """A candle with a positive time and a consistent open, high, low and close."""
    finite(bar.get("time"), True)
    for key in ("open", "high", "low", "close"):
        finite(bar.get(key), True)
    if bar["low"] > min(bar["open"], bar["close"]) or bar["high"] < max(bar["open"], bar["close"]):
        raise ValueError("Inconsistent candle range")
    return bar


def atr(candles, seconds: float, now_s: float, period: int = 14) -> float:
    """Average true range over ``period`` closed, contiguous candles ending at most two intervals ago."""
    bars = sorted([c for c in candles if finite(c.get("time"), True) + seconds <= now_s], key=lambda c: c["time"])
    if len(bars) < period + 1:
        raise ValueError(f"At least {period + 1} closed candles needed for ATR")
    bars = bars[-(period + 1):]
    if now_s - (bars[-1]["time"] + seconds) > seconds * 2:
        raise ValueError("ATR source stale")
    for bar in bars:
        candle(bar)
    if any(b["time"] - a["time"] != seconds for a, b in zip(bars, bars[1:])):
        raise ValueError("ATR source has gaps or duplicates")
    return sum(max(b["high"] - b["low"], abs(b["high"] - a["close"]), abs(b["low"] - a["close"]))
               for a, b in zip(bars, bars[1:])) / period
