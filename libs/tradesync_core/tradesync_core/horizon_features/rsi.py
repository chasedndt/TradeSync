"""RSI: Wilder's relative strength, on a period matched to the horizon."""

from __future__ import annotations

from typing import Any

from ..horizon_outlook import Horizon
from .base import Bars, Reading, series


def period_days(h: Horizon) -> int:
    """14 daily bars up to one month ahead; 98 daily bars for longer horizons, not weekly RSI."""
    return 14 if h.days <= 30 else 98


def wilder_rsi(closes: tuple[float, ...], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = [max(0.0, b - a) for a, b in zip(closes, closes[1:])]
    losses = [max(0.0, a - b) for a, b in zip(closes, closes[1:])]
    avg_gain, avg_loss = sum(gains[:period]) / period, sum(losses[:period]) / period
    for t in range(period, len(closes)):
        if t > period:
            avg_gain = (avg_gain * (period - 1) + gains[t - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[t - 1]) / period
        # Define the zero-gain/zero-loss case as neutral, not overbought.
        out[t] = (50.0 if avg_gain == 0 else 100.0) if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


class Rsi:
    key = "rsi"
    label = "RSI"
    kind = "context"
    measures = "Wilder's relative strength: 14 daily bars up to one month ahead, 98 daily bars for three and six months. This is not RSI calculated from weekly candles. Flat prices read neutral at 50. Above 70 is overbought, below 30 oversold."

    def values(self, bars: Bars, h: Horizon) -> list[float | None]:
        return wilder_rsi(bars.closes, period_days(h))

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return [None if v is None else "overbought" if v >= 70 else "oversold" if v <= 30 else "firm" if v >= 50 else "soft"
                for v in self.values(bars, h)]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        value = self.values(bars, h)[-1]
        if value is None:
            return Reading(None, "context", None, f"Needs {period_days(h) + 1} daily closes.")
        state = self.states(bars, h)[-1]
        scale = f"{period_days(h)}-day"
        return Reading(state, "context", round(value, 1), f"The {scale} RSI is {value:.0f}, {str(state).replace('_', ' ')}.")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        line = series(f"RSI ({period_days(h)} days)", bars.times, self.values(bars, h), start, role="oscillator", pane="lower")
        return [{**line, "guides": [30, 70], "range": [0, 100]}]


FEATURE = Rsi()
