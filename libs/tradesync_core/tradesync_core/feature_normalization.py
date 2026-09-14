"""Normalize one time-ordered feature request without changing active scoring."""

from __future__ import annotations

from typing import Any, Mapping

from .feature_catalog import FeatureCatalog, FeatureValidationError, _number
from .feature_statistics import freshness_factor, z_score_statistics
from .regime_weights import bounded_z_score


def _parse_request(
    request: Mapping[str, Any],
) -> tuple[str, str, str, int, float, str, list[tuple[int, float]]]:
    if not isinstance(request, Mapping):
        raise FeatureValidationError("normalization request must be an object")
    for field in ("feature_id", "symbol", "timeframe"):
        if not isinstance(request.get(field), str) or not request[field]:
            raise FeatureValidationError(f"{field} must be a non-empty string")
    evaluated_at = int(_number(request.get("evaluated_at_ms"), "evaluated_at_ms"))

    current = request.get("current")
    if not isinstance(current, Mapping):
        raise FeatureValidationError("current must be an object")
    current_ts = int(_number(current.get("ts"), "current.ts"))
    current_value = _number(current.get("value"), "current.value")
    source_event_id = current.get("source_event_id")
    if not isinstance(source_event_id, str) or not source_event_id:
        raise FeatureValidationError(
            "current.source_event_id must be a non-empty string"
        )

    history_raw = request.get("history")
    if not isinstance(history_raw, list):
        raise FeatureValidationError("history must be an array")
    history: list[tuple[int, float]] = []
    for index, item in enumerate(history_raw):
        if not isinstance(item, Mapping):
            raise FeatureValidationError(f"history[{index}] must be an object")
        ts = int(_number(item.get("ts"), f"history[{index}].ts"))
        value = _number(item.get("value"), f"history[{index}].value")
        history.append((ts, value))

    timestamps = [item[0] for item in history]
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise FeatureValidationError(
            "history timestamps must be strictly increasing and unique"
        )
    if any(ts >= current_ts for ts in timestamps):
        raise FeatureValidationError(
            "history must contain only observations before current.ts"
        )
    if evaluated_at < current_ts:
        raise FeatureValidationError("evaluated_at_ms cannot precede current.ts")

    return (
        str(request["feature_id"]),
        str(request["symbol"]),
        str(request["timeframe"]),
        evaluated_at,
        current_value,
        source_event_id,
        history,
    )


def normalize_feature(
    catalog: FeatureCatalog,
    request: Mapping[str, Any],
    method_override: str | None = None,
) -> dict[str, Any]:
    """Normalize one time-ordered feature request without changing active scoring."""

    (
        feature_id,
        symbol,
        timeframe,
        evaluated_at,
        current_value,
        source_event_id,
        history,
    ) = _parse_request(request)
    if feature_id not in catalog.features:
        raise FeatureValidationError(f"unknown feature_id: {feature_id}")
    definition = catalog.features[feature_id]
    current_ts = int(request["current"]["ts"])

    result: dict[str, Any] = {
        "schema_version": "market_feature_value_v1",
        "catalog_version": catalog.version,
        "catalog_digest": catalog.digest,
        "feature_id": feature_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "observed_at_ms": current_ts,
        "evaluated_at_ms": evaluated_at,
        "source_event_id": source_event_id,
        "source": definition["source"],
        "unit": definition["unit"],
        "provenance": definition["provenance"],
        "availability": definition["availability"],
        "current_value": current_value,
        "status": "unavailable",
        "reason": None,
        "normalization": None,
        "normalized_value": None,
        "score": None,
        "score_mode": definition["score_mode"],
        "scoring_allowed": False,
        "data_quality": 0.0,
        "history_count": 0,
    }

    if definition["availability"] != "implemented":
        result["reason"] = (
            f"feature is {definition['availability']} in catalog v{catalog.version}"
        )
        return result
    if definition["normalization"] == "none":
        result["status"] = "not_normalized"
        result["reason"] = (
            "base, display, proxy, or context feature has no scoring normalization"
        )
        return result

    method = method_override or definition["normalization"]
    if method not in {"ordinary_zscore", "robust_zscore"}:
        raise FeatureValidationError(
            "method override must be ordinary_zscore or robust_zscore"
        )

    lookback = int(definition["lookback_points"])
    minimum = int(definition["minimum_history_points"])
    selected = history[-lookback:] if lookback else []
    result["history_count"] = len(selected)
    if len(selected) < minimum:
        result["status"] = "collecting_history"
        result["reason"] = (
            f"needs at least {minimum} prior values; received {len(selected)}"
        )
        return result

    age_ms = evaluated_at - current_ts
    freshness = freshness_factor(
        age_ms,
        int(definition["fresh_after_ms"]),
        int(definition["stale_after_ms"]),
    )
    sample_factor = min(len(selected) / lookback, 1.0) if lookback else 0.0
    quality = sample_factor * freshness

    values = [value for _, value in selected]
    try:
        stats = z_score_statistics(values, current_value, method)
    except FeatureValidationError as exc:
        result["reason"] = str(exc)
        return result

    bounded = bounded_z_score(stats["z_score"], 2.0)
    score = None
    if definition["score_mode"] == "direct":
        score = bounded
    elif definition["score_mode"] == "inverse":
        score = -bounded

    status = "ready" if freshness > 0 else "stale"
    scoring_allowed = bool(
        status == "ready"
        and definition["scoring_eligible"]
        and definition["score_mode"] in {"direct", "inverse"}
    )
    if not scoring_allowed:
        score = None

    result.update(
        {
            "status": status,
            "reason": None if status == "ready" else "observation is stale",
            "history_start_ms": selected[0][0],
            "history_end_ms": selected[-1][0],
            "history_count": len(selected),
            "normalization": {
                "method": stats["method"],
                "requested_method": stats["requested_method"],
                "fallback": stats["fallback"],
                "center": round(stats["center"], 12),
                "dispersion": round(stats["dispersion"], 12),
                "mad": round(stats["mad"], 12) if "mad" in stats else None,
                "z_score": round(stats["z_score"], 12),
                "compression": "tanh(z / 2)",
            },
            "normalized_value": round(bounded, 12),
            "score": round(score, 12) if score is not None else None,
            "scoring_allowed": scoring_allowed,
            "data_quality": round(quality, 12),
            "quality_components": {
                "sample_factor": round(sample_factor, 12),
                "freshness_factor": round(freshness, 12),
            },
        }
    )
    return result
