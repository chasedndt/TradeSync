"""Bars for the multi-horizon outlook: OHLCV columns at one interval, sorted by time.

The same record-keeping reads 15-minute, hourly and daily bars; ``bar_seconds``
says which, and the last bar is marked partial while it is still trading so
no record window ends on an unfinished close. ``extras`` carries other series
aligned to the bars, such as Hyperliquid's hourly funding rate and premium.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

DAY = 86400
HOUR = 3600
MAX_FUNDING_AGE_S = 2 * HOUR
MIN_HOURS_IN_DAY = 12


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
    extras: Mapping[str, tuple[float | None, ...]] = field(default_factory=dict, hash=False, compare=False)

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

    def extra(self, name: str) -> tuple[float | None, ...]:
        """An aligned series, or all None when it was not supplied."""
        return self.extras.get(name) or (None,) * len(self.closes)

    def __len__(self) -> int:
        return len(self.closes)


def align_hourly(times: Sequence[int], bar_seconds: int, rows: Sequence[Sequence[float]], column: int) -> tuple[float | None, ...]:
    """For each bar, the hourly value in force at its close (bars under a day) or the mean over the day (daily bars).

    ``rows`` are ``[time_s, value, ...]`` sorted by time. A value older than two
    hours at the bar's close is not carried forward, and a day needs at least
    twelve hourly values; otherwise the bar has none.
    """
    stamps = [int(r[0]) for r in rows]
    values = [float(r[column]) for r in rows]
    out: list[float | None] = []
    for t in times:
        close = t + bar_seconds
        if bar_seconds >= DAY:
            window = values[bisect_left(stamps, t):bisect_left(stamps, close)]
            out.append(sum(window) / len(window) if len(window) >= MIN_HOURS_IN_DAY else None)
        else:
            i = bisect_right(stamps, close) - 1
            out.append(values[i] if i >= 0 and close - stamps[i] <= MAX_FUNDING_AGE_S else None)
    return tuple(out)


def with_funding(bars: Bars, rows: Sequence[Sequence[float]]) -> Bars:
    """Bars carrying the hourly funding rate and premium aligned to them, from ``[time_s, rate, premium]`` rows."""
    if not rows:
        return bars
    ordered = sorted(rows, key=lambda r: r[0])
    return replace(bars, extras={
        **bars.extras,
        "funding_rate": align_hourly(bars.times, bars.bar_seconds, ordered, 1),
        "oracle_premium": align_hourly(bars.times, bars.bar_seconds, ordered, 2),
    })
