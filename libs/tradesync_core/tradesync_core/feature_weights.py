"""Per-feature weights inside a rulebook, and the weighted mean that applies them.

A rulebook's block weights say how much each evidence block counts. A learning
proposal may also trust one *feature* inside a block more or less than its
neighbours - for example the one-hour return less than order flow, when the
measured outcomes say the return reading misleads. ``feature_weights`` holds
those multipliers, keyed by catalog feature id.

A multiplier scales a feature's pull on a score, never its contribution to
coverage. Coverage describes how much evidence was collected; a reading that is
trusted less was still collected. A rulebook without ``feature_weights`` scores
exactly as it did before this module existed: every multiplier is 1.0, and
multiplying by 1.0 is exact in floating point, so stored evidence digests do not
change.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

FEATURE_WEIGHTS_KEY = "feature_weights"
# Generous outer bound for validation. Learning proposals use tighter limits of
# their own (tradesync_core.learning_proposal.LearningLimits).
MAX_FEATURE_WEIGHT = 4.0


class FeatureWeightError(ValueError):
    """Raised when a rulebook's feature weights are malformed."""


def validate_feature_weights(value: Any) -> dict[str, float]:
    """Return validated multipliers; ``None`` means no feature is re-weighted."""

    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise FeatureWeightError("feature_weights must be an object")
    weights: dict[str, float] = {}
    for feature_id, raw in value.items():
        if not isinstance(feature_id, str) or not feature_id.strip():
            raise FeatureWeightError("feature_weights keys must be feature ids")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise FeatureWeightError(f"feature_weights.{feature_id} must be a number")
        weight = float(raw)
        if not math.isfinite(weight) or not 0 < weight <= MAX_FEATURE_WEIGHT:
            raise FeatureWeightError(
                f"feature_weights.{feature_id} must be greater than 0 and at most "
                f"{MAX_FEATURE_WEIGHT:g}"
            )
        weights[feature_id] = weight
    return weights


def feature_weights_of(rulebook_data: Mapping[str, Any]) -> dict[str, float]:
    """The multipliers a validated rulebook configuration declares."""

    declared = rulebook_data.get(FEATURE_WEIGHTS_KEY) or {}
    return {str(key): float(value) for key, value in declared.items()}


def diff_feature_weights(
    before: Mapping[str, float], after: Mapping[str, float]
) -> dict[str, dict[str, float]]:
    """Every feature whose multiplier differs, with the implicit 1.0 made explicit."""

    return {
        name: {"before": before.get(name, 1.0), "after": after.get(name, 1.0)}
        for name in sorted(set(before) | set(after))
        if before.get(name, 1.0) != after.get(name, 1.0)
    }


def feature_weight(weights: Mapping[str, float] | None, feature_id: str) -> float:
    """The multiplier for one feature; 1.0 unless the rulebook says otherwise."""

    if not weights:
        return 1.0
    return float(weights.get(feature_id, 1.0))


def weighted_mean(items: Iterable[tuple[float, float, float]]) -> float | None:
    """``sum(score * quality * weight) / sum(quality * weight)``.

    Items are ``(score, quality, weight)``. Returns ``None`` when nothing carries
    any weight, which callers report as "no score" rather than as zero.
    """

    numerator = 0.0
    denominator = 0.0
    for score, quality, weight in items:
        numerator += float(score) * float(quality) * float(weight)
        denominator += float(quality) * float(weight)
    return numerator / denominator if denominator > 0 else None
