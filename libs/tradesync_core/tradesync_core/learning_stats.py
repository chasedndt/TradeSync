"""Interval and sample-size arithmetic for outcome learning.

Two corrections matter more than any others when judging paper calls:

- **Overlap.** Verdicts arrive every minute and a 60 minute outcome window
  covers sixty of them. Calls a few minutes apart are nearly the same trade.
  ``effective_sample_size`` clusters observations into epoch-aligned time
  buckets one horizon long, with every symbol pooled into the same bucket
  (BTC, ETH and SOL in the same hour are not three facts), and returns the
  Kish effective count ``(sum n_k)^2 / sum n_k^2``. With one observation per
  bucket that is the plain count; with everything in one bucket it is one.
  It assumes observations inside a bucket are fully dependent, which is the
  conservative choice.
- **Small samples.** A proportion's interval uses the Wilson score method, which
  stays inside [0, 1] and behaves near 0 and 1 where the normal approximation
  does not. It is evaluated at the effective sample size, not the raw count.

Pure and deterministic.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

Z_95 = 1.959963984540054


def wilson_interval(
    proportion: float, n: float, z: float = Z_95
) -> tuple[float, float] | None:
    """Wilson score interval for ``proportion`` observed over ``n`` (may be fractional)."""

    if n <= 0 or not math.isfinite(n):
        return None
    p = min(max(float(proportion), 0.0), 1.0)
    z2 = z * z
    denominator = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denominator
    half = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denominator
    # At p = 0 or 1 the bound is exactly 0 or 1; say so rather than 0.9999...
    low = 0.0 if p == 0.0 else max(0.0, centre - half)
    high = 1.0 if p == 1.0 else min(1.0, centre + half)
    return low, high


def cluster_counts(opened_at_s: Iterable[int], horizon_minutes: int) -> dict[int, int]:
    """Observations per epoch-aligned time bucket one horizon wide."""

    if horizon_minutes <= 0:
        raise ValueError("horizon_minutes must be positive")
    width = horizon_minutes * 60
    counts: dict[int, int] = {}
    for opened in opened_at_s:
        bucket = int(opened) // width
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def effective_sample_size(opened_at_s: Iterable[int], horizon_minutes: int) -> float:
    """Kish effective count over time clusters one horizon wide, symbols pooled."""

    counts = cluster_counts(opened_at_s, horizon_minutes)
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return total * total / sum(count * count for count in counts.values())


def mean_interval(
    values: Sequence[float], effective_n: float, z: float = Z_95
) -> tuple[float, float | None, float | None] | None:
    """Mean with a normal interval whose standard error uses the effective count.

    Returns ``None`` for no values, and no interval bounds when fewer than two
    values or effective observations exist: a spread cannot be measured then.
    """

    n = len(values)
    if n == 0:
        return None
    mean = sum(values) / n
    if n < 2 or effective_n < 2:
        return mean, None, None
    variance = sum((value - mean) ** 2 for value in values) / (n - 1)
    half = z * math.sqrt(variance / effective_n)
    return mean, mean - half, mean + half


def expected_agreement(share_a: float, share_b: float) -> float:
    """How often two independent yes/no readings agree by chance.

    ``share_a * share_b + (1 - share_a) * (1 - share_b)``. With ``share_a`` the
    share of calls that pointed up and ``share_b`` the share of windows where
    the market went up, this is the hit rate a guesser with the same bias would
    score (``tradesync_core.outcomes.expected_hit_rate``).
    """

    return share_a * share_b + (1.0 - share_a) * (1.0 - share_b)
