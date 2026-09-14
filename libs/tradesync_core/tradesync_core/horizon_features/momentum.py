"""Momentum: the move over the horizon's own length, in units of an ordinary move that long."""

from __future__ import annotations

import math
from typing import Any

from ..horizon_spec import Horizon
from ..horizon_stats import rolling_volatility
from .base import Bars, Reading, series


class Momentum:
    key = "momentum"
    label = "Momentum"
    kind = "directional"
    measures = "The change over the last stretch as long as the horizon (the last four hours for four hours ahead), against the size of an ordinary move that long."

    def scores(self, bars: Bars, h: Horizon) -> list[float | None]:
        closes, out = bars.closes, []
        sigmas = rolling_volatility(closes, h.vol_bars)
        for t in range(len(closes)):
            sigma = sigmas[t] if t >= max(h.steps, h.vol_bars) else None
            out.append(math.log(closes[t] / closes[t - h.steps]) / (sigma * math.sqrt(h.steps)) if sigma else None)
        return out

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return [None if z is None else "strong_up" if z >= 1 else "up" if z > 0 else "strong_down" if z <= -1 else "down"
                for z in self.scores(bars, h)]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        z = self.scores(bars, h)[-1]
        if z is None:
            return Reading(None, "neutral", None, f"Needs {max(h.steps, h.vol_bars) + 1} bars.")
        change = (bars.closes[-1] / bars.closes[-1 - h.steps] - 1) * 100
        state = self.states(bars, h)[-1]
        size = "a larger than ordinary" if abs(z) >= 1 else "a smaller than ordinary"
        return Reading(state, "up" if z > 0 else "down", round(change, 2),
                       f"{change:+.1f}% over the last {h.label}, {size} move for that length ({abs(z):.1f} times the usual size).")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        n = len(bars)
        if n <= h.steps:
            return []
        values: list[float | None] = [None] * n
        values[n - 1 - h.steps], values[n - 1] = bars.closes[n - 1 - h.steps], bars.closes[n - 1]
        change = (bars.closes[-1] / bars.closes[-1 - h.steps] - 1) * 100
        return [series(f"{change:+.1f}% over {h.label}", bars.times, values, min(start, n - 1 - h.steps), role="momentum")]


FEATURE = Momentum()
