"""Turn regime block evidence into an admitted paper signal, or a refusal.

This module is deliberately pure. The live producer and any replay or backtest
run must reach the same verdict from the same evidence, so nothing here reads a
clock, a database, or a network socket.

A refusal is a first-class result, not an error. When the evidence cannot
support a paper opportunity the caller still receives the full reasoning, so an
empty opportunity panel can explain itself instead of looking broken.

Vocabulary used below, in ordinary language:

``weighted_score``
    The rulebook's quality-weighted blend of block scores, between -1 and +1.
    Positive leans long, negative leans short. It is a suitability score, not a
    probability that a trade wins.
``data_coverage``
    How much of the rulebook's total block weight actually had admissible
    evidence behind it. 1.0 means every block reported; 0.0 means none did. It
    describes evidence availability, never confidence in an outcome.
``paper_risk_multiplier``
    A policy cap on paper position size. A reduction is a rule we chose, not a
    prediction about the market.
``deadband``
    A band around zero inside which a score is treated as no direction at all,
    so noise near zero cannot manufacture a long or short.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "paper_signal_v1"

# Policy constants. These are chosen research settings, not measured facts, and
# they are recorded on every decision so a stored signal can be re-read later
# against the policy that produced it.
DEFAULT_MINIMUM_COVERAGE_TO_EMIT = 0.30
# Direction is established only by features the catalog marks directional.
# Today exactly one is admitted, so this floor is what stops a single
# half-collected feature from setting a trade direction on its own.
DEFAULT_MINIMUM_DIRECTIONAL_COVERAGE = 0.50
# Hysteresis. Establishing a NEW direction requires clearing the entry
# threshold; an EXISTING direction is held until the score falls back through
# the lower exit threshold. A single symmetric band makes the side flip every
# time a score hovering near zero crosses it, which is noise, not a regime.
DEFAULT_DIRECTION_DEADBAND = 0.05
DEFAULT_DIRECTION_ENTER_THRESHOLD = 0.15
DEFAULT_MAXIMUM_EVIDENCE_AGE_MS = 120_000

INADMISSIBLE_PROVENANCE = frozenset({"proxy", "context_only", "unavailable"})


class PaperSignalError(ValueError):
    """Raised only for malformed input, never for an ordinary refusal."""


@dataclass(frozen=True)
class AdmissionPolicy:
    """The versioned thresholds a decision was taken under."""

    minimum_coverage_to_emit: float = DEFAULT_MINIMUM_COVERAGE_TO_EMIT
    minimum_directional_coverage: float = DEFAULT_MINIMUM_DIRECTIONAL_COVERAGE
    direction_deadband: float = DEFAULT_DIRECTION_DEADBAND
    direction_enter_threshold: float = DEFAULT_DIRECTION_ENTER_THRESHOLD
    maximum_evidence_age_ms: int = DEFAULT_MAXIMUM_EVIDENCE_AGE_MS

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_coverage_to_emit": self.minimum_coverage_to_emit,
            "minimum_directional_coverage": self.minimum_directional_coverage,
            "direction_deadband": self.direction_deadband,
            "direction_enter_threshold": self.direction_enter_threshold,
            "maximum_evidence_age_ms": self.maximum_evidence_age_ms,
            "note": (
                "Policy thresholds are research settings, not measured facts. "
                "Coverage describes evidence availability, not win probability. "
                "Suitability describes how tradeable conditions are and never "
                "sets a direction."
            ),
        }


@dataclass(frozen=True)
class PaperSignalDecision:
    """Either an admitted paper signal or an explained refusal."""

    admitted: bool
    symbol: str
    direction: str
    weighted_score: float
    data_coverage: float
    directional_score: float | None
    directional_coverage: float
    paper_risk_multiplier: float
    evidence_digest: str
    rejection_reasons: list[dict[str, str]] = field(default_factory=list)
    contributing_features: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "mode": "paper_shadow",
            "execution_authority": False,
            "admitted": self.admitted,
            "symbol": self.symbol,
            "direction": self.direction,
            "weighted_score": self.weighted_score,
            "suitability_score": self.weighted_score,
            "data_coverage": self.data_coverage,
            "directional_score": self.directional_score,
            "directional_coverage": self.directional_coverage,
            "paper_risk_multiplier": self.paper_risk_multiplier,
            "evidence_digest": self.evidence_digest,
            "rejection_reasons": self.rejection_reasons,
            "contributing_features": self.contributing_features,
            "evidence": self.evidence,
        }


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _collect_contributing_features(
    feature_results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return the features that actually carried the score, newest field first."""

    contributing = []
    for result in feature_results:
        if not isinstance(result, Mapping) or not result.get("scoring_allowed"):
            continue
        contributing.append(
            {
                "feature_id": str(result.get("feature_id", "")),
                "block": result.get("block"),
                "score": _number(result.get("score")),
                "data_quality": _number(result.get("data_quality")),
                "provenance": result.get("provenance"),
                "observed_at_ms": result.get("observed_at_ms"),
                "history_count": result.get("history_count"),
            }
        )
    contributing.sort(key=lambda item: item["feature_id"])
    return contributing


def _evidence_age_reasons(
    contributing: Sequence[Mapping[str, Any]],
    evaluated_at_ms: int,
    policy: AdmissionPolicy,
) -> list[dict[str, str]]:
    """Reject evidence that is stale, or timestamped in the future."""

    reasons = []
    for item in contributing:
        observed_at = item.get("observed_at_ms")
        if not isinstance(observed_at, int) or isinstance(observed_at, bool):
            continue
        age_ms = evaluated_at_ms - observed_at
        if age_ms < 0:
            reasons.append(
                {
                    "code": "evidence_timestamped_in_future",
                    "feature_id": str(item.get("feature_id")),
                    "detail": (
                        f"observed_at is {abs(age_ms)} ms ahead of the evaluation "
                        "time, so the reading cannot be trusted"
                    ),
                }
            )
        elif age_ms > policy.maximum_evidence_age_ms:
            reasons.append(
                {
                    "code": "evidence_stale",
                    "feature_id": str(item.get("feature_id")),
                    "detail": (
                        f"observed_at is {age_ms} ms old, beyond the "
                        f"{policy.maximum_evidence_age_ms} ms admission bound"
                    ),
                }
            )
    return reasons


def _provenance_reasons(
    contributing: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    reasons = []
    for item in contributing:
        provenance = item.get("provenance")
        if provenance in INADMISSIBLE_PROVENANCE:
            reasons.append(
                {
                    "code": "inadmissible_provenance",
                    "feature_id": str(item.get("feature_id")),
                    "detail": (
                        f"provenance '{provenance}' may inform a human but may "
                        "never contribute to a generic directional score"
                    ),
                }
            )
    return reasons


def decide_paper_signal(
    symbol: str,
    evaluation: Mapping[str, Any],
    feature_results: Sequence[Mapping[str, Any]],
    catalog_summary: Mapping[str, Any],
    evaluated_at_ms: int,
    policy: AdmissionPolicy | None = None,
    directional: Mapping[str, Any] | None = None,
    previous_direction: str | None = None,
) -> PaperSignalDecision:
    """Decide whether the evidence supports one paper signal for ``symbol``.

    ``evaluation`` is the output of ``regime_weights.evaluate_blocks``, which
    scores playbook **suitability** — how tradeable conditions are.

    ``directional`` is ``aggregate_directional_evidence(...).to_dict()`` and is
    the only thing permitted to set LONG or SHORT. Passing ``None`` means no
    directional evidence was supplied, and no direction can be admitted:
    suitability alone never implies a side.
    """

    if not symbol:
        raise PaperSignalError("symbol is required")
    if not isinstance(evaluation, Mapping):
        raise PaperSignalError("evaluation must be a mapping")
    if not isinstance(evaluated_at_ms, int) or isinstance(evaluated_at_ms, bool):
        raise PaperSignalError("evaluated_at_ms must be an integer")

    policy = policy or AdmissionPolicy()

    weighted_score = _number(evaluation.get("weighted_score"))
    data_coverage = _number(evaluation.get("data_coverage"))
    risk_multiplier = _number(evaluation.get("paper_risk_multiplier"))
    if weighted_score is None or data_coverage is None or risk_multiplier is None:
        raise PaperSignalError(
            "evaluation must carry numeric weighted_score, data_coverage and "
            "paper_risk_multiplier"
        )

    contributing = _collect_contributing_features(feature_results)

    reasons: list[dict[str, str]] = []
    reasons.extend(_provenance_reasons(contributing))
    reasons.extend(_evidence_age_reasons(contributing, evaluated_at_ms, policy))

    if not contributing:
        reasons.append(
            {
                "code": "no_admitted_evidence",
                "feature_id": "",
                "detail": (
                    "no feature was admitted for scoring, so there is nothing "
                    "for a paper opportunity to rest on"
                ),
            }
        )

    if data_coverage < policy.minimum_coverage_to_emit:
        reasons.append(
            {
                "code": "coverage_below_emit_floor",
                "feature_id": "",
                "detail": (
                    f"data coverage {data_coverage:.4f} is below the "
                    f"{policy.minimum_coverage_to_emit} floor; missing blocks: "
                    + (", ".join(evaluation.get("missing_blocks") or []) or "none")
                ),
            }
        )

    # Direction is decided ONLY by directional evidence. The blended rulebook
    # score measures suitability: deep two-sided books and tight spreads make a
    # market tradeable, they do not make it a buy.
    directional = directional or {}
    directional_score = _number(directional.get("score"))
    directional_coverage = _number(directional.get("coverage")) or 0.0

    if directional_score is None:
        reasons.append(
            {
                "code": "no_directional_evidence",
                "feature_id": "",
                "detail": (
                    "no feature marked directional in the catalog was ready, so "
                    "no side can be established; suitability alone never implies "
                    "a direction"
                ),
            }
        )
    else:
        # Holding an existing side needs only the exit threshold; establishing
        # a new one needs the higher entry threshold.
        candidate = "LONG" if directional_score > 0 else "SHORT"
        holding = previous_direction in {"LONG", "SHORT"} and previous_direction == candidate
        required = (
            policy.direction_deadband if holding else policy.direction_enter_threshold
        )
        if abs(directional_score) < required:
            reasons.append(
                {
                    "code": "score_inside_deadband",
                    "feature_id": "",
                    "detail": (
                        f"directional score {directional_score:.6f} did not reach the "
                        f"{'±%s hold' % policy.direction_deadband if holding else '±%s entry' % policy.direction_enter_threshold} "
                        f"threshold; treated as no direction rather than a weak one"
                    ),
                }
            )

    if directional_coverage < policy.minimum_directional_coverage:
        admitted_ids = ", ".join(directional.get("admitted_feature_ids") or []) or "none"
        reasons.append(
            {
                "code": "directional_coverage_below_floor",
                "feature_id": "",
                "detail": (
                    f"directional coverage {directional_coverage:.4f} is below the "
                    f"{policy.minimum_directional_coverage} floor; features able to "
                    f"set a direction: {admitted_ids}"
                ),
            }
        )

    if risk_multiplier <= 0:
        reasons.append(
            {
                "code": "paper_risk_fully_capped",
                "feature_id": "",
                "detail": (
                    "the paper risk cap resolved to zero, so no paper position "
                    "size is permitted under this rulebook"
                ),
            }
        )

    admitted = not reasons
    if not admitted or directional_score is None:
        direction = "NONE"
    elif directional_score > 0:
        direction = "LONG"
    else:
        direction = "SHORT"

    evidence = {
        "rulebook_id": evaluation.get("rulebook_id"),
        "rulebook_version": evaluation.get("rulebook_version"),
        "rulebook_digest": evaluation.get("config_digest"),
        "catalog_id": catalog_summary.get("catalog_id"),
        "catalog_version": catalog_summary.get("version"),
        "catalog_digest": catalog_summary.get("digest"),
        "evaluated_at_ms": evaluated_at_ms,
        "contributions": evaluation.get("contributions"),
        "missing_blocks": evaluation.get("missing_blocks"),
        "risk_caps_applied": evaluation.get("risk_caps_applied"),
        "calculation": evaluation.get("calculation"),
        "suitability_note": (
            "weighted_score measures playbook suitability, not direction. "
            "Direction comes only from catalog-directional features."
        ),
        "directional": dict(directional) if directional else None,
        "previous_direction": previous_direction,
        "policy": policy.to_dict(),
    }

    # The digest binds the verdict to the exact evidence and configuration that
    # produced it, so replaying the same window is idempotent rather than
    # creating a second opportunity.
    digest = _canonical_digest(
        {
            "schema_version": SCHEMA_VERSION,
            "symbol": symbol,
            "rulebook_digest": evaluation.get("config_digest"),
            "catalog_digest": catalog_summary.get("digest"),
            "policy": policy.to_dict(),
            "directional": directional.get("contributors") if directional else None,
            "previous_direction": previous_direction,
            "features": [
                {
                    "feature_id": item["feature_id"],
                    "observed_at_ms": item["observed_at_ms"],
                    "score": item["score"],
                    "data_quality": item["data_quality"],
                }
                for item in contributing
            ],
        }
    )

    return PaperSignalDecision(
        admitted=admitted,
        symbol=symbol,
        direction=direction,
        weighted_score=round(weighted_score, 12),
        data_coverage=round(data_coverage, 12),
        directional_score=(
            round(directional_score, 12) if directional_score is not None else None
        ),
        directional_coverage=round(directional_coverage, 12),
        paper_risk_multiplier=risk_multiplier,
        evidence_digest=digest,
        rejection_reasons=reasons,
        contributing_features=list(contributing),
        evidence=evidence,
    )
