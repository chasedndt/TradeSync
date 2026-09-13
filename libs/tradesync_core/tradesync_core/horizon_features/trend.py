"""Trend: the close against its moving average at the horizon's scale, and that average's slope."""

from __future__ import annotations

from typing import Any

from ..horizon_outlook import Horizon, slope_days, trend_states
from .base import Bars, Reading, fmt_price, series

WORDS = {"above_rising": "above a rising", "above_falling": "above a falling",
         "below_rising": "below a rising", "below_falling": "below a falling"}


class Trend:
    key = "trend"
    label = "Trend"
    kind = "directional"
    measures = "The close against its 20, 50 or 200-day average (lower, medium or higher time frame) and whether that average is rising."

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return trend_states(bars.closes, h.ma_days)[0]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        states, averages = trend_states(bars.closes, h.ma_days)
        state, average = states[-1], averages[-1]
        if state is None or average is None:
            return Reading(None, "neutral", None, f"Needs {h.ma_days + slope_days(h.ma_days)} daily closes.")
        distance = (bars.closes[-1] / average - 1) * 100
        lean = "up" if state == "above_rising" else "down" if state == "below_falling" else "neutral"
        return Reading(state, lean, round(distance, 2),
                       f"The close is {abs(distance):.1f}% {WORDS[state]} {h.ma_days}-day average ({fmt_price(average)}).")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        _, averages = trend_states(bars.closes, h.ma_days)
        return [series(f"{h.ma_days}-day average", bars.times, averages, start, role="average")]


FEATURE = Trend()
