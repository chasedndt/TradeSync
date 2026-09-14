"""The source-governed market feature catalog: its shape, validation and loading."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .regime_weights import config_digest


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
        # A second venue used as a price reference, never as a trading venue.
        # Added in catalog 1.5.0 for Coinbase spot: calling it
        # "authoritative_market_derived" would misdescribe Coinbase as the
        # venue TradeSync trades on, which it is not and will not be.
        "external_reference_venue",
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
    # Which source authorities may influence a score at all. This is the line
    # separating "TradeSync measured it" from "somebody else said so", and it
    # is the most consequential whitelist in the catalog.
    #
    # `external_reference_venue` was added by operator decision on 2026-09-08,
    # to admit Coinbase spot premium. It admits a second venue as a *price
    # reference* only: Hyperliquid remains the sole trading venue, and nothing
    # here grants an external source approval or execution authority.
    scoring_authority = {
        "authoritative_market",
        "authoritative_market_derived",
        "external_reference_venue",
    }

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
            "signal_kind",
            "decision_role",
            "missing_data",
        ):
            if not isinstance(definition.get(field), str) or not definition[field].strip():
                raise FeatureValidationError(
                    f"features.{feature_id}.{field} must be a non-empty string"
                )

        # A feature may only set a trade direction when the catalog says it
        # measures direction. Suitability describes how tradeable conditions
        # are and must never be read as a long or short.
        if definition["signal_kind"] not in {"directional", "suitability", "none"}:
            raise FeatureValidationError(
                f"features.{feature_id}.signal_kind is invalid"
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
