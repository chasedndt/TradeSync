"""Funding: Hyperliquid's hourly funding rate against its own recent range.

High funding means longs are paying shorts more than usual (crowded longs);
unusually low or negative funding means the reverse. Read on the horizon's own
bars: the rate in force at each short bar's close, or the day's mean for daily
bars, ranked among the horizon's ranking window.
"""

from __future__ import annotations

from typing import Any

from ..horizon_spec import Horizon
from ..horizon_stats import rolling_rank
from .base import Bars, Reading, series

MIN_RANKED = 120
HOURS_A_YEAR = 24 * 365


def state_of(rank: float) -> str:
    return "elevated" if rank >= 0.8 else "depressed" if rank <= 0.2 else "normal"


class Funding:
    key = "funding"
    label = "Funding"
    kind = "context"
    measures = ("Hyperliquid's hourly funding rate against its own recent range (30 to 60 days for the short term, a year for longer "
                "horizons): elevated when longs pay more than usual, depressed when they pay less or shorts pay.")

    def values(self, bars: Bars, h: Horizon) -> list[float | None]:
        return list(bars.extra("funding_rate"))

    def ranks(self, bars: Bars, h: Horizon) -> list[float | None]:
        return rolling_rank(tuple(self.values(bars, h)), h.rank_bars, MIN_RANKED)

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return [None if r is None else state_of(r) for r in self.ranks(bars, h)]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        rate, rank = self.values(bars, h)[-1], self.ranks(bars, h)[-1]
        if rate is None or rank is None:
            return Reading(None, "context", None, f"Needs {MIN_RANKED} bars with Hyperliquid funding history.")
        state = state_of(rank)
        annual = rate * HOURS_A_YEAR * 100
        payer = "longs pay shorts" if rate > 0 else "shorts pay longs" if rate < 0 else "nobody pays"
        words = {"elevated": "higher than usual", "depressed": "lower than usual", "normal": "within its usual range"}[state]
        return Reading(state, "context", round(annual, 2),
                       f"Funding is {annual:+.1f}% a year ({rate * 100:+.4f}% an hour, {payer}), percentile {rank * 100:.0f} "
                       f"of the past {h.period(h.rank_bars)}: {words}.")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        annual = [None if v is None else v * HOURS_A_YEAR * 100 for v in self.values(bars, h)]
        line = series("funding, % a year", bars.times, annual, start, role="funding", pane="lower")
        return [{**line, "guides": [0]}] if line["points"] else []


FEATURE = Funding()
