"""Participation: recent traded volume against a longer average, from Hyperliquid's real trading only."""

from __future__ import annotations

from typing import Any

from ..horizon_outlook import Horizon
from .base import Bars, Reading, series

# (recent, baseline) days by band.
WINDOWS = {"lower": (7, 30), "medium": (30, 90), "higher": (90, 365)}


class Participation:
    key = "participation"
    label = "Participation"
    kind = "context"
    measures = ("Traded volume over a recent window against a longer one (7 against 30 days, 30 against 90, or 90 against 365), "
                "counting only real trading: the venue's history before February 2023 has no volume.")

    def ratios(self, bars: Bars, h: Horizon) -> list[float | None]:
        recent, base = WINDOWS[h.band]
        volumes, out, running = bars.volumes, [], [0.0]
        for v in volumes:
            running.append(running[-1] + v)
        for t in range(len(volumes)):
            if t < base - 1 or min(volumes[t - base + 1:t + 1]) <= 0:
                out.append(None)
                continue
            recent_mean = (running[t + 1] - running[t + 1 - recent]) / recent
            base_mean = (running[t + 1] - running[t + 1 - base]) / base
            out.append(recent_mean / base_mean if base_mean > 0 else None)
        if bars.last_partial and len(out) >= 2:
            out[-1] = out[-2]  # a day still trading has only part of its volume: read through the last closed day
        return out

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return [None if r is None else "rising" if r >= 1.2 else "fading" if r <= 0.8 else "steady" for r in self.ratios(bars, h)]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        recent, base = WINDOWS[h.band]
        ratio = self.ratios(bars, h)[-1]
        if ratio is None:
            return Reading(None, "context", None, f"Needs {base} days of real traded volume.")
        state = self.states(bars, h)[-1]
        return Reading(state, "context", round(ratio, 2),
                       f"Volume over the last {recent} {'closed ' if bars.last_partial else ''}days is {ratio:.2f} times its {base}-day average, {state}.")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        recent, _ = WINDOWS[h.band]
        volumes = bars.volumes
        average = [None if t < recent - 1 else sum(volumes[t - recent + 1:t + 1]) / recent for t in range(len(volumes))]
        shown = [v if v > 0 else None for v in volumes]
        return [series("daily volume", bars.times, shown, start, kind="histogram", role="volume", pane="lower"),
                series(f"{recent}-day average volume", bars.times, average, start, role="average", pane="lower")]


FEATURE = Participation()
