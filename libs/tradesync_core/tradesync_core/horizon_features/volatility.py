"""Volatility: realised volatility over the horizon's lookback, ranked against a longer stretch."""

from __future__ import annotations

import math
from typing import Any

from ..horizon_spec import Horizon
from ..horizon_stats import rolling_rank, rolling_volatility
from .base import Bars, Reading, series

MIN_RANKED = 120
YEAR_SECONDS = 365 * 86400


def state_of(rank: float) -> str:
    return "compressed" if rank <= 0.25 else "elevated" if rank >= 0.75 else "normal"


class Volatility:
    key = "volatility"
    label = "Volatility"
    kind = "context"
    measures = ("Realised volatility over the horizon's lookback, ranked against the past 30 to 60 days (short term) "
                "or year (longer horizons): compressed, normal or elevated.")

    def per_bar(self, bars: Bars, h: Horizon) -> list[float | None]:
        return rolling_volatility(bars.closes, h.vol_bars)

    def ranks(self, bars: Bars, h: Horizon) -> list[float | None]:
        # The latest volatility among the last rank_bars values, the latest included.
        return rolling_rank(self.per_bar(bars, h), h.rank_bars, MIN_RANKED)

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return [None if r is None else state_of(r) for r in self.ranks(bars, h)]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        sigma, rank = self.per_bar(bars, h)[-1], self.ranks(bars, h)[-1]
        if sigma is None or rank is None:
            return Reading(None, "context", None, f"Needs {h.vol_bars + MIN_RANKED} bars to rank volatility.")
        state = state_of(rank)
        annual = sigma * math.sqrt(YEAR_SECONDS / h.bar_seconds) * 100
        move = (math.exp(sigma * math.sqrt(h.steps)) - 1) * 100
        return Reading(state, "context", round(annual, 1),
                       f"Realised volatility is {annual:.0f}% a year, {state} (percentile {rank * 100:.0f} of the past {h.period(h.rank_bars)}); "
                       f"an ordinary {h.adjective} move is about {move:.1f}%.")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        vols = self.per_bar(bars, h)
        upper = [c * math.exp(v * math.sqrt(h.steps)) if v else None for c, v in zip(bars.closes, vols)]
        lower = [c * math.exp(-v * math.sqrt(h.steps)) if v else None for c, v in zip(bars.closes, vols)]
        return [series(f"one ordinary {h.adjective} move above", bars.times, upper, start, role="band_upper"),
                series(f"one ordinary {h.adjective} move below", bars.times, lower, start, role="band_lower")]


FEATURE = Volatility()
