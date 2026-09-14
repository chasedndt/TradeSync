"""Aggregate attributions into evidence per feature, block, entry regime, symbol and horizon.

Every table is keyed by its dimension *and* the horizon, because a reading can
help at 60 minutes and mislead at 15.

For a feature or block the question is "when this reading took a stance, was it
right more often than chance?". The misled rate is ``misled / (supported +
misled)`` over decisive results only. Chance is not assumed to be one half:

- a directional reading is compared with the market direction, so chance is
  the agreement two independent up/down series with the same biases would reach
  (a reading that always points up in a rising week is not skilled);
- a suitability reading is compared with whether the call paid, the same way.

For an entry regime, symbol or horizon the calls themselves are judged: a win is
``supported``, a loss beyond costs ``misled``, and chance is the hit rate a
guesser with the same long/short mix would score in the same market.

A verdict needs at least ``min_decided`` decisive results, a time-clustered
effective sample of at least ``min_effective``, and a Wilson interval (at the
effective size) that excludes chance. Otherwise it is ``no_evidence``. Intervals
are per group and not adjusted for the number of groups inspected; a verdict is
a reason to test a change, which walk-forward replay then does.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from .attribution import AGAINST_CALL, MISLED, NEUTRAL, SUPPORTED, WITH_CALL
from .attribution_reason import label_for
from .decision_contributions import DIRECTIONAL, SUITABILITY
from .learning_stats import (
    Z_95,
    effective_sample_size,
    expected_agreement,
    mean_interval,
    wilson_interval,
)
from .outcome_classification import NO_FOLLOW_THROUGH, WINS

HELPING = "helping"
HURTING = "hurting"
NO_EVIDENCE = "no_evidence"

FEATURE = "feature"
BLOCK = "block"
REGIME = "regime"
SYMBOL = "symbol"
HORIZON = "horizon"
DIMENSIONS = (FEATURE, BLOCK, REGIME, SYMBOL, HORIZON)


@dataclass(frozen=True)
class VerdictPolicy:
    min_decided: int = 50
    min_effective: float = 20.0
    z: float = Z_95

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GroupEvidence:
    dimension: str
    key: str
    label: str
    role: str | None
    horizon_minutes: int
    attributions: int
    decided: int
    supported: int
    misled: int
    neutral: int
    misled_rate: float | None
    misled_low: float | None
    misled_high: float | None
    chance_misled_rate: float | None
    weighted_misled_share: float | None
    effective_samples: float
    mean_net_return_pct: float | None
    mean_net_agreed_pct: float | None
    agreed: int
    mean_net_disagreed_pct: float | None
    disagreed: int
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            key: round(value, 6) if isinstance(value, float) else value
            for key, value in asdict(self).items()
        }


@dataclass(frozen=True)
class _Obs:
    opened_at_s: int
    net: float
    won: bool
    long_call: bool
    stance: str
    verdict: str
    role: str
    size: float


def _observations(rows: Sequence[Mapping[str, Any]], dimension: str) -> dict[tuple[str, str, int], list[_Obs]]:
    """Group observations by (key, role, horizon).

    A reading is grouped by its role as well as its id: a feature recorded as
    suitability evidence before the catalog made it directional answered a
    different question then, and pooling the two would blur both.
    """
    groups: dict[tuple[str, str, int], list[_Obs]] = {}
    for row in rows:
        horizon = int(row["horizon_minutes"])
        won = row["classification"] in WINS
        decided = row["classification"] != NO_FOLLOW_THROUGH
        common = (int(row["opened_at_s"]), float(row["net_return_pct"]), won, row["direction"] == "LONG")
        if dimension in (FEATURE, BLOCK):
            for item in row.get("features" if dimension == FEATURE else "blocks") or []:
                role = str(item.get("role") or SUITABILITY)
                obs = _Obs(*common, str(item.get("stance")), str(item.get("verdict")),
                           role, abs(float(item.get("contribution") or 0.0)))
                groups.setdefault((str(item.get("id")), role, horizon), []).append(obs)
            continue
        key = {REGIME: row.get("entry_regime") or "unknown", SYMBOL: row["symbol"], HORIZON: f"{horizon}m"}[dimension]
        verdict = SUPPORTED if won else (MISLED if decided else NEUTRAL)
        groups.setdefault((str(key), "", horizon), []).append(_Obs(*common, WITH_CALL, verdict, DIRECTIONAL, 1.0))
    return groups


def _chance_misled(judged: Sequence[_Obs]) -> float | None:
    """Misled rate expected if stance and result were unrelated, by role."""
    parts = []
    for role in (DIRECTIONAL, SUITABILITY):
        subset = [o for o in judged if o.role == role]
        if not subset:
            continue
        n = len(subset)
        if role == DIRECTIONAL:
            pointed_up = sum((o.stance == WITH_CALL) == o.long_call for o in subset) / n
            market_up = sum(o.won == o.long_call for o in subset) / n
            parts.append((n, expected_agreement(pointed_up, market_up)))
        else:
            favourable = sum(o.stance == WITH_CALL for o in subset) / n
            wins = sum(o.won for o in subset) / n
            parts.append((n, expected_agreement(favourable, wins)))
    if not parts:
        return None
    total = sum(n for n, _ in parts)
    return 1.0 - sum(n * agreement for n, agreement in parts) / total


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _group(dimension: str, key: str, role: str, horizon: int, obs: Sequence[_Obs], policy: VerdictPolicy) -> GroupEvidence:
    judged = [o for o in obs if o.verdict in (SUPPORTED, MISLED)]
    misled = sum(o.verdict == MISLED for o in judged)
    decided = len(judged)
    ess = effective_sample_size([o.opened_at_s for o in judged], horizon) if judged else 0.0
    rate = misled / decided if decided else None
    interval = wilson_interval(rate, ess, policy.z) if rate is not None and ess > 0 else None
    chance = _chance_misled(judged)
    size_total = sum(o.size for o in judged)
    weighted = sum(o.size for o in judged if o.verdict == MISLED) / size_total if size_total > 0 else None

    verdict = NO_EVIDENCE
    if interval and chance is not None and decided >= policy.min_decided and ess >= policy.min_effective:
        if interval[0] > chance:
            verdict = HURTING
        elif interval[1] < chance:
            verdict = HELPING

    per_reading = dimension in (FEATURE, BLOCK)
    agreed = [o.net for o in obs if o.stance == WITH_CALL]
    disagreed = [o.net for o in obs if o.stance == AGAINST_CALL]
    mean_all = mean_interval([o.net for o in obs], ess)
    return GroupEvidence(
        dimension=dimension,
        key=key,
        label=label_for(key) if per_reading else key,
        role=role if per_reading else None,
        horizon_minutes=horizon,
        attributions=len(obs),
        decided=decided,
        supported=decided - misled,
        misled=misled,
        neutral=len(obs) - decided,
        misled_rate=rate,
        misled_low=interval[0] if interval else None,
        misled_high=interval[1] if interval else None,
        chance_misled_rate=chance,
        weighted_misled_share=weighted if per_reading else None,
        effective_samples=ess,
        mean_net_return_pct=mean_all[0] if mean_all else None,
        mean_net_agreed_pct=_mean(agreed) if per_reading else None,
        agreed=len(agreed) if per_reading else 0,
        mean_net_disagreed_pct=_mean(disagreed) if per_reading else None,
        disagreed=len(disagreed) if per_reading else 0,
        verdict=verdict,
    )


def aggregate(
    rows: Sequence[Mapping[str, Any]], dimension: str, policy: VerdictPolicy | None = None
) -> list[GroupEvidence]:
    """Evidence for every (key, horizon) group of one dimension, deterministic order."""

    if dimension not in DIMENSIONS:
        raise ValueError(f"unknown dimension {dimension!r}")
    policy = policy or VerdictPolicy()
    groups = _observations(rows, dimension)
    return [
        _group(dimension, key, role, horizon, groups[(key, role, horizon)], policy)
        for key, role, horizon in sorted(groups, key=lambda item: (item[2], item[0], item[1]))
    ]


def aggregate_all(
    rows: Sequence[Mapping[str, Any]], policy: VerdictPolicy | None = None
) -> dict[str, list[dict[str, Any]]]:
    return {dimension: [g.to_dict() for g in aggregate(rows, dimension, policy)] for dimension in DIMENSIONS}
