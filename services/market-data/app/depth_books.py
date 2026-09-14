"""The latest aggregated Hyperliquid order books, kept for the liquidity heatmap.

Hyperliquid's ``l2Book`` returns 20 levels a side. Unaggregated that covers a
few dollars around the touch; with ``nSigFigs`` 3 it groups BTC into about
$100 steps (roughly ±2.5% of price) and with 2 into about $1,000 steps
(roughly ±25%), which is wide enough to see where resting liquidity sits on
higher timeframes. A websocket message does not say which aggregation it
answers, so each aggregation has its own connection and is filed under it.

Displayed orders can be cancelled: this is resting liquidity as observed, not
executable depth and not liquidation levels.
"""

from __future__ import annotations

import math
import time
from typing import Any

AGGREGATIONS: tuple[int, ...] = (2, 3)
STALE_AFTER_MS = 120_000


def parse_side(rows: Any) -> list[tuple[float, float]]:
    """``[{px, sz, n}, ...]`` from the venue as (price, size) pairs; malformed rows are dropped."""
    out: list[tuple[float, float]] = []
    for row in rows if isinstance(rows, list) else []:
        try:
            price, size = float(row["px"]), float(row["sz"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(price) and math.isfinite(size) and price > 0 and size > 0:
            out.append((price, size))
    return out


class DepthBooks:
    """The most recent book per (coin, aggregation), replaced by every message."""

    def __init__(self) -> None:
        self._books: dict[tuple[str, int], dict[str, Any]] = {}

    def ingest(self, n_sig_figs: int, message: Any, now_ms: int | None = None) -> bool:
        if not isinstance(message, dict) or message.get("channel") != "l2Book":
            return False
        data = message.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("coin"), str):
            return False
        levels = data.get("levels")
        if not isinstance(levels, list) or len(levels) != 2:
            return False
        bids, asks = parse_side(levels[0]), parse_side(levels[1])
        if not bids and not asks:
            return False
        received = now_ms if now_ms is not None else int(time.time() * 1000)
        venue_time = data.get("time")
        self._books[(data["coin"], n_sig_figs)] = {
            "time_ms": int(venue_time) if isinstance(venue_time, (int, float)) else received,
            "received_ms": received,
            "bids": bids,
            "asks": asks,
        }
        return True

    def latest(self, coin: str, now_ms: int | None = None) -> dict[str, dict[str, Any]]:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        books: dict[str, dict[str, Any]] = {}
        for n in AGGREGATIONS:
            book = self._books.get((coin, n))
            if book is None:
                continue
            age = now - book["received_ms"]
            books[str(n)] = {
                "n_sig_figs": n,
                "time_ms": book["time_ms"],
                "age_ms": age,
                "stale": age > STALE_AFTER_MS,
                "bids": [[price, size] for price, size in book["bids"]],
                "asks": [[price, size] for price, size in book["asks"]],
            }
        return books
