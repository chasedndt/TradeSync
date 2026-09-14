"""The shape every horizon feature shares.

A feature reads bars at a horizon's scale and gives:

- ``states``: the bucket each past bar fell in (``above_rising``,
  ``overbought``...), so the record can ask what followed bars like today's;
- ``read``: today's state, a lean (``up``/``down``/``neutral`` for directional
  features, ``context`` otherwise), a value and one plain sentence;
- ``overlays``: how it is drawn, as data the chart renders (lines and bands on
  price, an oscillator or histogram in a lower pane, levels).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from ..horizon_bars import DAY, Bars, bar_in_progress, day_in_progress
from ..horizon_spec import Horizon

__all__ = ["DAY", "Bars", "HorizonFeature", "Reading", "bar_in_progress", "day_in_progress", "fmt_price", "series"]


@dataclass(frozen=True)
class Reading:
    state: str | None
    lean: str
    value: float | None
    text: str


class HorizonFeature(Protocol):
    key: str
    label: str
    kind: str
    measures: str

    def states(self, bars: Bars, h: Horizon) -> list[str | None]: ...

    def read(self, bars: Bars, h: Horizon) -> Reading: ...

    def overlays(self, bars: Bars, h: Horizon, start: int) -> list[dict[str, Any]]: ...


def series(label: str, times: Sequence[int], values: Sequence[float | None], start: int, *,
           kind: str = "line", role: str = "feature", pane: str = "price") -> dict[str, Any]:
    """A drawable series from ``start`` on, skipping bars without a value."""
    points = [[t, round(v, 8)] for t, v in zip(times[start:], values[start:]) if v is not None]
    return {"kind": kind, "label": label, "role": role, "pane": pane, "points": points}


def fmt_price(value: float) -> str:
    return f"{value:,.0f}" if value >= 1000 else f"{value:,.2f}" if value >= 1 else f"{value:.4g}"
