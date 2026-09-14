"""Drawdown: how far the close is below its highest high of a lookback matched to the horizon.

A one-year lookback for daily horizons (near the high within 5%, a pullback to
20%, a drawdown to 40%, deeper beyond). Shorter lookbacks scale those
thresholds by the square root of their length, so a 3% dip from the 7-day high
counts as a pullback rather than as being near the high.
"""

from __future__ import annotations

import math
from typing import Any

from ..horizon_spec import Horizon
from ..horizon_stats import rolling_extreme
from .base import Bars, Reading, fmt_price, series

YEAR_SECONDS = 365 * 86400
THRESHOLDS = (0.05, 0.2, 0.4)
WORDS = {"near_high": "near", "pullback": "in a pullback from", "drawdown": "in a drawdown from", "deep_drawdown": "in a deep drawdown from"}


def lookback_label(h: Horizon) -> str:
    return "one-year" if h.period(h.high_bars) == "year" else h.span(h.high_bars)


def thresholds(h: Horizon) -> tuple[float, float, float]:
    scale = min(1.0, math.sqrt(h.high_bars * h.bar_seconds / YEAR_SECONDS))
    return tuple(t * scale for t in THRESHOLDS)  # type: ignore[return-value]


class Drawdown:
    key = "drawdown"
    label = "Drawdown"
    kind = "context"
    measures = "How far the close is below its highest high of a lookback matched to the horizon (7 to 30 days short term, a year otherwise): near the high, a pullback, a drawdown or a deep drawdown."

    def depths(self, bars: Bars, h: Horizon) -> list[float | None]:
        highs = rolling_extreme(bars.highs, h.high_bars, largest=True)
        return [None if hi is None or hi <= 0 else c / hi - 1 for c, hi in zip(bars.closes, highs)]

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        near, pullback, drawdown = thresholds(h)
        return [None if d is None else "near_high" if d > -near else "pullback" if d > -pullback else "drawdown" if d > -drawdown else "deep_drawdown"
                for d in self.depths(bars, h)]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        depth = self.depths(bars, h)[-1]
        highs = rolling_extreme(bars.highs, h.high_bars, largest=True)
        if depth is None or highs[-1] is None:
            return Reading(None, "context", None, f"Needs {h.high_bars} bars.")
        state = self.states(bars, h)[-1]
        return Reading(state, "context", round(depth * 100, 1),
                       f"The close is {abs(depth) * 100:.1f}% below the {lookback_label(h)} high of {fmt_price(highs[-1])}, {WORDS[str(state)]} it.")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        return [series(f"{lookback_label(h)} high", bars.times, rolling_extreme(bars.highs, h.high_bars, largest=True), start, role="range_high")]


FEATURE = Drawdown()
