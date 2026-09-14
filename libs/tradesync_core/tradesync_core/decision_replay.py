"""Re-decide one stored paper decision under another rulebook, feature weights included.

This extends ``tradesync_core.replay`` rather than replacing it: the case is
built by ``case_from_stored_evidence`` and decided by ``replay_case``, which call
the same ``evaluate_blocks`` and ``decide_paper_signal`` the live producer calls.
Two things are added:

- **Feature weights.** A block's recorded score is a quality-weighted mean of
  its admitted features, and the directional score a mean of its contributors.
  When a rulebook re-weights a feature, those means are recomputed from the
  recorded per-feature readings with the new multipliers. Blocks and readings
  the rulebook does not re-weight keep their recorded values exactly.
- **The recorded policy.** Each stored decision carries the admission policy it
  was taken under; replaying under that policy isolates the rulebook as the
  only thing that differs.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Mapping

from .feature_weights import feature_weight, weighted_mean
from .paper_signal import AdmissionPolicy, PaperSignalDecision
from .regime_weights import RegimeRulebook
from .replay import ReplayCase, ReplayError, case_from_stored_evidence, replay_case


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def policy_from_stored(decision: Mapping[str, Any]) -> AdmissionPolicy:
    """The admission policy a decision was taken under, as recorded with it.

    A threshold that is absent from the record did not exist when the decision
    was taken, and is replayed as the rule of that day rather than today's
    default: before hysteresis a side was entered at the same deadband that held
    it, and before directional coverage was gated there was no floor.
    """

    stored = (decision.get("evidence") or {}).get("policy") or {}
    defaults = AdmissionPolicy()

    def pick(name: str, fallback: float) -> float:
        value = _number(stored.get(name))
        return value if value is not None else fallback

    deadband = pick("direction_deadband", defaults.direction_deadband)
    return AdmissionPolicy(
        minimum_coverage_to_emit=pick("minimum_coverage_to_emit", defaults.minimum_coverage_to_emit),
        minimum_directional_coverage=pick("minimum_directional_coverage", 0.0),
        direction_deadband=deadband,
        direction_enter_threshold=pick("direction_enter_threshold", deadband),
        maximum_evidence_age_ms=int(pick("maximum_evidence_age_ms", defaults.maximum_evidence_age_ms)),
    )


def catalog_from_stored(decision: Mapping[str, Any]) -> dict[str, Any]:
    evidence = decision.get("evidence") or {}
    return {
        "catalog_id": evidence.get("catalog_id"),
        "version": evidence.get("catalog_version"),
        "digest": evidence.get("catalog_digest"),
    }


def reweighted_case(
    decision_id: str,
    symbol: str,
    decision: Mapping[str, Any],
    feature_weights: Mapping[str, float] | None = None,
) -> ReplayCase:
    """The replay case for a stored decision, with feature multipliers applied."""

    case = case_from_stored_evidence(decision_id, symbol, decision)
    if not feature_weights:
        return case

    block_scores = dict(case.block_scores)
    readings: dict[str, list[tuple[float, float, float]]] = {}
    for item in decision.get("contributing_features") or []:
        score, quality = _number(item.get("score")), _number(item.get("data_quality"))
        block = item.get("block")
        if score is None or quality is None or block not in block_scores:
            continue
        readings.setdefault(block, []).append((score, quality, feature_weight(feature_weights, str(item.get("feature_id")))))
    for block, items in readings.items():
        if any(weight != 1.0 for _, _, weight in items):
            recomputed = weighted_mean(items)
            if recomputed is not None:
                block_scores[block] = recomputed

    directional = dict(case.directional)
    contributors = []
    for item in directional.get("contributors") or []:
        score, quality = _number(item.get("score")), _number(item.get("quality"))
        if score is None or quality is None:
            continue
        weight = feature_weight(feature_weights, str(item.get("feature_id")))
        entry = {"feature_id": item.get("feature_id"), "score": score, "quality": quality}
        if weight != 1.0:
            entry["weight"] = weight
        contributors.append(entry)
    if contributors:
        recomputed = weighted_mean((c["score"], c["quality"], c.get("weight", 1.0)) for c in contributors)
        directional["contributors"] = contributors
        directional["score"] = round(recomputed, 12) if recomputed is not None else None
    return replace(case, block_scores=block_scores, directional=directional)


def replay_decision(
    decision_id: str,
    symbol: str,
    decision: Mapping[str, Any],
    rulebook: RegimeRulebook,
) -> PaperSignalDecision:
    """What ``rulebook`` would have decided from this decision's recorded evidence.

    Raises ``ReplayError`` for a decision recorded before directional evidence
    existed: its side came from a rule that no longer exists, so no replay of
    the current rule can say what that decision would have been.
    """

    if not isinstance((decision.get("evidence") or {}).get("directional"), dict):
        raise ReplayError(
            f"decision {decision_id} predates directional evidence and cannot be "
            "replayed under the current decision rule"
        )
    case = reweighted_case(decision_id, symbol, decision, rulebook.feature_weights)
    return replay_case(case, rulebook, policy_from_stored(decision), catalog_from_stored(decision))
