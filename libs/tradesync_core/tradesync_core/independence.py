"""How much independent evidence a sample of overlapping windows really holds.

A verdict is recorded every minute and a 240-minute horizon covers four hours of
price. Two observations a few minutes apart share almost all of their window:
they are very nearly the same trade counted twice. Treating them as independent
understates the uncertainty, which is how a 74-observation sample once reported a
"significant" result.

The first correction estimated the effective sample as elapsed span divided by
horizon, times the number of symbols. Codex's review of 2026-09-09 found two
problems with that, both real:

- A span counts time, not evidence. Collection gaps and disjoint regime periods
  inside the span produce windows that were never observed.
- Counting each symbol as independent is generous. BTC, ETH and SOL move
  together, so three symbols in the same hour are not three separate facts.

This module replaces the estimate with measurements:

- ``independent_counts`` selects actually non-overlapping observations, per
  symbol and, as a conservative bound, with all symbols pooled into one stream.
- ``block_bootstrap_skill_se`` resamples whole time blocks one horizon long,
  with every symbol's observations kept together inside a block, so both the
  overlap between nearby windows and the correlation between symbols are
  carried into the error rather than assumed away.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable, Sequence

from .outcomes import expected_hit_rate


@dataclass(frozen=True)
class Observation:
    """One measured outcome, reduced to what skill measurement needs."""

    symbol: str
    opened_at_s: int
    direction: str  # LONG | SHORT
    forward_return_pct: float
    signed_return_pct: float

    @property
    def hit(self) -> bool:
        return self.signed_return_pct > 0

    @property
    def market_up(self) -> bool:
        return self.forward_return_pct > 0

    @property
    def is_long(self) -> bool:
        return self.direction == "LONG"


def non_overlapping(
    observations: Iterable[Observation],
    horizon_minutes: int,
    *,
    pool_symbols: bool = False,
) -> list[Observation]:
    """The largest set of observations whose windows do not overlap.

    Every window has the same length, so taking the earliest remaining window
    each time is optimal: no other selection holds more. The count is therefore
    not understated by the choice of greedy selection.

    With ``pool_symbols`` the symbols share one timeline, which treats BTC, ETH
    and SOL in the same window as a single piece of evidence. That is the
    conservative bound; the per-symbol count is the generous one.
    """
    if horizon_minutes <= 0:
        raise ValueError("horizon_minutes must be positive")
    horizon_s = horizon_minutes * 60

    streams: dict[str, list[Observation]] = {}
    for obs in observations:
        key = "*" if pool_symbols else obs.symbol
        streams.setdefault(key, []).append(obs)

    kept: list[Observation] = []
    for stream in streams.values():
        last_start: int | None = None
        for obs in sorted(stream, key=lambda o: (o.opened_at_s, o.symbol)):
            if last_start is None or obs.opened_at_s >= last_start + horizon_s:
                kept.append(obs)
                last_start = obs.opened_at_s
    return sorted(kept, key=lambda o: (o.opened_at_s, o.symbol))


def independent_counts(
    observations: Sequence[Observation], horizon_minutes: int
) -> dict[str, int]:
    """Measured independent windows: the generous and the conservative count."""
    return {
        "per_symbol": len(non_overlapping(observations, horizon_minutes)),
        "pooled": len(non_overlapping(observations, horizon_minutes, pool_symbols=True)),
    }


def skill_of(observations: Sequence[Observation]) -> dict[str, float] | None:
    """Hit rate, the base rate a guesser with the same bias would score, and the gap."""
    n = len(observations)
    if n == 0:
        return None
    hit_rate = sum(o.hit for o in observations) / n
    up_rate = sum(o.market_up for o in observations) / n
    long_share = sum(o.is_long for o in observations) / n
    expected = expected_hit_rate(up_rate, long_share)
    return {
        "hit_rate": hit_rate,
        "market_up_rate": up_rate,
        "long_share": long_share,
        "expected_hit_rate": expected,
        "skill": hit_rate - expected,
    }


def time_blocks(
    observations: Sequence[Observation], horizon_minutes: int
) -> list[list[Observation]]:
    """Consecutive, non-empty blocks one horizon long, all symbols together."""
    if horizon_minutes <= 0:
        raise ValueError("horizon_minutes must be positive")
    if not observations:
        return []
    horizon_s = horizon_minutes * 60
    origin = min(o.opened_at_s for o in observations)
    blocks: dict[int, list[Observation]] = {}
    for obs in observations:
        blocks.setdefault((obs.opened_at_s - origin) // horizon_s, []).append(obs)
    return [blocks[key] for key in sorted(blocks)]


def block_bootstrap_skill_se(
    observations: Sequence[Observation],
    horizon_minutes: int,
    *,
    draws: int = 1000,
    seed: int = 0,
) -> float | None:
    """Standard error of skill from resampling whole time blocks.

    Returns ``None`` with fewer than two blocks: one block resampled against
    itself has no variation to measure, and reporting zero would claim a
    certainty the sample does not have.

    Seeded, so the same sample always reports the same error.
    """
    blocks = time_blocks(observations, horizon_minutes)
    if len(blocks) < 2:
        return None
    rng = random.Random(seed)
    skills: list[float] = []
    for _ in range(draws):
        sample: list[Observation] = []
        for _ in range(len(blocks)):
            sample.extend(blocks[rng.randrange(len(blocks))])
        measured = skill_of(sample)
        if measured is not None:
            skills.append(measured["skill"])
    if len(skills) < 2:
        return None
    mean = sum(skills) / len(skills)
    variance = sum((s - mean) ** 2 for s in skills) / (len(skills) - 1)
    return math.sqrt(variance)


def binomial_se(effective_n: float) -> float | None:
    """Worst-case standard error of a proportion over ``effective_n`` observations.

    Uses p = 0.5, the largest possible variance, so it cannot flatter a sample
    whose hit rate happens to sit near 0 or 1.
    """
    if effective_n <= 0:
        return None
    return math.sqrt(0.25 / effective_n)
