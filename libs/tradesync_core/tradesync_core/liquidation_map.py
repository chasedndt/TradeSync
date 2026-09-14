"""Estimated liquidation levels from open-interest changes: the data behind the liquidation heatmap.

Open interest that rises during a bar is new positions, and every new contract
has a long side and a short side. Their liquidation prices are estimated from
the bar's typical price and an assumed spread of leverage: a long opened at P
with leverage L is forced out near P × (1 − 1/L + m), a short near
P × (1 + 1/L − m), where m is the maintenance margin. Open interest that falls
closes positions, removed in proportion across the estimated levels. A level
is cleared once price trades through it (a long level when a later bar's low
reaches it, a short level when a later high does). What remains, bar by bar,
is where leveraged positions would be forced out if price got there. It is an
estimate from open interest and assumptions, not observed orders.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

# (leverage, share of new open interest): an assumption, stated on every response.
DEFAULT_LEVERAGE: tuple[tuple[int, float], ...] = ((5, 0.15), (10, 0.30), (20, 0.25), (25, 0.12), (50, 0.12), (100, 0.06))
DEFAULT_MAINTENANCE = 0.005
PRICE_BINS = 240
CELL_FLOOR = 0.002  # cells under this share of the busiest cell are left out of the payload


@dataclass(frozen=True)
class Bar:
    time: int
    high: float
    low: float
    close: float
    open_interest_usd: float

    @property
    def typical(self) -> float:
        return (self.high + self.low + self.close) / 3


def liquidation_price(entry: float, leverage: float, maintenance: float, side: str) -> float:
    return entry * (1 - 1 / leverage + maintenance) if side == "long" else entry * (1 + 1 / leverage - maintenance)


class PriceGrid:
    """Geometric price bins, so every bin is the same percentage wide."""

    def __init__(self, low: float, high: float, bins: int = PRICE_BINS) -> None:
        self.low, self.high, self.bins = low, high, bins
        self._log = math.log(high / low)
        self.centres = [low * math.exp(self._log * (i + 0.5) / bins) for i in range(bins)]

    def index(self, price: float) -> int | None:
        if price <= self.low or price >= self.high:
            return None
        return min(self.bins - 1, int(math.log(price / self.low) / self._log * self.bins))


def grid_for(bars: Sequence[Bar], leverage: Sequence[tuple[int, float]], bins: int = PRICE_BINS) -> PriceGrid:
    """Wide enough for the lowest-leverage levels opened at the window's extremes."""
    widest = 1 / min(lev for lev, _ in leverage)
    return PriceGrid(min(b.low for b in bars) * (1 - widest * 1.05), max(b.high for b in bars) * (1 + widest * 1.05), bins)


def estimate(bars: Sequence[Bar], output_from: int = 0, leverage: Sequence[tuple[int, float]] = DEFAULT_LEVERAGE,
             maintenance: float = DEFAULT_MAINTENANCE, bins: int = PRICE_BINS) -> dict[str, Any]:
    """Estimated long and short liquidation notional per price bin, for every bar from ``output_from`` on."""
    if len(bars) < 2:
        return {"times": [], "prices": [], "cells": [], "max_usd": 0, "profile": {"long": [], "short": []}, "clusters": {"above": [], "below": []}}
    grid = grid_for(bars, leverage, bins)
    longs = [0.0] * bins
    shorts = [0.0] * bins
    frames: list[tuple[int, list[float], list[float]]] = []
    for i, bar in enumerate(bars):
        if i > 0:
            # Price traded through these levels during the bar: those positions were forced out.
            for b, centre in enumerate(grid.centres):
                if centre >= bar.low:
                    longs[b] = 0.0
                if centre <= bar.high:
                    shorts[b] = 0.0
            previous = bars[i - 1].open_interest_usd
            change = bar.open_interest_usd - previous
            if change > 0:
                for lev, share in leverage:
                    for side, book in (("long", longs), ("short", shorts)):
                        b = grid.index(liquidation_price(bar.typical, lev, maintenance, side))
                        if b is not None:
                            book[b] += change * share
            elif change < 0 and previous > 0:
                kept = max(0.0, 1 + change / previous)
                longs[:] = [v * kept for v in longs]
                shorts[:] = [v * kept for v in shorts]
        if i >= output_from:
            frames.append((i, list(longs), list(shorts)))

    busiest = max((max(max(l), max(s)) for _, l, s in frames), default=0.0)
    floor = busiest * CELL_FLOOR
    cells = [[t, b, round(l[b]), round(s[b])] for t, (_, l, s) in enumerate(frames) for b in range(bins) if l[b] > floor or s[b] > floor]
    last = bars[-1].close
    profile_long = [[round(grid.centres[b], 8), round(v)] for b, v in enumerate(longs) if v > floor]
    profile_short = [[round(grid.centres[b], 8), round(v)] for b, v in enumerate(shorts) if v > floor]

    def clusters(levels: list[list[float]], above: bool) -> list[dict[str, float]]:
        side = [lv for lv in levels if (lv[0] > last if above else lv[0] < last)]
        return [{"price": p, "usd": usd, "distance_pct": round((p / last - 1) * 100, 2)} for p, usd in sorted(side, key=lambda lv: -lv[1])[:3]]

    return {
        "times": [bars[i].time for i, _, _ in frames],
        "prices": [round(c, 8) for c in grid.centres],
        "cells": cells,
        "max_usd": round(busiest),
        "profile": {"price": last, "long": profile_long, "short": profile_short},
        "clusters": {"above": clusters(profile_short, above=True), "below": clusters(profile_long, above=False)},
        "assumptions": {"leverage": {str(lev): share for lev, share in leverage}, "maintenance_margin": maintenance},
    }


def skew(profile: dict[str, Any], within_pct: float = 3.0) -> float | None:
    """(short levels above − long levels below) / both, within ``within_pct`` of price: which side holds more forced-out positions nearby."""
    price = profile.get("price")
    if not price:
        return None
    above = sum(usd for p, usd in profile.get("short", []) if price < p <= price * (1 + within_pct / 100))
    below = sum(usd for p, usd in profile.get("long", []) if price * (1 - within_pct / 100) <= p < price)
    return round((above - below) / (above + below), 4) if above + below > 0 else None
