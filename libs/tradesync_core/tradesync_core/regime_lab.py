"""Paper-only Regime Lab calculations shared by API, replay, and tests.

The browser never calculates a score. It submits operator controls; this module
validates a challenger draft and aggregates admitted feature evidence into
rulebook blocks. Challengers are judged by replaying stored decisions
(``replay_judgement``), not by re-scoring one market snapshot.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .feature_weights import feature_weight
from .market_features import FeatureCatalog
from .regime_weights import (
    RegimeRulebook,
    RulebookValidationError,
    validate_rulebook,
)


class RegimeLabValidationError(ValueError):
    """Raised when an operator experiment violates a paper-lab gate."""


@dataclass(frozen=True)
class AggregatedEvidence:
    block_scores: dict[str, float]
    data_quality: dict[str, float]
    blocks: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class DirectionalEvidence:
    """Direction, separated from suitability.

    The rulebook scores *playbook suitability*: whether conditions are
    tradeable. Most admitted features measure exactly that — two-sided depth,
    spread, impact. A deep order book does not mean "buy", so the sign of the
    blended suitability score must never be read as a trade direction.

    Only features the catalog marks ``signal_kind: directional`` may set a
    direction, and they are aggregated here on their own.
    """

    score: float | None
    coverage: float
    contributors: list[dict[str, Any]]
    admitted_feature_ids: list[str]
    ready_feature_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "coverage": self.coverage,
            "contributors": self.contributors,
            "admitted_feature_ids": self.admitted_feature_ids,
            "ready_feature_ids": self.ready_feature_ids,
            "calculation": "sum(score * quality) / sum(quality) over directional features only",
        }


def aggregate_directional_evidence(
    catalog: FeatureCatalog,
    feature_results: Sequence[Mapping[str, Any]],
    feature_weights: Mapping[str, float] | None = None,
) -> DirectionalEvidence:
    """Aggregate only the features permitted to establish a direction.

    ``feature_weights`` (from an adopted rulebook) scale each feature's pull on
    the score. Coverage is unaffected: it counts evidence collected, not trust.
    """

    admitted = [
        feature_id
        for feature_id, definition in catalog.features.items()
        if definition.get("signal_kind") == "directional"
        and definition["scoring_eligible"]
        and definition["score_mode"] in {"direct", "inverse"}
    ]
    result_by_id = {
        str(item.get("feature_id")): item
        for item in feature_results
        if isinstance(item, Mapping) and item.get("feature_id")
    }

    numerator = 0.0
    quality_total = 0.0
    weighted_quality_total = 0.0
    contributors: list[dict[str, Any]] = []
    for feature_id in admitted:
        result = result_by_id.get(feature_id)
        if not result or not result.get("scoring_allowed"):
            continue
        score = result.get("score")
        quality = result.get("data_quality")
        if not isinstance(score, (int, float)) or not isinstance(quality, (int, float)):
            continue
        if not math.isfinite(float(score)) or not math.isfinite(float(quality)):
            continue
        safe_quality = min(max(float(quality), 0.0), 1.0)
        weight = feature_weight(feature_weights, feature_id)
        numerator += float(score) * safe_quality * weight
        quality_total += safe_quality
        weighted_quality_total += safe_quality * weight
        contributor = {
            "feature_id": feature_id,
            "score": round(float(score), 12),
            "quality": round(safe_quality, 12),
        }
        if weight != 1.0:
            contributor["weight"] = weight
        contributors.append(contributor)

    score = (
        round(numerator / weighted_quality_total, 12)
        if weighted_quality_total > 0
        else None
    )
    coverage = round(quality_total / len(admitted), 12) if admitted else 0.0
    return DirectionalEvidence(
        score=score,
        coverage=coverage,
        contributors=contributors,
        admitted_feature_ids=admitted,
        ready_feature_ids=[item["feature_id"] for item in contributors],
    )


def aggregate_feature_evidence(
    catalog: FeatureCatalog,
    rulebook: RegimeRulebook,
    feature_results: Sequence[Mapping[str, Any]],
) -> AggregatedEvidence:
    """Aggregate generic feature scores into deterministic rulebook blocks.

    Each admitted direct/inverse feature has equal standing within its block.
    Its data quality weights the block score and contributes to block coverage.
    Playbook-specific features remain visible evidence but cannot manufacture a
    generic directional score.
    """

    result_by_id = {
        str(item.get("feature_id")): item
        for item in feature_results
        if isinstance(item, Mapping) and item.get("feature_id")
    }
    block_scores: dict[str, float] = {}
    data_quality: dict[str, float] = {}
    block_details: dict[str, dict[str, Any]] = {}
    weights = rulebook.feature_weights

    for block in rulebook.weights:
        admitted = [
            feature_id
            for feature_id, definition in catalog.features.items()
            if definition["block"] == block
            and definition["scoring_eligible"]
            and definition["score_mode"] in {"direct", "inverse"}
        ]
        ready: list[dict[str, Any]] = []
        numerator = 0.0
        quality_total = 0.0
        weighted_quality_total = 0.0
        for feature_id in admitted:
            result = result_by_id.get(feature_id)
            if not result or not result.get("scoring_allowed"):
                continue
            score = result.get("score")
            quality = result.get("data_quality")
            if not isinstance(score, (int, float)) or not isinstance(
                quality, (int, float)
            ):
                continue
            if not math.isfinite(float(score)) or not math.isfinite(float(quality)):
                continue
            safe_quality = min(max(float(quality), 0.0), 1.0)
            weight = feature_weight(weights, feature_id)
            numerator += float(score) * safe_quality * weight
            quality_total += safe_quality
            weighted_quality_total += safe_quality * weight
            entry = {
                "feature_id": feature_id,
                "score": round(float(score), 12),
                "quality": round(safe_quality, 12),
            }
            if weight != 1.0:
                entry["weight"] = weight
            ready.append(entry)

        # Quality (coverage) counts evidence collected; weights change only
        # how hard each collected reading pulls on the block's score.
        block_quality = quality_total / len(admitted) if admitted else 0.0
        block_score = (
            numerator / weighted_quality_total if weighted_quality_total > 0 else None
        )
        if block_score is not None:
            block_scores[block] = round(block_score, 12)
            data_quality[block] = round(block_quality, 12)

        block_details[block] = {
            "admitted_feature_ids": admitted,
            "ready_features": ready,
            "missing_feature_ids": [
                feature_id
                for feature_id in admitted
                if feature_id not in {item["feature_id"] for item in ready}
            ],
            "score": round(block_score, 12) if block_score is not None else None,
            "quality": round(block_quality, 12),
            "status": "ready" if ready else "unavailable",
        }

    return AggregatedEvidence(
        block_scores=block_scores,
        data_quality=data_quality,
        blocks=block_details,
    )


def challenger_rulebook(
    baseline: RegimeRulebook,
    weights: Mapping[str, Any],
    version: str,
    purpose: str | None = None,
) -> RegimeRulebook:
    """A validated paper draft of ``baseline`` with new block weights.

    The baseline configuration is never mutated. A replay needs only this; a
    saved experiment also records its hypothesis as the draft's purpose.
    """

    if not isinstance(version, str) or not version.strip():
        raise RegimeLabValidationError("challenger version is required")
    if not isinstance(weights, Mapping):
        raise RegimeLabValidationError("weights must be an object")
    expected = set(baseline.weights)
    if set(weights) != expected:
        missing = sorted(expected - set(weights))
        unknown = sorted(set(weights) - expected)
        parts = []
        if missing:
            parts.append(f"missing blocks: {', '.join(missing)}")
        if unknown:
            parts.append(f"unknown blocks: {', '.join(unknown)}")
        raise RegimeLabValidationError("; ".join(parts))

    draft = json.loads(json.dumps(baseline.data))
    draft["version"] = version.strip()
    draft["status"] = "draft"
    draft["environment"] = "paper"
    if purpose:
        draft["purpose"] = purpose.strip()
    for block, raw_weight in weights.items():
        draft["blocks"][block]["weight"] = raw_weight

    try:
        return validate_rulebook(draft)
    except RulebookValidationError as exc:
        raise RegimeLabValidationError(str(exc)) from exc


def build_challenger_rulebook(
    baseline: RegimeRulebook,
    weights: Mapping[str, Any],
    version: str,
    hypothesis: str,
) -> RegimeRulebook:
    """The draft a saved experiment stores: a hypothesis of at least 20 characters is its purpose."""

    if not isinstance(hypothesis, str) or len(hypothesis.strip()) < 20:
        raise RegimeLabValidationError(
            "hypothesis must contain at least 20 characters"
        )
    return challenger_rulebook(baseline, weights, version, hypothesis)
