"""Forward-return statistics on daily closes: the record behind a multi-horizon outlook.

Pure: closes in, numbers out. Consecutive days share almost all of a
six-month window, so every figure carries the number of independent
(non-overlapping) windows beside the number of days. That count, not the
days, says how far a figure can be trusted.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right, insort
from functools import lru_cache
from typing import Sequence


def forward_returns(closes: Sequence[float], days: int, last_complete: bool = True) -> list[float | None]:
    """``close[t + days] / close[t] - 1`` for each day; None where the window runs past the data.

    With ``last_complete=False`` the last close is a day still trading, so no
    window ends on it: its close is not yet the day's close.
    """
    n = len(closes)
    end = n if last_complete else n - 1
    out: list[float | None] = []
    for t in range(n):
        if t + days < end and closes[t] > 0:
            out.append(closes[t + days] / closes[t] - 1.0)
        else:
            out.append(None)
    return out


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile of an already sorted, non-empty sequence."""
    if not sorted_values:
        raise ValueError("quantile of no values")
    pos = (len(sorted_values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def independent_windows(indices: Sequence[int], days: int) -> int:
    """How many windows of ``days`` fit without overlapping, taking the earliest first."""
    count, next_free = 0, None
    for i in sorted(indices):
        if next_free is None or i >= next_free:
            count += 1
            next_free = i + days
    return count


def summarize(values: Sequence[float], indices: Sequence[int], days: int) -> dict[str, float | int | None]:
    """Share of windows that ended higher, the median and the 10/25/75/90th percentile moves, in percent."""
    if not values:
        return {"days": 0, "independent_windows": 0, "share_up": None, "median_pct": None, "median_abs_pct": None,
                "p10_pct": None, "p25_pct": None, "p75_pct": None, "p90_pct": None}
    ordered = sorted(values)

    def pct(q: float) -> float:
        return round(quantile(ordered, q) * 100, 2)

    return {
        "days": len(values),
        "independent_windows": independent_windows(indices, days),
        "share_up": round(sum(1 for v in values if v > 0) / len(values), 3),
        "median_pct": pct(0.5),
        "median_abs_pct": round(quantile(sorted(abs(v) for v in values), 0.5) * 100, 2),
        "p10_pct": pct(0.1),
        "p25_pct": pct(0.25),
        "p75_pct": pct(0.75),
        "p90_pct": pct(0.9),
    }


def moving_averages(closes: Sequence[float], n: int) -> list[float | None]:
    """Simple moving average ending on each day; None until ``n`` closes exist."""
    out: list[float | None] = []
    running = 0.0
    for t, close in enumerate(closes):
        running += close
        if t >= n:
            running -= closes[t - n]
        out.append(running / n if t >= n - 1 else None)
    return out


def rolling_extreme(values: Sequence[float], window: int, largest: bool = True) -> list[float | None]:
    """Highest (or lowest) value over the last ``window`` days, in one pass; None until the window is full."""
    from collections import deque

    out: list[float | None] = []
    kept: deque[int] = deque()
    for i, value in enumerate(values):
        while kept and ((values[kept[-1]] <= value) if largest else (values[kept[-1]] >= value)):
            kept.pop()
        kept.append(i)
        if kept[0] <= i - window:
            kept.popleft()
        out.append(values[kept[0]] if i >= window - 1 else None)
    return out


@lru_cache(maxsize=64)
def _rolling_volatility(closes: tuple[float, ...], lookback: int) -> tuple[float | None, ...]:
    out: list[float | None] = [None] * len(closes)
    returns = [0.0] + [math.log(b / a) if a > 0 and b > 0 else 0.0 for a, b in zip(closes, closes[1:])]
    total = squares = 0.0
    for t in range(1, len(closes)):
        r = returns[t]
        total += r
        squares += r * r
        if t > lookback:
            old = returns[t - lookback]
            total -= old
            squares -= old * old
        if t >= lookback:
            mean = total / lookback
            out[t] = math.sqrt(max(0.0, (squares - lookback * mean * mean) / (lookback - 1)))
    return tuple(out)


def rolling_volatility(closes: Sequence[float], lookback: int) -> list[float | None]:
    """``daily_volatility`` of the window ending on every day, in one pass (running sums); cached per series."""
    return list(_rolling_volatility(tuple(closes), lookback))


@lru_cache(maxsize=64)
def _rolling_rank(values: tuple[float | None, ...], window: int, min_count: int) -> tuple[float | None, ...]:
    kept: list[float] = []
    out: list[float | None] = []
    for t, value in enumerate(values):
        if value is not None:
            insort(kept, value)
        if t >= window:
            old = values[t - window]
            if old is not None:
                del kept[bisect_left(kept, old)]
        out.append(None if value is None or len(kept) < min_count else bisect_right(kept, value) / len(kept))
    return tuple(out)


def rolling_rank(values: Sequence[float | None], window: int, min_count: int) -> list[float | None]:
    """Share of the last ``window`` values (today included) at or below today's, once ``min_count`` exist; cached."""
    return list(_rolling_rank(tuple(values), window, min_count))


def daily_volatility(closes: Sequence[float], lookback: int) -> float | None:
    """Sample standard deviation of daily log returns over the last ``lookback`` days."""
    window = closes[-(lookback + 1):]
    returns = [math.log(b / a) for a, b in zip(window, window[1:]) if a > 0 and b > 0]
    if len(returns) < max(10, lookback // 2):
        return None
    mean = sum(returns) / len(returns)
    return math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
