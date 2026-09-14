"""Resting liquidity over time from recorded aggregated order books: the data behind the liquidity heatmap.

Each recorded book (one a minute, 20 aggregated levels a side) falls in a time
bucket; a cell is the average resting notional (price × size) at that price
level across the bucket's books. Bids and asks stay separate, so the page can
show where liquidity rests below and above price and where it builds up.
Displayed orders can be cancelled: this is what was resting, not what would
have filled, and not liquidation levels.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any, Mapping, Sequence

# window -> (span seconds, bucket seconds, aggregation): near price for short windows, wide for long ones.
WINDOWS: dict[str, tuple[int, int, int]] = {
    "6h": (6 * 3600, 300, 3),
    "24h": (86400, 900, 3),
    "3d": (3 * 86400, 3600, 3),
    "7d": (7 * 86400, 2 * 3600, 2),
    "30d": (30 * 86400, 8 * 3600, 2),
}
WALL_RANGE = 0.05


def _epoch(value: Any) -> float:
    return value.timestamp() if isinstance(value, datetime) else float(value)


def _key(price: float) -> float:
    return float(f"{price:.8g}")


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    pos = (len(sorted_values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def build(rows: Sequence[Mapping[str, Any]], bucket_seconds: int, start_s: int, end_s: int) -> dict[str, Any]:
    """Average resting notional per (time bucket, price level), bids and asks apart, from recorded books."""
    n_buckets = max(1, math.ceil((end_s - start_s) / bucket_seconds))
    times = [start_s + i * bucket_seconds for i in range(n_buckets)]
    sums: dict[tuple[int, float], list[float]] = defaultdict(lambda: [0.0, 0.0])
    books = [0] * n_buckets
    mids: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        t = int((_epoch(row["observed_at"]) - start_s) // bucket_seconds)
        if not 0 <= t < n_buckets:
            continue
        books[t] += 1
        if row.get("mid_price"):
            mids[t].append(float(row["mid_price"]))
        for side, index in (("bids", 0), ("asks", 1)):
            for price, size in row.get(side) or []:
                sums[(t, _key(float(price)))][index] += float(price) * float(size)
    prices = sorted({price for _, price in sums})
    position = {price: i for i, price in enumerate(prices)}
    bids: list[list[float]] = []
    asks: list[list[float]] = []
    values: list[float] = []
    for (t, price), (bid_usd, ask_usd) in sorted(sums.items()):
        for amount, out in ((bid_usd, bids), (ask_usd, asks)):
            if amount > 0:
                average = amount / books[t]
                out.append([t, position[price], round(average)])
                values.append(average)
    values.sort()
    steps = sorted(b - a for a, b in zip(prices, prices[1:]) if b > a)
    return {
        "bucket_seconds": bucket_seconds,
        "times": times,
        "prices": prices,
        "price_step": steps[len(steps) // 2] if steps else None,
        "bids": bids,
        "asks": asks,
        "mid": [[times[t], round(sum(m) / len(m), 8)] for t, m in sorted(mids.items())],
        "books_per_bucket": books,
        "max_usd": round(values[-1]) if values else 0,
        "p95_usd": round(_quantile(values, 0.95)) if values else 0,
    }


def walls(bids: Sequence[Sequence[float]], asks: Sequence[Sequence[float]], mid: float, within: float = WALL_RANGE) -> dict[str, Any]:
    """The largest resting bid below and ask above price within ``within`` of it, and the bid/ask balance there."""
    def largest(levels: Sequence[Sequence[float]], above: bool) -> dict[str, float] | None:
        near = [(float(p), float(p) * float(s)) for p, s in levels
                if (mid < float(p) <= mid * (1 + within) if above else mid * (1 - within) <= float(p) < mid)]
        if not near:
            return None
        price, usd = max(near, key=lambda level: level[1])
        return {"price": price, "usd": round(usd), "distance_bps": round((price / mid - 1) * 10_000, 1)}

    bid_usd = sum(float(p) * float(s) for p, s in bids if mid * (1 - within) <= float(p) < mid)
    ask_usd = sum(float(p) * float(s) for p, s in asks if mid < float(p) <= mid * (1 + within))
    total = bid_usd + ask_usd
    return {"below": largest(bids, above=False), "above": largest(asks, above=True),
            "bid_usd": round(bid_usd), "ask_usd": round(ask_usd),
            "imbalance": round((bid_usd - ask_usd) / total, 4) if total > 0 else None, "within_pct": within * 100}
