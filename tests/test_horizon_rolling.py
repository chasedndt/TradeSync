"""The one-pass rolling volatility and rank give the same numbers as the day-by-day definitions."""

from __future__ import annotations

import math
import random

from tradesync_core.horizon_stats import daily_volatility, rolling_rank, rolling_volatility


def walk(n: int, seed: int = 7) -> list[float]:
    rng = random.Random(seed)
    closes, price = [], 100.0
    for _ in range(n):
        price *= math.exp(rng.gauss(0.0005, 0.03))
        closes.append(price)
    return closes


def test_rolling_volatility_matches_the_window_definition() -> None:
    closes = walk(800)
    for lookback in (30, 60, 365):
        fast = rolling_volatility(closes, lookback)
        for t in range(len(closes)):
            slow = daily_volatility(closes[t - lookback:t + 1], lookback) if t >= lookback else None
            if slow is None:
                assert fast[t] is None
            else:
                assert abs(fast[t] - slow) < 1e-9, (lookback, t)


def test_rolling_rank_matches_counting_the_window() -> None:
    rng = random.Random(3)
    values = [None if rng.random() < 0.05 else rng.random() for _ in range(900)]
    window, min_count = 366, 120
    fast = rolling_rank(values, window, min_count)
    for t, v in enumerate(values):
        past = [x for x in values[max(0, t - window + 1):t + 1] if x is not None]
        slow = None if v is None or len(past) < min_count else sum(1 for x in past if x <= v) / len(past)
        assert fast[t] == slow, t
