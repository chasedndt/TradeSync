"""Dispersion statistics and freshness for paper-shadow feature normalization."""

from __future__ import annotations

import statistics
from typing import Any, Sequence

from .feature_catalog import FeatureValidationError, _number

FLAT_REASON = "flat: every recent value identical"
MAD_FALLBACK = "median absolute deviation is zero; ordinary z-score used"


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


def z_score_statistics(
    history: Sequence[float], current_value: float, method: str
) -> dict[str, Any]:
    """The z-score by the requested method, with one recorded fallback.

    Spread and buy impact move in whole ticks, so most recent values are often
    identical: the median absolute deviation is then zero although the values
    do vary, and the robust z-score has no scale. The ordinary z-score is used
    instead and the substitution is recorded in ``method`` and ``fallback``.
    When every recent value is identical there is no dispersion by either
    measure and the reading stays unavailable.
    """

    if method not in {"ordinary_zscore", "robust_zscore"}:
        raise FeatureValidationError(
            "method must be ordinary_zscore or robust_zscore"
        )
    values = [_number(value, "history value") for value in history]
    recorded = {"requested_method": method, "fallback": None}
    if len(values) >= 2 and all(value == values[0] for value in values):
        raise FeatureValidationError(FLAT_REASON)
    if method == "ordinary_zscore":
        return {**ordinary_statistics(values, current_value), **recorded, "method": method}
    if len(values) >= 2:
        center = statistics.median(values)
        if statistics.median(abs(value - center) for value in values) == 0:
            return {
                **ordinary_statistics(values, current_value),
                **recorded,
                "method": "ordinary_zscore",
                "mad": 0.0,
                "fallback": MAD_FALLBACK,
            }
    return {**robust_statistics(values, current_value), **recorded, "method": method}


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
