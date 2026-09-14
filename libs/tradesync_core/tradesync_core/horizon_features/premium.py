"""Premium: Hyperliquid's mark price against its oracle price, against its own recent range.

A mark above the oracle means buyers are paying up on the venue (rich); below
it, sellers are pressing (cheap). Read on the horizon's own bars from the hourly
premium Hyperliquid publishes with funding.
"""

from __future__ import annotations

from typing import Any

from ..horizon_spec import Horizon
from ..horizon_stats import rolling_rank
from .base import Bars, Reading, series

MIN_RANKED = 120


def state_of(rank: float) -> str:
    return "rich" if rank >= 0.8 else "cheap" if rank <= 0.2 else "fair"


class Premium:
    key = "premium"
    label = "Premium"
    kind = "context"
    measures = ("Hyperliquid's hourly premium of mark over oracle price, in basis points, against its own recent range: "
                "rich when buyers pay up on the venue, cheap when sellers press.")

    def values(self, bars: Bars, h: Horizon) -> list[float | None]:
        return [None if v is None else v * 10_000 for v in bars.extra("oracle_premium")]

    def ranks(self, bars: Bars, h: Horizon) -> list[float | None]:
        return rolling_rank(tuple(self.values(bars, h)), h.rank_bars, MIN_RANKED)

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return [None if r is None else state_of(r) for r in self.ranks(bars, h)]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        bps, rank = self.values(bars, h)[-1], self.ranks(bars, h)[-1]
        if bps is None or rank is None:
            return Reading(None, "context", None, f"Needs {MIN_RANKED} bars with Hyperliquid premium history.")
        state = state_of(rank)
        side = "above" if bps > 0 else "below" if bps < 0 else "at"
        return Reading(state, "context", round(bps, 2),
                       f"The mark trades {abs(bps):.1f} bps {side} the oracle, percentile {rank * 100:.0f} of the past "
                       f"{h.period(h.rank_bars)}: {state}.")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        line = series("premium, bps", bars.times, self.values(bars, h), start, role="premium", pane="lower")
        return [{**line, "guides": [0]}] if line["points"] else []


FEATURE = Premium()
