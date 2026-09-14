"""Dispersion statistics and freshness for paper-shadow feature normalization."""

from __future__ import annotations

import statistics
from typing import Sequence

from .feature_catalog import FeatureValidationError, _number


def ordinary_statistics(
    history: Sequence[float], current_value: float
) -> dict[str, float]:
    """Calculate a sample z-score using mean and sample standard deviation."""

    values = [_number(value, "history value") for value in history]
    current = _number(current_value, "current.value")
    if len(values) < 2:
        raise FeatureValidationError(
            "ordinary z-score requires at least 2 historical values"
        )
    center = statistics.fmean(values)
    dispersion = statistics.stdev(values)
    if dispersion == 0:
        raise FeatureValidationError(
            "ordinary z-score unavailable because sample standard deviation is zero"
        )
    return {
        "center": center,
        "dispersion": dispersion,
        "z_score": (current - center) / dispersion,
    }


def robust_statistics(
    history: Sequence[float], current_value: float
) -> dict[str, float]:
    """Calculate a robust z-score using median and scaled MAD."""

    values = [_number(value, "history value") for value in history]
    current = _number(current_value, "current.value")
    if len(values) < 2:
        raise FeatureValidationError(
            "robust z-score requires at least 2 historical values"
        )
    center = statistics.median(values)
    mad = statistics.median(abs(value - center) for value in values)
    dispersion = 1.4826 * mad
    if dispersion == 0:
        raise FeatureValidationError(
            "robust z-score unavailable because median absolute deviation is zero"
        )
    return {
        "center": center,
        "mad": mad,
        "dispersion": dispersion,
        "z_score": (current - center) / dispersion,
    }


def freshness_factor(
    age_ms: int, fresh_after_ms: int, stale_after_ms: int
) -> float:
    """Return 1 when fresh, 0 when stale, and a linear value between."""

    if age_ms < 0:
        raise FeatureValidationError("evaluated_at_ms cannot precede current.ts")
    if stale_after_ms <= 0:
        return 0.0
    if age_ms <= fresh_after_ms:
        return 1.0
    if age_ms >= stale_after_ms:
        return 0.0
    width = stale_after_ms - fresh_after_ms
    return 1.0 - ((age_ms - fresh_after_ms) / width)
