"""Drawdown: how far the close is below its highest high of the past year."""

from __future__ import annotations

from typing import Any

from ..horizon_outlook import Horizon
from ..horizon_stats import rolling_extreme
from .base import Bars, Reading, fmt_price, series

YEAR = 365


class Drawdown:
    key = "drawdown"
    label = "Drawdown"
    kind = "context"
    measures = "How far the close is below its highest high of the past year: near the high, a pullback, a drawdown or a deep drawdown."

    def depths(self, bars: Bars) -> list[float | None]:
        highs = rolling_extreme(bars.highs, YEAR, largest=True)
        return [None if hi is None or hi <= 0 else c / hi - 1 for c, hi in zip(bars.closes, highs)]

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return [None if d is None else "near_high" if d > -0.05 else "pullback" if d > -0.2 else "drawdown" if d > -0.4 else "deep_drawdown"
                for d in self.depths(bars)]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        depth = self.depths(bars)[-1]
        highs = rolling_extreme(bars.highs, YEAR, largest=True)
        if depth is None or highs[-1] is None:
            return Reading(None, "context", None, f"Needs {YEAR} daily bars.")
        state = self.states(bars, h)[-1]
        words = {"near_high": "near", "pullback": "in a pullback from", "drawdown": "in a drawdown from", "deep_drawdown": "in a deep drawdown from"}
        return Reading(state, "context", round(depth * 100, 1),
                       f"The close is {abs(depth) * 100:.1f}% below the one-year high of {fmt_price(highs[-1])}, {words[str(state)]} it.")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        return [series("one-year high", bars.times, rolling_extreme(bars.highs, YEAR, largest=True), start, role="range_high")]


FEATURE = Drawdown()
