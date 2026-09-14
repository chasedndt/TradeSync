"""Range position: where the close sits between the low and the high of a lookback matched to the horizon."""

from __future__ import annotations

from typing import Any

from ..horizon_spec import Horizon
from ..horizon_stats import rolling_extreme
from .base import Bars, Reading, fmt_price, series


def state_of(position: float) -> str:
    return "near_high" if position >= 0.8 else "near_low" if position <= 0.2 else "middle"


class RangePosition:
    key = "range"
    label = "Range position"
    kind = "context"
    measures = "Where the close sits between the lowest low and highest high of a lookback matched to the horizon (one day for one hour ahead, two years for six months)."

    def _bounds(self, bars: Bars, h: Horizon) -> tuple[list[float | None], list[float | None]]:
        return rolling_extreme(bars.highs, h.range_bars, largest=True), rolling_extreme(bars.lows, h.range_bars, largest=False)

    def positions(self, bars: Bars, h: Horizon) -> list[float | None]:
        highs, lows = self._bounds(bars, h)
        return [None if hi is None or lo is None else ((c - lo) / (hi - lo) if hi > lo else 0.5)
                for c, hi, lo in zip(bars.closes, highs, lows)]

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return [None if p is None else state_of(p) for p in self.positions(bars, h)]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        highs, lows = self._bounds(bars, h)
        position, high, low = self.positions(bars, h)[-1], highs[-1], lows[-1]
        if position is None or high is None or low is None:
            return Reading(None, "context", None, f"Needs {h.range_bars} bars.")
        return Reading(state_of(position), "context", round(position * 100, 1),
                       f"The close sits {position * 100:.0f}% of the way up its {h.span(h.range_bars)} range, {fmt_price(low)} to {fmt_price(high)}.")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        highs, lows = self._bounds(bars, h)
        return [series(f"{h.span(h.range_bars)} high", bars.times, highs, start, role="range_high"),
                series(f"{h.span(h.range_bars)} low", bars.times, lows, start, role="range_low")]


FEATURE = RangePosition()
