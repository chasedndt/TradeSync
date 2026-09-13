"""The shape every horizon feature shares.

A feature reads daily bars at a horizon's scale and gives:

- ``states``: the bucket each past day fell in (``above_rising``,
  ``overbought``...), so the record can ask what followed days like today;
- ``read``: today's state, a lean (``up``/``down``/``neutral`` for directional
  features, ``context`` otherwise), a value and one plain sentence;
- ``overlays``: how it is drawn, as data the chart renders (lines and bands on
  price, an oscillator or histogram in a lower pane, levels).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from ..horizon_outlook import Horizon


DAY = 86400


def day_in_progress(last_time: int | float | None, now_s: float | None) -> bool:
    """Whether a daily bar opened at ``last_time`` (epoch seconds) is still trading at ``now_s``."""
    return last_time is not None and now_s is not None and last_time + DAY > now_s


@dataclass(frozen=True)
class Bars:
    times: tuple[int, ...]
    opens: tuple[float, ...]
    highs: tuple[float, ...]
    lows: tuple[float, ...]
    closes: tuple[float, ...]
    volumes: tuple[float, ...]
    last_partial: bool = False  # the last bar is today's, still trading

    @classmethod
    def from_candles(cls, candles: Sequence[Mapping[str, Any]], now_s: float | None = None) -> "Bars":
        """Bars sorted by time; with ``now_s`` a last bar still trading is marked partial."""
        rows = sorted((c for c in candles if isinstance(c.get("close"), (int, float)) and c["close"] > 0), key=lambda c: c["time"])

        def column(name: str) -> tuple[float, ...]:
            return tuple(float(c[name]) if isinstance(c.get(name), (int, float)) else float(c["close"]) for c in rows)

        return cls(
            times=tuple(int(c["time"]) for c in rows),
            opens=column("open"), highs=column("high"), lows=column("low"), closes=column("close"),
            volumes=tuple(float(c.get("volume") or 0.0) if isinstance(c.get("volume"), (int, float)) else 0.0 for c in rows),
            last_partial=bool(rows) and day_in_progress(int(rows[-1]["time"]), now_s),
        )

    def __len__(self) -> int:
        return len(self.closes)


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
    """A drawable series from ``start`` on, skipping days without a value."""
    points = [[t, round(v, 8)] for t, v in zip(times[start:], values[start:]) if v is not None]
    return {"kind": kind, "label": label, "role": role, "pane": pane, "points": points}


def fmt_price(value: float) -> str:
    return f"{value:,.0f}" if value >= 1000 else f"{value:,.2f}" if value >= 1 else f"{value:.4g}"
