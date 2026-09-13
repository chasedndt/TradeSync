"""Volatility: realised volatility over the horizon's lookback, ranked against the past year."""

from __future__ import annotations

import math
from typing import Any

from ..horizon_outlook import Horizon
from ..horizon_stats import daily_volatility
from .base import Bars, Reading, series

YEAR = 365
MIN_RANKED = 120


class Volatility:
    key = "volatility"
    label = "Volatility"
    kind = "context"
    measures = "Realised volatility over the horizon's lookback, ranked against the past year: compressed, normal or elevated."

    def daily(self, bars: Bars, h: Horizon) -> list[float | None]:
        closes = bars.closes
        return [daily_volatility(closes[t - h.vol_lookback:t + 1], h.vol_lookback) if t >= h.vol_lookback else None
                for t in range(len(closes))]

    def ranks(self, bars: Bars, h: Horizon) -> list[float | None]:
        vols, out = self.daily(bars, h), []
        for t, v in enumerate(vols):
            past = [x for x in vols[max(0, t - YEAR):t + 1] if x is not None]
            out.append(None if v is None or len(past) < MIN_RANKED else sum(1 for x in past if x <= v) / len(past))
        return out

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return [None if r is None else "compressed" if r <= 0.25 else "elevated" if r >= 0.75 else "normal" for r in self.ranks(bars, h)]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        sigma, rank = self.daily(bars, h)[-1], self.ranks(bars, h)[-1]
        if sigma is None or rank is None:
            return Reading(None, "context", None, f"Needs {h.vol_lookback + MIN_RANKED} daily closes to rank volatility.")
        state = "compressed" if rank <= 0.25 else "elevated" if rank >= 0.75 else "normal"
        annual = sigma * math.sqrt(YEAR) * 100
        move = (math.exp(sigma * math.sqrt(h.days)) - 1) * 100
        return Reading(state, "context", round(annual, 1),
                       f"Realised volatility is {annual:.0f}% a year, {state} (percentile {rank * 100:.0f} of the past year); "
                       f"an ordinary {h.label} move is about {move:.1f}%.")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        vols = self.daily(bars, h)
        upper = [c * math.exp(v * math.sqrt(h.days)) if v else None for c, v in zip(bars.closes, vols)]
        lower = [c * math.exp(-v * math.sqrt(h.days)) if v else None for c, v in zip(bars.closes, vols)]
        return [series(f"one ordinary {h.label} move above", bars.times, upper, start, role="band_upper"),
                series(f"one ordinary {h.label} move below", bars.times, lower, start, role="band_lower")]


FEATURE = Volatility()
