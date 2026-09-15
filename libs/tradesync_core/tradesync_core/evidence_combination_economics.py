"""What a probability must reach before a call pays its round trip.

If a long is taken when the chance of a rise is p, rises average U% and falls
average D% (both measured on the fitting windows), and the round trip costs c%,
the expected net return is

    p U - (1 - p) D - c

which is above zero only when p > (D + c) / (U + D). A short earns
(1 - p) D - p U - c, which needs p < (D - c) / (U + D). With U = D the long
threshold is 1/2 + c / 2U: the smaller the typical move, the nearer to
certainty a call must be before it pays. The move sizes are assumed not to
depend on p, which is a simplification stated wherever the thresholds are shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .evidence_combination_data import Decision
from .learning_stats import effective_sample_size, mean_interval


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def breakeven_probabilities(mean_rise_pct: float, mean_fall_pct: float, cost_pct: float) -> tuple[float, float]:
    """(long above, short below) for mean move magnitudes U and D and a round-trip cost c, all in percent."""
    if mean_rise_pct <= 0 or mean_fall_pct <= 0:
        raise ValueError("mean moves must be positive magnitudes")
    if cost_pct < 0:
        raise ValueError("cost_pct cannot be negative")
    total = mean_rise_pct + mean_fall_pct
    return (mean_fall_pct + cost_pct) / total, (mean_fall_pct - cost_pct) / total


@dataclass(frozen=True)
class Breakeven:
    cost_pct: float
    mean_rise_pct: float | None
    mean_fall_pct: float | None
    long_above: float | None
    short_below: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cost_pct": self.cost_pct,
            "mean_rise_pct": _round(self.mean_rise_pct),
            "mean_fall_pct": _round(self.mean_fall_pct),
            "long_above": _round(self.long_above),
            "short_below": _round(self.short_below),
            "assumption": "move sizes measured on the fitting windows and assumed not to depend on the probability",
        }


def breakeven(decisions: Sequence[Decision], cost_pct: float) -> Breakeven:
    rises = [d.forward_return_pct for d in decisions if d.forward_return_pct > 0]
    falls = [-d.forward_return_pct for d in decisions if d.forward_return_pct < 0]
    mean_rise = sum(rises) / len(rises) if rises else None
    mean_fall = sum(falls) / len(falls) if falls else None
    if mean_rise is None or mean_fall is None:
        return Breakeven(cost_pct, mean_rise, mean_fall, None, None)
    long_above, short_below = breakeven_probabilities(mean_rise, mean_fall, cost_pct)
    return Breakeven(cost_pct, mean_rise, mean_fall, long_above, short_below)


@dataclass(frozen=True)
class Clearance:
    decisions: int
    long_calls: int
    short_calls: int
    mean_net_return_pct: float | None
    low: float | None
    high: float | None
    effective_windows: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": self.decisions,
            "long_calls": self.long_calls,
            "short_calls": self.short_calls,
            "mean_net_return_pct": _round(self.mean_net_return_pct),
            "low": _round(self.low),
            "high": _round(self.high),
            "effective_windows": round(self.effective_windows, 3),
        }


def side_cleared(probability: float, threshold: Breakeven) -> str | None:
    """'long' above the long threshold, 'short' below the short one, None in between."""
    if threshold.long_above is not None and probability > threshold.long_above:
        return "long"
    if threshold.short_below is not None and probability < threshold.short_below:
        return "short"
    return None


def clearance(
    decisions: Sequence[Decision],
    probabilities: Sequence[float],
    threshold: Breakeven,
    horizon_minutes: int,
) -> Clearance:
    """Decisions whose probability cleared a threshold, and what the implied call returned after costs."""
    if len(decisions) != len(probabilities):
        raise ValueError("one probability per decision")
    nets: list[float] = []
    opened: list[int] = []
    long_calls = short_calls = 0
    for decision, probability in zip(decisions, probabilities):
        side = side_cleared(probability, threshold)
        if side == "long":
            long_calls += 1
            nets.append(decision.forward_return_pct - threshold.cost_pct)
        elif side == "short":
            short_calls += 1
            nets.append(-decision.forward_return_pct - threshold.cost_pct)
        else:
            continue
        opened.append(decision.opened_at_s)
    effective = effective_sample_size(opened, horizon_minutes) if opened else 0.0
    measured = mean_interval(nets, effective) if nets else None
    return Clearance(
        decisions=len(decisions),
        long_calls=long_calls,
        short_calls=short_calls,
        mean_net_return_pct=measured[0] if measured else None,
        low=measured[1] if measured else None,
        high=measured[2] if measured else None,
        effective_windows=effective,
    )
