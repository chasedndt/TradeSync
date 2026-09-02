"""Source-governed market feature catalog and paper-shadow normalization."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .regime_weights import (
    RegimeRulebook,
    bounded_z_score,
    config_digest,
    load_rulebook,
)


class FeatureValidationError(ValueError):
    """Raised when a feature catalog or normalization request is invalid."""


@dataclass(frozen=True)
class FeatureCatalog:
    data: dict[str, Any]
    digest: str
    features: dict[str, dict[str, Any]]

    @property
    def version(self) -> str:
        return str(self.data["version"])


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FeatureValidationError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise FeatureValidationError(f"{field} must be finite")
    return number


def validate_catalog(data: Mapping[str, Any]) -> FeatureCatalog:
    required_text = ("schema_version", "catalog_id", "version", "status", "venue")
    for field in required_text:
        if not isinstance(data.get(field), str) or not str(data[field]).strip():
            raise FeatureValidationError(f"{field} must be a non-empty string")

    if data["schema_version"] != "market_feature_catalog_v1":
        raise FeatureValidationError("schema_version must be market_feature_catalog_v1")
    if data["status"] != "paper_shadow":
        raise FeatureValidationError("v1 catalog status must be paper_shadow")
    if data["venue"] != "hyperliquid":
        raise FeatureValidationError("v1 catalog is Hyperliquid-only")

    features = data.get("features")
    if not isinstance(features, Mapping) or not features:
        raise FeatureValidationError("features must be a non-empty object")

    allowed_availability = {"implemented", "planned", "unavailable"}
    allowed_provenance = {"observed", "derived", "proxy", "context_only", "unavailable"}
    allowed_authority = {
        "authoritative_market",
        "authoritative_market_derived",
        "proxy_only",
        "context_only",
        "unavailable",
    }
    allowed_normalization = {"none", "ordinary_zscore", "robust_zscore"}
    allowed_score_mode = {
        "none",
        "direct",
        "inverse",
        "playbook_specific",
        "context_only",
        "unavailable",
    }
    scoring_provenance = {"observed", "derived"}
    scoring_authority = {"authoritative_market", "authoritative_market_derived"}

    copied_features: dict[str, dict[str, Any]] = {}
    for feature_id, raw_definition in features.items():
        if not isinstance(feature_id, str) or not feature_id:
            raise FeatureValidationError("every feature must have a non-empty ID")
        if not isinstance(raw_definition, Mapping):
            raise FeatureValidationError(f"features.{feature_id} must be an object")
        definition = dict(raw_definition)

        for field in (
            "block",
            "availability",
            "provenance",
            "source_authority",
            "source",
            "unit",
            "comparator",
            "normalization",
            "score_mode",
            "decision_role",
            "missing_data",
        ):
            if not isinstance(definition.get(field), str) or not definition[field].strip():
                raise FeatureValidationError(
                    f"features.{feature_id}.{field} must be a non-empty string"
                )

        if definition["availability"] not in allowed_availability:
            raise FeatureValidationError(f"features.{feature_id}.availability is invalid")
        if definition["provenance"] not in allowed_provenance:
            raise FeatureValidationError(f"features.{feature_id}.provenance is invalid")
        if definition["source_authority"] not in allowed_authority:
            raise FeatureValidationError(f"features.{feature_id}.source_authority is invalid")
        if definition["normalization"] not in allowed_normalization:
            raise FeatureValidationError(f"features.{feature_id}.normalization is invalid")
        if definition["score_mode"] not in allowed_score_mode:
            raise FeatureValidationError(f"features.{feature_id}.score_mode is invalid")
        if not isinstance(definition.get("scoring_eligible"), bool):
            raise FeatureValidationError(
                f"features.{feature_id}.scoring_eligible must be boolean"
            )

        numeric_fields = (
            "lookback_points",
            "minimum_history_points",
            "sampling_interval_ms",
            "fresh_after_ms",
            "stale_after_ms",
        )
        values = {
            field: _number(definition.get(field), f"features.{feature_id}.{field}")
            for field in numeric_fields
        }
        if any(value < 0 or not value.is_integer() for value in values.values()):
            raise FeatureValidationError(
                f"features.{feature_id} history and freshness values must be non-negative integers"
            )
        if values["minimum_history_points"] > values["lookback_points"]:
            raise FeatureValidationError(
                f"features.{feature_id} minimum history exceeds lookback"
            )
        if (
            definition["availability"] == "implemented"
            and definition["normalization"] != "none"
            and values["sampling_interval_ms"] <= 0
        ):
            raise FeatureValidationError(
                f"features.{feature_id} implemented feature requires a positive sampling interval"
            )
        if (
            values["stale_after_ms"]
            and values["fresh_after_ms"] > values["stale_after_ms"]
        ):
            raise FeatureValidationError(
                f"features.{feature_id} fresh threshold exceeds stale threshold"
            )

        if definition["scoring_eligible"]:
            if definition["availability"] == "unavailable":
                raise FeatureValidationError(
                    f"features.{feature_id} unavailable feature cannot be scoring eligible"
                )
            if definition["provenance"] not in scoring_provenance:
                raise FeatureValidationError(
                    f"features.{feature_id} scoring provenance is not admitted"
                )
            if definition["source_authority"] not in scoring_authority:
                raise FeatureValidationError(
                    f"features.{feature_id} scoring authority is not admitted"
                )
            if definition["normalization"] == "none":
                raise FeatureValidationError(
                    f"features.{feature_id} scoring feature requires normalization"
                )
            if definition["score_mode"] not in {
                "direct",
                "inverse",
                "playbook_specific",
            }:
                raise FeatureValidationError(
                    f"features.{feature_id} scoring mode is not admitted"
                )

        caveats = definition.get("caveats")
        if (
            not isinstance(caveats, list)
            or not caveats
            or not all(isinstance(item, str) and item for item in caveats)
        ):
            raise FeatureValidationError(
                f"features.{feature_id}.caveats must be a non-empty string array"
            )
        copied_features[feature_id] = json.loads(json.dumps(definition))

    copied = json.loads(json.dumps(data))
    return FeatureCatalog(
        data=copied,
        digest=config_digest(copied),
        features=copied_features,
    )


def load_catalog(path: str | Path) -> FeatureCatalog:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, Mapping):
        raise FeatureValidationError("catalog root must be an object")
    return validate_catalog(data)


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
        stats = (
            ordinary_statistics(values, current_value)
            if method == "ordinary_zscore"
            else robust_statistics(values, current_value)
        )
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
                "method": method,
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


def validate_rulebook_compatibility(
    catalog: FeatureCatalog, rulebook: RegimeRulebook
) -> dict[str, Any]:
    """Verify that scoring-eligible feature blocks exist in the rulebook."""

    rulebook_blocks = set(rulebook.weights)
    scoring_features = {
        feature_id: definition
        for feature_id, definition in catalog.features.items()
        if definition["scoring_eligible"]
    }
    unknown_blocks = sorted(
        {
            definition["block"]
            for definition in scoring_features.values()
            if definition["block"] not in rulebook_blocks
        }
    )
    if unknown_blocks:
        raise FeatureValidationError(
            "scoring features reference unknown rulebook blocks: "
            + ", ".join(unknown_blocks)
        )

    implemented_by_block = {
        block: sorted(
            feature_id
            for feature_id, definition in scoring_features.items()
            if definition["availability"] == "implemented"
            and definition["block"] == block
        )
        for block in sorted(rulebook_blocks)
    }
    uncovered_blocks = sorted(
        block for block, feature_ids in implemented_by_block.items() if not feature_ids
    )
    return {
        "compatible": True,
        "catalog_version": catalog.version,
        "catalog_digest": catalog.digest,
        "rulebook_version": rulebook.version,
        "rulebook_digest": rulebook.digest,
        "implemented_scoring_features_by_block": implemented_by_block,
        "uncovered_blocks": uncovered_blocks,
    }


def _read_json(path: str | Path) -> Mapping[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise FeatureValidationError("JSON root must be an object")
    return value


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tradesync_core.market_features",
        description="Validate and paper-normalize source-governed market features.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-catalog")
    validate.add_argument("catalog")
    normalize = commands.add_parser("normalize")
    normalize.add_argument("catalog")
    normalize.add_argument("request")
    compare = commands.add_parser("compare-methods")
    compare.add_argument("catalog")
    compare.add_argument("request")
    compatibility = commands.add_parser("validate-compatibility")
    compatibility.add_argument("catalog")
    compatibility.add_argument("rulebook")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_cli().parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
        if args.command == "validate-catalog":
            _print_json(
                {
                    "valid": True,
                    "catalog_id": catalog.data["catalog_id"],
                    "version": catalog.version,
                    "digest": catalog.digest,
                    "feature_count": len(catalog.features),
                    "implemented_count": sum(
                        definition["availability"] == "implemented"
                        for definition in catalog.features.values()
                    ),
                    "scoring_eligible_count": sum(
                        bool(definition["scoring_eligible"])
                        for definition in catalog.features.values()
                    ),
                    "implemented_scoring_eligible_count": sum(
                        bool(definition["scoring_eligible"])
                        and definition["availability"] == "implemented"
                        for definition in catalog.features.values()
                    ),
                }
            )
            return 0
        if args.command == "validate-compatibility":
            _print_json(
                validate_rulebook_compatibility(
                    catalog, load_rulebook(args.rulebook)
                )
            )
            return 0
        request = _read_json(args.request)
        if args.command == "normalize":
            _print_json(normalize_feature(catalog, request))
            return 0
        if args.command == "compare-methods":
            _print_json(
                {
                    "ordinary": normalize_feature(
                        catalog, request, "ordinary_zscore"
                    ),
                    "robust": normalize_feature(catalog, request, "robust_zscore"),
                }
            )
            return 0
    except (OSError, json.JSONDecodeError, FeatureValidationError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
