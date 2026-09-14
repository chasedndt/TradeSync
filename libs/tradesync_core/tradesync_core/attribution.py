"""Explain one measured paper call: what it earned after costs, and which readings led it there.

For each measured horizon this produces:

- a result net of an explicit round-trip cost, and a classification
  (``tradesync_core.outcome_classification``);
- per-feature and per-block attribution. Every recorded reading is marked
  ``supported`` when it pointed the way the price then went beyond costs,
  ``misled`` when it pointed the other way, and ``neutral`` when it had no
  stance or the price stayed inside the cost band (a move that does not pay for
  the round trip is not evidence for or against any reading);
- a plain-English reason naming the readings that misled or supported the call,
  and the regime at entry (``tradesync_core.attribution_reason``).

What "pointed the way the price went" means depends on the reading's role. A
directional reading points up or down. A suitability reading says conditions
were favourable or unfavourable for taking the call: it is supported when a
favourable reading is followed by a win, or an unfavourable one by a loss.

Pure and deterministic, so the job that stores attributions and the replay that
tests weight proposals always reach the same result from the same inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .attribution_reason import label_for, reason_sentence
from .decision_contributions import (
    DIRECTIONAL,
    Contribution,
    DecisionContributions,
    contributions_from_decision,
)
from .outcome_classification import DEFAULT_ROUND_TRIP_COST_PCT, OutcomeClass, classify_outcome

SCHEMA_VERSION = "opportunity_attribution_v1"

SUPPORTED = "supported"
MISLED = "misled"
NEUTRAL = "neutral"

WITH_CALL = "with"
AGAINST_CALL = "against"
NO_STANCE = "none"

SIDES = ("LONG", "SHORT")
REGIMES = ("rising", "falling", "flat", "unknown")


class AttributionError(ValueError):
    """Raised for malformed input, never for a losing call."""


@dataclass(frozen=True)
class MeasuredHorizon:
    """The stored outcome columns one attribution needs."""

    horizon_minutes: int
    signed_return_pct: float
    max_favourable_pct: float | None = None
    max_adverse_pct: float | None = None


def stance_of(item: Contribution, direction: str) -> str:
    """Whether a reading pushed toward the call that was taken."""

    if item.contribution == 0:
        return NO_STANCE
    if item.role == DIRECTIONAL:
        points_long = item.contribution > 0
        return WITH_CALL if points_long == (direction == "LONG") else AGAINST_CALL
    return WITH_CALL if item.contribution > 0 else AGAINST_CALL


def judge(stance: str, outcome: OutcomeClass) -> str:
    """Supported when the reading's stance matched a decisive result."""

    if stance == NO_STANCE or not outcome.decided:
        return NEUTRAL
    return SUPPORTED if (stance == WITH_CALL) == outcome.won else MISLED


def _judged(items: tuple[Contribution, ...], direction: str, outcome: OutcomeClass):
    judged = []
    for item in items:
        stance = stance_of(item, direction)
        judged.append(
            {
                "id": item.key,
                "label": label_for(item.key),
                "block": item.block,
                "role": item.role,
                "score": round(item.score, 6),
                "quality": round(item.quality, 6),
                "weight": item.weight,
                "contribution": round(item.contribution, 6),
                "stance": stance,
                "verdict": judge(stance, outcome),
            }
        )
    return tuple(judged)


@dataclass(frozen=True)
class Attribution:
    opportunity_id: str
    symbol: str
    direction: str
    opened_at_s: int
    horizon_minutes: int
    outcome: OutcomeClass
    entry_regime: str
    reason: str
    features: tuple[dict[str, Any], ...]
    blocks: tuple[dict[str, Any], ...]
    rulebook_version: str | None
    rulebook_digest: str | None

    @property
    def classification(self) -> str:
        return self.outcome.classification

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "opportunity_id": self.opportunity_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "opened_at_s": self.opened_at_s,
            "horizon_minutes": self.horizon_minutes,
            **self.outcome.to_dict(),
            "entry_regime": self.entry_regime,
            "reason": self.reason,
            "features": [dict(item) for item in self.features],
            "blocks": [dict(item) for item in self.blocks],
            "rulebook_version": self.rulebook_version,
            "rulebook_digest": self.rulebook_digest,
        }


def attribute_outcome(
    *,
    opportunity_id: str,
    symbol: str,
    direction: str,
    opened_at_s: int,
    decision: Mapping[str, Any],
    measured: MeasuredHorizon,
    entry_regime: str | None = None,
    cost_pct: float = DEFAULT_ROUND_TRIP_COST_PCT,
    contributions: DecisionContributions | None = None,
) -> Attribution:
    """Classify, attribute and explain one opportunity at one measured horizon.

    ``contributions`` may be passed when the same decision is attributed at
    several horizons, so it is split once rather than once per horizon.
    """

    if direction not in SIDES:
        raise AttributionError(f"direction {direction!r} has no side to attribute")
    if not opportunity_id:
        raise AttributionError("opportunity_id is required")
    if measured.horizon_minutes <= 0:
        raise AttributionError("horizon_minutes must be positive")

    outcome = classify_outcome(
        measured.signed_return_pct,
        measured.max_favourable_pct,
        measured.max_adverse_pct,
        cost_pct,
    )
    parts = contributions if contributions is not None else contributions_from_decision(decision)
    features = _judged(parts.features, direction, outcome)
    blocks = _judged(parts.blocks, direction, outcome)
    regime = entry_regime if entry_regime in REGIMES else "unknown"
    return Attribution(
        opportunity_id=str(opportunity_id),
        symbol=symbol,
        direction=direction,
        opened_at_s=int(opened_at_s),
        horizon_minutes=int(measured.horizon_minutes),
        outcome=outcome,
        entry_regime=regime,
        reason=reason_sentence(symbol, direction, measured.horizon_minutes, outcome, features, regime),
        features=features,
        blocks=blocks,
        rulebook_version=parts.rulebook_version,
        rulebook_digest=parts.rulebook_digest,
    )
