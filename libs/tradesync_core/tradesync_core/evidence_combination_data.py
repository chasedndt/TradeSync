"""The decisions evidence combination learns from, and how they are split in time.

One ``Decision`` is one paper opportunity measured at one horizon: when it
opened, what the market then did, the regime at entry, the rulebook's
directional score, and each source's call at entry. A call is the sign of the
source's entry reading: +1 reads up, -1 reads down. A zero or missing reading
abstains, and an abstaining source is simply absent from ``calls``.

The outcome is the market's direction, not whether the paper call won: a window
whose forward return is above zero rose, below zero fell, and exactly zero
neither (it is excluded, and counted).

The split is chronological and purged, as in ``walk_forward``: the oldest
decisions fit, the newest are tested, and a fitting decision whose outcome
window reaches into the test period is dropped, so no price move is both
learned from and tested on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .independence import Observation, independent_counts
from .learning_stats import effective_sample_size

UP = 1
DOWN = -1
DEFAULT_HOLDOUT_FRACTION = 0.30


@dataclass(frozen=True)
class Decision:
    """One measured decision, reduced to what combination needs."""

    key: str
    symbol: str
    opened_at_s: int
    forward_return_pct: float
    regime: str = "unknown"
    calls: Mapping[str, int] = field(default_factory=dict)
    rulebook_score: float | None = None

    @property
    def moved(self) -> bool:
        """False for a window that closed exactly where it opened."""
        return self.forward_return_pct != 0

    @property
    def rose(self) -> bool:
        return self.forward_return_pct > 0

    @property
    def outcome(self) -> int:
        """1 when the market rose, 0 when it fell."""
        return 1 if self.rose else 0


def call_from_reading(value: float | None) -> int | None:
    """The sign of an entry reading as a call; zero, missing or non-finite abstains."""
    if value is None or not math.isfinite(value) or value == 0:
        return None
    return UP if value > 0 else DOWN


def effective_windows(decisions: Iterable[Decision], horizon_minutes: int) -> float:
    """Kish effective count over horizon-wide time clusters, symbols pooled.

    The same count opportunity learning uses (``learning_stats``): calls in the
    same horizon-long window are treated as one cluster of dependent evidence.
    """
    return effective_sample_size([d.opened_at_s for d in decisions], horizon_minutes)


def independent_windows(decisions: Sequence[Decision], horizon_minutes: int) -> dict[str, int]:
    """Non-overlapping windows actually observed, per symbol and pooled (``independence``)."""
    observations = [
        Observation(d.symbol, d.opened_at_s, "LONG", d.forward_return_pct, d.forward_return_pct)
        for d in decisions
    ]
    return independent_counts(observations, horizon_minutes)


@dataclass(frozen=True)
class Split:
    fit: tuple[Decision, ...]
    test: tuple[Decision, ...]
    purged: int
    flat_excluded: int


def chronological_split(
    decisions: Sequence[Decision],
    horizon_minutes: int,
    holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION,
) -> Split:
    """Oldest decisions fit, newest ``holdout_fraction`` test; never shuffled; purged at the boundary."""
    if not 0 < holdout_fraction < 1:
        raise ValueError("holdout_fraction must be between 0 and 1")
    if horizon_minutes <= 0:
        raise ValueError("horizon_minutes must be positive")
    moved = sorted((d for d in decisions if d.moved), key=lambda d: (d.opened_at_s, d.key))
    flat = sum(1 for d in decisions if not d.moved)
    if len(moved) < 2:
        return Split(tuple(moved), (), 0, flat)
    cut = len(moved) - math.ceil(len(moved) * holdout_fraction)
    fit, test = moved[:cut], moved[cut:]
    boundary = test[0].opened_at_s
    kept = [d for d in fit if d.opened_at_s + horizon_minutes * 60 <= boundary]
    return Split(tuple(kept), tuple(test), len(fit) - len(kept), flat)


def window_summary(decisions: Sequence[Decision], horizon_minutes: int) -> dict[str, Any]:
    """Size of one side of the split, as raw decisions and as independent evidence."""
    if not decisions:
        return {
            "decisions": 0,
            "first_opened_at_s": None,
            "last_opened_at_s": None,
            "effective_windows": 0.0,
            "independent_windows": {"per_symbol": 0, "pooled": 0},
            "rise_share": None,
        }
    opened = [d.opened_at_s for d in decisions]
    return {
        "decisions": len(decisions),
        "first_opened_at_s": min(opened),
        "last_opened_at_s": max(opened),
        "effective_windows": round(effective_windows(decisions, horizon_minutes), 3),
        "independent_windows": independent_windows(decisions, horizon_minutes),
        "rise_share": round(sum(d.rose for d in decisions) / len(decisions), 6),
    }
