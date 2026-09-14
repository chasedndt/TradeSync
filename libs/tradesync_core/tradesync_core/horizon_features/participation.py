"""Participation: recent traded volume against a longer average, from Hyperliquid's real trading only."""

from __future__ import annotations

from typing import Any

from ..horizon_spec import INTERVAL_WORDS, Horizon
from .base import Bars, Reading, series


class Participation:
    key = "participation"
    label = "Participation"
    kind = "context"
    measures = ("Traded volume over a recent window against a longer one (for example 2 against 24 hours for one hour ahead, "
                "7 against 30 days for a week), counting only real trading: the venue's daily history before February 2023 has no volume.")

    def ratios(self, bars: Bars, h: Horizon) -> list[float | None]:
        recent, base = h.participation
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
            out[-1] = out[-2]  # a bar still trading has only part of its volume: read through the last closed bar
        return out

    def states(self, bars: Bars, h: Horizon) -> list[str | None]:
        return [None if r is None else "rising" if r >= 1.2 else "fading" if r <= 0.8 else "steady" for r in self.ratios(bars, h)]

    def read(self, bars: Bars, h: Horizon) -> Reading:
        recent, base = h.participation
        ratio = self.ratios(bars, h)[-1]
        if ratio is None:
            return Reading(None, "context", None, f"Needs {base} bars of real traded volume.")
        state = self.states(bars, h)[-1]
        closed = " (closed bars only)" if bars.last_partial else ""
        return Reading(state, "context", round(ratio, 2),
                       f"Volume over the last {h.period(recent)}{closed} is {ratio:.2f} times its {h.span(base)} average, {state}.")

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]:
        recent, _ = h.participation
        volumes = bars.volumes
        average = [None if t < recent - 1 else sum(volumes[t - recent + 1:t + 1]) / recent for t in range(len(volumes))]
        shown = [v if v > 0 else None for v in volumes]
        return [series(f"{INTERVAL_WORDS[h.interval]} volume", bars.times, shown, start, kind="histogram", role="volume", pane="lower"),
                series(f"{h.span(recent)} average volume", bars.times, average, start, role="average", pane="lower")]


FEATURE = Participation()
