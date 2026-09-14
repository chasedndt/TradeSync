"""Turn measured verdicts into a challenger rulebook, inside the rulebook's own limits.

A proposal is a draft, never an activation. It moves weights by bounded steps in
the direction the evidence points, and nothing else changes:

- a block judged ``hurting`` at the target horizon has its weight scaled down by
  ``step``, one judged ``helping`` scaled up. The set is renormalised to the sum
  the rulebook requires, and no block may exceed ``max_single_block_weight``;
- a *directional* feature judged hurting or helping has its multiplier scaled
  the same way, clamped to ``[feature_weight_min, feature_weight_max]``.
  Suitability features never set a side, so re-weighting them cannot change
  which calls are admitted; their verdicts are reported, not acted on;
- risk caps, normalisation and the admission policy are copied unchanged, and
  the parent's version and digest are recorded in ``lineage``.

Without a single verdict there is no proposal: weights are not changed for the
sake of changing them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from .decision_contributions import DIRECTIONAL
from .learning_aggregate import HELPING, HURTING, NO_EVIDENCE, GroupEvidence
from .regime_weights import RegimeRulebook, validate_rulebook

PROPOSAL_METHOD = "opportunity_learning_v1"
VERSION_MARKER = "-learn."


@dataclass(frozen=True)
class LearningLimits:
    step: float = 0.20
    feature_weight_min: float = 0.25
    feature_weight_max: float = 2.0

    def __post_init__(self) -> None:
        if not 0 < self.step < 1:
            raise ValueError("step must be between 0 and 1")
        if not 0 < self.feature_weight_min <= 1 <= self.feature_weight_max:
            raise ValueError("feature weight limits must bracket 1.0")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WeightChange:
    blocks: dict[str, dict[str, Any]] = field(default_factory=dict)
    features: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return any(abs(c["after"] - c["before"]) > 1e-9 for c in self.blocks.values()) or bool(self.features)

    def to_dict(self) -> dict[str, Any]:
        return {"blocks": self.blocks, "features": self.features}


def proposal_version(parent_version: str, stamp: str) -> str:
    """``1.0.0-learn.202609141200``; a learned parent does not grow a chain."""
    return f"{parent_version.split(VERSION_MARKER)[0]}{VERSION_MARKER}{stamp}"


def capped_normalise(weights: Mapping[str, float], cap: float, total: float = 1.0) -> dict[str, float]:
    """Scale to ``total`` with no weight above ``cap``; rounded to 6 dp, exact sum."""

    names = sorted(weights)
    raw = {name: max(0.0, float(weights[name])) for name in names}
    if not names or sum(raw.values()) <= 0:
        raise ValueError("weights must contain a positive value")
    if cap * len(names) < total - 1e-12:
        raise ValueError("cap is too small for the required total")
    fixed: dict[str, float] = {}
    while True:
        free = [name for name in names if name not in fixed]
        remaining = total - sum(fixed.values())
        free_sum = sum(raw[name] for name in free)
        share = {
            name: (raw[name] * remaining / free_sum if free_sum > 0 else remaining / len(free))
            for name in free
        }
        over = [name for name in free if share[name] > cap]
        if not over:
            result = {**fixed, **share}
            break
        for name in over:
            fixed[name] = cap
    rounded = {name: round(result[name], 6) for name in names}
    residual = total - sum(rounded.values())
    if residual:
        room = [n for n in names if 0 <= rounded[n] + residual <= cap]
        target = max(room, key=lambda n: (rounded[n], n))
        rounded[target] += residual
    return rounded


def _factor(verdict: str, step: float) -> float:
    return {HURTING: 1.0 - step, HELPING: 1.0 + step}.get(verdict, 1.0)


def propose_weight_change(
    baseline: RegimeRulebook,
    feature_groups: Sequence[GroupEvidence],
    block_groups: Sequence[GroupEvidence],
    horizon_minutes: int,
    limits: LearningLimits | None = None,
) -> WeightChange:
    limits = limits or LearningLimits()
    blocks = {g.key: g for g in block_groups if g.horizon_minutes == horizon_minutes}
    scaled = {name: weight * _factor(blocks[name].verdict if name in blocks else NO_EVIDENCE, limits.step)
              for name, weight in baseline.weights.items()}
    moved = any(scaled[name] != weight for name, weight in baseline.weights.items())
    cap = float(baseline.data["validation"]["max_single_block_weight"])
    target = float(baseline.data["validation"]["weight_sum"])
    after = capped_normalise(scaled, cap, target) if moved else dict(baseline.weights)
    block_changes = {
        name: {
            "before": weight,
            "after": after[name],
            "verdict": blocks[name].verdict if name in blocks else NO_EVIDENCE,
        }
        for name, weight in sorted(baseline.weights.items())
    }

    current = baseline.feature_weights
    feature_changes: dict[str, dict[str, Any]] = {}
    for group in sorted(feature_groups, key=lambda g: g.key):
        if group.horizon_minutes != horizon_minutes or group.role != DIRECTIONAL:
            continue
        if group.verdict not in (HURTING, HELPING):
            continue
        before = current.get(group.key, 1.0)
        new = min(max(before * _factor(group.verdict, limits.step), limits.feature_weight_min), limits.feature_weight_max)
        if abs(new - before) > 1e-9:
            feature_changes[group.key] = {"before": before, "after": round(new, 6), "verdict": group.verdict}
    return WeightChange(blocks=block_changes, features=feature_changes)


def hypothesis_text(change: WeightChange, horizon_minutes: int, cost_pct: float, label_of) -> str:
    def names(verdict: str) -> str:
        items = [label_of(k) for k, c in {**change.blocks, **change.features}.items() if c["verdict"] == verdict]
        return ", ".join(items)

    down, up = names(HURTING), names(HELPING)
    parts = []
    if down:
        parts.append(f"trust {down} less (misled more often than chance)")
    if up:
        parts.append(f"trust {up} more (right more often than chance)")
    return (
        f"At the {horizon_minutes}m horizon after {cost_pct:.2f}% round-trip costs, "
        + " and ".join(parts)
        + ". Expected: a higher mean net return on the newest decisions, which the walk-forward replay tests."
    )


def build_challenger(baseline: RegimeRulebook, change: WeightChange, version: str, hypothesis: str) -> RegimeRulebook:
    """A validated draft rulebook carrying the change and its lineage."""

    data = json.loads(json.dumps(baseline.data))
    data["version"] = version
    data["status"] = "draft"
    data["environment"] = "paper"
    data["purpose"] = hypothesis
    for name, detail in change.blocks.items():
        data["blocks"][name]["weight"] = detail["after"]
    weights = dict(baseline.feature_weights)
    weights.update({name: detail["after"] for name, detail in change.features.items()})
    weights = {name: value for name, value in sorted(weights.items()) if value != 1.0}
    if weights:
        data["feature_weights"] = weights
    else:
        data.pop("feature_weights", None)
    data["lineage"] = {
        "parent_version": baseline.version,
        "parent_digest": baseline.digest,
        "method": PROPOSAL_METHOD,
    }
    return validate_rulebook(data)
