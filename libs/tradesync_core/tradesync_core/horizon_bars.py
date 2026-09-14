"""Bars for the multi-horizon outlook: OHLCV columns at one interval, sorted by time.

The same record-keeping reads 15-minute, hourly and daily bars; ``bar_seconds``
says which, and the last bar is marked partial while it is still trading so
no record window ends on an unfinished close.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

DAY = 86400


def bar_in_progress(last_time: int | float | None, now_s: float | None, bar_seconds: int = DAY) -> bool:
    """Whether a bar opened at ``last_time`` (epoch seconds) is still trading at ``now_s``."""
    return last_time is not None and now_s is not None and last_time + bar_seconds > now_s


def day_in_progress(last_time: int | float | None, now_s: float | None) -> bool:
    return bar_in_progress(last_time, now_s, DAY)


@dataclass(frozen=True)
class Bars:
    times: tuple[int, ...]
    opens: tuple[float, ...]
    highs: tuple[float, ...]
    lows: tuple[float, ...]
    closes: tuple[float, ...]
    volumes: tuple[float, ...]
    last_partial: bool = False  # the last bar is still trading
    bar_seconds: int = DAY

    @classmethod
    def from_candles(cls, candles: Sequence[Mapping[str, Any]], now_s: float | None = None, bar_seconds: int = DAY) -> "Bars":
        """Bars sorted by time; with ``now_s`` a last bar still trading is marked partial."""
        rows = sorted((c for c in candles if isinstance(c.get("close"), (int, float)) and c["close"] > 0), key=lambda c: c["time"])

        def column(name: str) -> tuple[float, ...]:
            return tuple(float(c[name]) if isinstance(c.get(name), (int, float)) else float(c["close"]) for c in rows)

        return cls(
            times=tuple(int(c["time"]) for c in rows),
            opens=column("open"), highs=column("high"), lows=column("low"), closes=column("close"),
            volumes=tuple(float(c.get("volume") or 0.0) if isinstance(c.get("volume"), (int, float)) else 0.0 for c in rows),
            last_partial=bool(rows) and bar_in_progress(int(rows[-1]["time"]), now_s, bar_seconds),
            bar_seconds=bar_seconds,
        )

    def __len__(self) -> int:
        return len(self.closes)
