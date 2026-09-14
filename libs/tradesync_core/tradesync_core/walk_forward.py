"""Learn weights on older decisions, then test them on newer ones.

1. Decisions with a measured outcome at the target horizon are ordered by time.
   The oldest ``1 - holdout_fraction`` learn; the newest ``holdout_fraction``
   test. Never shuffled: a change has to survive data from after it was learned.
2. A learning decision whose outcome window reaches into the test period is
   purged, so no price move is both learned from and tested on.
3. Learning decisions are attributed and aggregated; the verdicts at the target
   horizon produce a proposal (``tradesync_core.learning_proposal``).
4. Every test decision is replayed under the baseline and under the proposal
   (``tradesync_core.decision_replay``). Each rulebook reports how many it
   admits, its hit rate after costs and its mean net return, with intervals at
   the time-clustered effective sample size.

Only decisions that were admitted and measured can be scored. A proposal that
would admit a decision the baseline refused has no outcome to score it on, so
the replay can show a proposal refusing or flipping calls, never inventing new
ones. The baseline replay should reproduce the stored decisions; the share it
does is reported, because a comparison against a baseline that does not
reproduce production is not a comparison with production.

Pure and deterministic: same records, same result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .attribution import MeasuredHorizon, attribute_outcome
from .attribution_reason import label_for
from .decision_contributions import contributions_from_decision
from .learning_aggregate import BLOCK, FEATURE, VerdictPolicy, aggregate
from .learning_proposal import LearningLimits, build_challenger, hypothesis_text, propose_weight_change
from .outcome_classification import DEFAULT_ROUND_TRIP_COST_PCT
from .regime_weights import RegimeRulebook
from .walk_forward_replay import replay_metrics


@dataclass(frozen=True)
class DecisionRecord:
    opportunity_id: str
    symbol: str
    direction: str
    opened_at_s: int
    decision: Mapping[str, Any]
    entry_regime: str
    horizons: Mapping[int, MeasuredHorizon]


@dataclass(frozen=True)
class WalkForwardConfig:
    horizon_minutes: int = 60
    holdout_fraction: float = 0.30
    cost_pct: float = DEFAULT_ROUND_TRIP_COST_PCT
    limits: LearningLimits = field(default_factory=LearningLimits)
    verdicts: VerdictPolicy = field(default_factory=VerdictPolicy)


@dataclass(frozen=True)
class WalkForwardResult:
    proposal: RegimeRulebook | None
    reason: str
    change: dict[str, Any]
    evidence: dict[str, Any]
    replay: dict[str, Any]


def chronological_split(records: Sequence[DecisionRecord], config: WalkForwardConfig):
    """(learn, test, purged count), oldest first."""
    if not 0 < config.holdout_fraction < 1:
        raise ValueError("holdout_fraction must be between 0 and 1")
    usable = sorted((r for r in records if config.horizon_minutes in r.horizons),
                    key=lambda r: (r.opened_at_s, r.opportunity_id))
    if len(usable) < 2:
        return usable, [], 0
    cut = len(usable) - math.ceil(len(usable) * config.holdout_fraction)
    learn, test = usable[:cut], usable[cut:]
    boundary = test[0].opened_at_s
    kept = [r for r in learn if r.opened_at_s + config.horizon_minutes * 60 <= boundary]
    return kept, test, len(learn) - len(kept)


def attribute_records(records: Sequence[DecisionRecord], cost_pct: float) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        parts = contributions_from_decision(record.decision)
        for horizon in sorted(record.horizons):
            rows.append(attribute_outcome(
                opportunity_id=record.opportunity_id, symbol=record.symbol, direction=record.direction,
                opened_at_s=record.opened_at_s, decision=record.decision, measured=record.horizons[horizon],
                entry_regime=record.entry_regime, cost_pct=cost_pct, contributions=parts,
            ).to_dict())
    return rows


def _span(records: Sequence[DecisionRecord]) -> dict[str, Any]:
    return {"decisions": len(records),
            "first_opened_at_s": records[0].opened_at_s if records else None,
            "last_opened_at_s": records[-1].opened_at_s if records else None}


def _assessment(base: Mapping[str, Any], prop: Mapping[str, Any], minimum: float) -> str:
    if min(base["effective_samples"], prop["effective_samples"]) < minimum:
        return "insufficient_test_evidence"
    if base["mean_net_return_pct"] is None or prop["mean_net_return_pct"] is None:
        return "insufficient_test_evidence"
    better_mean = prop["mean_net_return_pct"] > base["mean_net_return_pct"]
    no_worse_hits = (prop["net_hit_rate"] or 0) >= (base["net_hit_rate"] or 0)
    if better_mean and no_worse_hits:
        return "replay_favours_proposal"
    if not better_mean and not no_worse_hits:
        return "replay_favours_baseline"
    return "mixed"


def run_walk_forward(
    records: Sequence[DecisionRecord],
    baseline: RegimeRulebook,
    version: str,
    config: WalkForwardConfig | None = None,
) -> WalkForwardResult:
    config = config or WalkForwardConfig()
    h = config.horizon_minutes
    learn, test, purged = chronological_split(records, config)
    rows = attribute_records(learn, config.cost_pct)
    features = aggregate(rows, FEATURE, config.verdicts)
    blocks = aggregate(rows, BLOCK, config.verdicts)
    evidence = {
        "horizon_minutes": h, "cost_pct": config.cost_pct, "holdout_fraction": config.holdout_fraction,
        "verdict_policy": config.verdicts.to_dict(), "limits": config.limits.to_dict(),
        "window": {"learn": {**_span(learn), "purged": purged}, "test": _span(test)},
        "learning_attributions": len(rows),
        "features": [g.to_dict() for g in features if g.horizon_minutes == h],
        "blocks": [g.to_dict() for g in blocks if g.horizon_minutes == h],
        "parent": {"version": baseline.version, "digest": baseline.digest},
    }
    if not test:
        return WalkForwardResult(None, "not enough measured decisions to hold any out for testing", {}, evidence, {})
    change = propose_weight_change(baseline, features, blocks, h, config.limits)
    if not change.changed:
        return WalkForwardResult(None, "no feature or block has a verdict at this horizon, so no weight should move",
                                 change.to_dict(), evidence, {})
    challenger = build_challenger(baseline, change, version, hypothesis_text(change, h, config.cost_pct, label_for))
    base = replay_metrics(test, baseline, h, config.cost_pct)
    prop = replay_metrics(test, challenger, h, config.cost_pct)
    evidence["guardrails"] = {
        "weights_valid": True,
        "risk_caps_unchanged": challenger.data["paper_risk"] == baseline.data["paper_risk"],
        "max_block_weight": max(challenger.weights.values()),
        "block_cap": baseline.data["validation"]["max_single_block_weight"],
        "baseline_reproduced_share": base["reproduced_share"],
        "test_sample_sufficient": min(base["effective_samples"], prop["effective_samples"]) >= config.verdicts.min_effective,
    }
    replay = {
        "baseline": base, "proposal": prop,
        "delta": {key: (None if prop[key] is None or base[key] is None else round(prop[key] - base[key], 6))
                  for key in ("admitted", "net_hit_rate", "mean_net_return_pct")},
        "assessment": _assessment(base, prop, config.verdicts.min_effective),
        "note": ("Replayed on the newest decisions only, none of which the proposal learned from. "
                 "Decisions a proposal would newly admit have no measured outcome and are not scored. "
                 "Descriptive evidence for an operator decision; nothing is adopted automatically."),
    }
    return WalkForwardResult(challenger, challenger.data["purpose"], change.to_dict(), evidence, replay)
