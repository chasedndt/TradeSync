"""Measured return correlation between tracked perps, and the exposure buckets it implies.

Buckets are derived, never listed. Two symbols share a bucket when the absolute
correlation of their closed hourly log returns reaches the operator's threshold,
and a bucket is a connected group of such links. Absolute, because a long in one
market and a short in a market moving opposite to it add risk rather than hedge
it. A symbol without enough overlapping history is reported as unmeasured rather
than assumed independent; the entry gate treats that as unavailable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

BAR_INTERVAL = "1h"
BAR_SECONDS = 3600
WINDOW_BARS = 168  # seven days of closed hourly bars
MIN_OVERLAP = 120  # shared returns needed before a correlation is stated
MAX_AGE_S = 3 * 3600  # an older measurement refuses entries rather than guessing


def closed_returns(candles: Iterable[Mapping[str, Any]], now_s: float, *, window: int = WINDOW_BARS) -> dict[int, float]:
    """Log returns of the latest closed bars, keyed by bar open time; only contiguous bars count."""
    closes: dict[int, float] = {}
    for candle in candles:
        at, close = candle.get("time"), candle.get("close")
        if isinstance(at, bool) or not isinstance(at, (int, float)) or isinstance(close, bool) or not isinstance(close, (int, float)):
            continue
        if not math.isfinite(close) or close <= 0 or at + BAR_SECONDS > now_s:
            continue
        closes[int(at)] = float(close)
    times = sorted(closes)[-(window + 1):]
    return {b: math.log(closes[b] / closes[a]) for a, b in zip(times, times[1:]) if b - a == BAR_SECONDS}


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))


def measure(candles_by_symbol: Mapping[str, Iterable[Mapping[str, Any]]], now_s: float, *, min_overlap: int = MIN_OVERLAP) -> dict[str, Any]:
    """Pairwise correlation over shared closed bars, in the universe's order."""
    symbols = list(candles_by_symbol)
    returns = {symbol: closed_returns(candles_by_symbol[symbol], now_s) for symbol in symbols}
    matrix: dict[str, dict[str, float | None]] = {s: {} for s in symbols}
    overlaps: dict[str, dict[str, int]] = {s: {} for s in symbols}
    for i, a in enumerate(symbols):
        for b in symbols[i:]:
            shared = sorted(set(returns[a]) & set(returns[b]))
            value = None
            if len(shared) >= min_overlap:
                value = pearson([returns[a][t] for t in shared], [returns[b][t] for t in shared])
                value = None if value is None else round(value, 6)
            matrix[a][b] = matrix[b][a] = value
            overlaps[a][b] = overlaps[b][a] = len(shared)
    unmeasured = [s for s in symbols if len(returns[s]) < min_overlap or matrix[s][s] is None]
    return {"bar_interval": BAR_INTERVAL, "window_bars": WINDOW_BARS, "min_overlap": min_overlap,
            "symbols": symbols, "matrix": matrix, "overlaps": overlaps, "unmeasured": unmeasured}


def buckets(symbols: Sequence[str], matrix: Mapping[str, Mapping[str, float | None]], threshold: float,
            unmeasured: Iterable[str] = ()) -> list[list[str]]:
    """Connected groups of symbols whose absolute correlation reaches ``threshold``."""
    skipped = set(unmeasured)
    members = [s for s in symbols if s not in skipped]
    parent = {s: s for s in members}

    def root(symbol: str) -> str:
        while parent[symbol] != symbol:
            parent[symbol] = parent[parent[symbol]]
            symbol = parent[symbol]
        return symbol

    for i, a in enumerate(members):
        for b in members[i + 1:]:
            value = (matrix.get(a) or {}).get(b)
            if value is not None and abs(value) >= threshold:
                parent[root(b)] = root(a)
    groups: dict[str, list[str]] = {}
    for symbol in members:
        groups.setdefault(root(symbol), []).append(symbol)
    return list(groups.values())


@dataclass(frozen=True)
class BucketView:
    """What the entry gate needs from the latest measurement, at the current threshold."""

    measured_at: float
    groups: tuple[tuple[str, ...], ...]
    unmeasured: frozenset[str]

    def members(self, symbol: str) -> tuple[str, ...] | None:
        for group in self.groups:
            if symbol in group:
                return group
        return None

    def grouped(self) -> frozenset[str]:
        return frozenset(s for group in self.groups for s in group)


def bucket_view(measurement: Mapping[str, Any], measured_at: float, threshold: float) -> BucketView:
    groups = buckets(measurement["symbols"], measurement["matrix"], threshold, measurement.get("unmeasured") or ())
    return BucketView(measured_at, tuple(tuple(g) for g in groups), frozenset(measurement.get("unmeasured") or ()))
