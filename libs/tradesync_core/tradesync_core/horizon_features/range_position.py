"""Range position: where the close sits between the low and the high of a lookback matched to the horizon."""

from __future__ import annotations

from typing import Any

from ..horizon_outlook import Horizon
from ..horizon_stats import rolling_extreme
from .base import Bars, Reading, fmt_price, series

LOOKBACK_DAYS = {"3d": 20, "1w": 30, "2w": 60, "1m": 120, "3m": 365, "6m": 730}


class RangePosition:
    key = "range"
    label = "Range position"
    kind = "context"
    measures = "Where the close sits between the lowest low and highest high of a lookback matched to the horizon (20 days for three days ahead, two years for six months)."

    def _bounds(self, bars: Bars, h: Horizon) -> tuple[int, list[float | None], list[float | None]]:
        days = LOOKBACK_DAYS.get(h.key, h.days * 4)
        return days, rolling_extreme(bars.highs, days, largest=True), rolling_extreme(bars.lows, days, largest=False)

    def positions(self, bars: Bars, h: Horizon) -> list[float | None]:
        _, highs, lows = self._bounds(bars, h)
        return [None if hi is None or lo is None else ((c - lo) / (hi - lo) if hi > lo else 0.5)
                for c, hi, lo in zip(bars.closes, highs, lows)]

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return [None if p is None else "near_high" if p >= 0.8 else "near_low" if p <= 0.2 else "middle" for p in self.positions(bars, h)]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        days, highs, lows = self._bounds(bars, h)
        position, high, low = self.positions(bars, h)[-1], highs[-1], lows[-1]
        if position is None or high is None or low is None:
            return Reading(None, "context", None, f"Needs {days} daily bars.")
        state = "near_high" if position >= 0.8 else "near_low" if position <= 0.2 else "middle"
        return Reading(state, "context", round(position * 100, 1),
                       f"The close sits {position * 100:.0f}% of the way up its {days}-day range, {fmt_price(low)} to {fmt_price(high)}.")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        days, highs, lows = self._bounds(bars, h)
        return [series(f"{days}-day high", bars.times, highs, start, role="range_high"),
                series(f"{days}-day low", bars.times, lows, start, role="range_low")]


FEATURE = RangePosition()
