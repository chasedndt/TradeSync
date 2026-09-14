"""Trend: the close against its moving average at the horizon's scale, and that average's slope."""

from __future__ import annotations

from typing import Any

from ..horizon_outlook import slope_bars, trend_states
from ..horizon_spec import Horizon
from .base import Bars, Reading, fmt_price, series

WORDS = {"above_rising": "above a rising", "above_falling": "above a falling",
         "below_rising": "below a rising", "below_falling": "below a falling"}


class Trend:
    key = "trend"
    label = "Trend"
    kind = "directional"
    measures = ("The close against its average at the horizon's scale (5 to 48 hours for the short term; 20, 50 or 200 days "
                "for the lower, medium and higher time frames) and whether that average is rising.")

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return trend_states(bars.closes, h.ma_bars)[0]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        states, averages = trend_states(bars.closes, h.ma_bars)
        state, average = states[-1], averages[-1]
        if state is None or average is None:
            return Reading(None, "neutral", None, f"Needs {h.ma_bars + slope_bars(h.ma_bars)} bars.")
        distance = (bars.closes[-1] / average - 1) * 100
        lean = "up" if state == "above_rising" else "down" if state == "below_falling" else "neutral"
        return Reading(state, lean, round(distance, 2),
                       f"The close is {abs(distance):.1f}% {WORDS[state]} {h.span(h.ma_bars)} average ({fmt_price(average)}).")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        _, averages = trend_states(bars.closes, h.ma_bars)
        return [series(f"{h.span(h.ma_bars)} average", bars.times, averages, start, role="average")]


FEATURE = Trend()
