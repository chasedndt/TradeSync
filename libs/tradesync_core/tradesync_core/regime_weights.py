"""Versioned, explainable regime weighting for paper-shadow evaluation.

This module deliberately does not replace the legacy production scorer. It is a
deterministic foundation for loading, validating, explaining, and comparing
versioned rulebooks before any rulebook can be promoted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .feature_weights import (
    FEATURE_WEIGHTS_KEY,
    FeatureWeightError,
    diff_feature_weights,
    feature_weights_of,
    validate_feature_weights,
)


class RulebookValidationError(ValueError):
    """Raised when a rulebook or score input violates its contract."""


@dataclass(frozen=True)
class RegimeRulebook:
    """Validated rulebook plus the digest needed for replay evidence."""

    data: dict[str, Any]
    digest: str
    weights: dict[str, float]
    compression_k: float
    risk_caps: dict[str, float]

    @property
    def version(self) -> str:
        return str(self.data["version"])

    @property
    def rulebook_id(self) -> str:
        return str(self.data["rulebook_id"])

    @property
    def feature_weights(self) -> dict[str, float]:
        """Per-feature multipliers; empty means every feature counts once."""
        return feature_weights_of(self.data)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def config_digest(value: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 digest for a JSON-compatible configuration."""

    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RulebookValidationError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise RulebookValidationError(f"{field} must be finite")
    return number


def validate_rulebook(data: Mapping[str, Any]) -> RegimeRulebook:
    """Validate configuration and return a typed, replayable rulebook."""

    required_text = (
        "schema_version",
        "rulebook_id",
        "version",
        "status",
        "environment",
        "horizon",
    )
    for field in required_text:
        if not isinstance(data.get(field), str) or not str(data[field]).strip():
            raise RulebookValidationError(f"{field} must be a non-empty string")

    if data["schema_version"] != "regime_rulebook_v1":
        raise RulebookValidationError("schema_version must be regime_rulebook_v1")
    if data["status"] not in {"draft", "paper_active", "retired"}:
        raise RulebookValidationError("status must be draft, paper_active, or retired")
    if data["environment"] != "paper":
        raise RulebookValidationError("v1 rulebooks are restricted to paper mode")

    normalization = data.get("normalization")
    if not isinstance(normalization, Mapping):
        raise RulebookValidationError("normalization must be an object")
    if normalization.get("method") != "tanh_zscore":
        raise RulebookValidationError("normalization.method must be tanh_zscore")
    compression_k = _number(normalization.get("compression_k"), "normalization.compression_k")
    if compression_k <= 0:
        raise RulebookValidationError("normalization.compression_k must be greater than 0")

    validation = data.get("validation")
    if not isinstance(validation, Mapping):
        raise RulebookValidationError("validation must be an object")
    expected_sum = _number(validation.get("weight_sum"), "validation.weight_sum")
    tolerance = _number(validation.get("weight_tolerance"), "validation.weight_tolerance")
    max_weight = _number(
        validation.get("max_single_block_weight"),
        "validation.max_single_block_weight",
    )
    if tolerance < 0 or not 0 < max_weight <= 1:
        raise RulebookValidationError("weight tolerance and maximum block weight are invalid")

    blocks = data.get("blocks")
    if not isinstance(blocks, Mapping) or not blocks:
        raise RulebookValidationError("blocks must be a non-empty object")

    weights: dict[str, float] = {}
    for name, block in blocks.items():
        if not isinstance(name, str) or not name:
            raise RulebookValidationError("every block must have a name")
        if not isinstance(block, Mapping):
            raise RulebookValidationError(f"blocks.{name} must be an object")
        weight = _number(block.get("weight"), f"blocks.{name}.weight")
        if weight < 0 or weight > max_weight:
            raise RulebookValidationError(
                f"blocks.{name}.weight must be between 0 and {max_weight}"
            )
        weights[name] = weight

    total_weight = sum(weights.values())
    if not math.isclose(total_weight, expected_sum, abs_tol=tolerance, rel_tol=0):
        raise RulebookValidationError(
            f"block weights sum to {total_weight:.12g}; expected {expected_sum:.12g}"
        )

    quality = data.get("quality")
    if not isinstance(quality, Mapping):
        raise RulebookValidationError("quality must be an object")
    coverage_threshold = _number(
        quality.get("minimum_coverage_for_normal_paper_risk"),
        "quality.minimum_coverage_for_normal_paper_risk",
    )
    if not 0 <= coverage_threshold <= 1:
        raise RulebookValidationError("minimum coverage must be between 0 and 1")

    paper_risk = data.get("paper_risk")
    if not isinstance(paper_risk, Mapping):
        raise RulebookValidationError("paper_risk must be an object")
    if paper_risk.get("combination_rule") != "minimum_cap_wins":
        raise RulebookValidationError("paper_risk.combination_rule must be minimum_cap_wins")

    for field in (
        "base_multiplier",
        "minimum_multiplier",
        "maximum_multiplier",
        "unknown_flag_multiplier",
    ):
        value = _number(paper_risk.get(field), f"paper_risk.{field}")
        if not 0 <= value <= 1:
            raise RulebookValidationError(f"paper_risk.{field} must be between 0 and 1")

    minimum = float(paper_risk["minimum_multiplier"])
    maximum = float(paper_risk["maximum_multiplier"])
    base = float(paper_risk["base_multiplier"])
    if minimum > maximum or not minimum <= base <= maximum:
        raise RulebookValidationError("paper risk minimum, base, and maximum are inconsistent")

    caps = paper_risk.get("caps")
    if not isinstance(caps, Mapping):
        raise RulebookValidationError("paper_risk.caps must be an object")
    risk_caps: dict[str, float] = {}
    for flag, raw_cap in caps.items():
        cap = _number(raw_cap, f"paper_risk.caps.{flag}")
        if not minimum <= cap <= maximum:
            raise RulebookValidationError(
                f"paper_risk.caps.{flag} must be between {minimum} and {maximum}"
            )
        risk_caps[str(flag)] = cap

    try:
        validate_feature_weights(data.get(FEATURE_WEIGHTS_KEY))
    except FeatureWeightError as exc:
        raise RulebookValidationError(str(exc)) from exc

    copied = json.loads(json.dumps(data))
    return RegimeRulebook(
        data=copied,
        digest=config_digest(copied),
        weights=weights,
        compression_k=compression_k,
        risk_caps=risk_caps,
    )


def load_rulebook(path: str | Path) -> RegimeRulebook:
    """Load and validate a rulebook JSON file."""

    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, Mapping):
        raise RulebookValidationError("rulebook root must be an object")
    return validate_rulebook(data)


def bounded_z_score(z_value: float, compression_k: float = 2.0) -> float:
    """Compress any finite z-score into the open interval (-1, 1)."""

    z = _number(z_value, "z_value")
    k = _number(compression_k, "compression_k")
    if k <= 0:
        raise RulebookValidationError("compression_k must be greater than 0")
    result = math.tanh(z / k)
    # Mathematically tanh only approaches the endpoints. IEEE-754 floating
    # point rounds sufficiently extreme finite inputs to exactly +/-1, so keep
    # the documented open-interval contract explicit at machine precision.
    if result >= 1.0:
        return math.nextafter(1.0, 0.0)
    if result <= -1.0:
        return math.nextafter(-1.0, 0.0)
    return result


def _validate_named_values(
    values: Mapping[str, Any],
    configured_names: set[str],
    field: str,
    minimum: float,
    maximum: float,
) -> dict[str, float]:
    if not isinstance(values, Mapping):
        raise RulebookValidationError(f"{field} must be an object")
    unknown = sorted(set(values) - configured_names)
    if unknown:
        raise RulebookValidationError(f"{field} contains unknown blocks: {', '.join(unknown)}")

    result: dict[str, float] = {}
    for name, raw_value in values.items():
        value = _number(raw_value, f"{field}.{name}")
        if not minimum <= value <= maximum:
            raise RulebookValidationError(
                f"{field}.{name} must be between {minimum} and {maximum}"
            )
        result[name] = value
    return result


def evaluate_blocks(
    rulebook: RegimeRulebook,
    block_scores: Mapping[str, Any],
    data_quality: Mapping[str, Any] | None = None,
    risk_flags: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Calculate a quality-adjusted score and deterministic paper-risk cap.

    The directional/suitability score is:

        sum(weight * quality * score) / sum(weight * quality)

    Missing blocks receive quality zero. Paper risk is separate: the most
    conservative active cap wins, and unknown flags fail closed.
    """

    configured_names = set(rulebook.weights)
    scores = _validate_named_values(
        block_scores,
        configured_names,
        "block_scores",
        -1.0,
        1.0,
    )
    qualities = _validate_named_values(
        data_quality or {},
        configured_names,
        "data_quality",
        0.0,
        1.0,
    )

    contributions: dict[str, dict[str, float]] = {}
    numerator = 0.0
    effective_weight = 0.0
    missing_blocks: list[str] = []

    for name, weight in rulebook.weights.items():
        if name not in scores:
            score = 0.0
            quality_value = 0.0
            missing_blocks.append(name)
        else:
            score = scores[name]
            quality_value = qualities.get(name, 1.0)

        weighted_quality = weight * quality_value
        contribution = weighted_quality * score
        numerator += contribution
        effective_weight += weighted_quality
        contributions[name] = {
            "weight": weight,
            "score": score,
            "quality": quality_value,
            "weighted_quality": round(weighted_quality, 12),
            "raw_contribution": round(contribution, 12),
        }

    weighted_score = numerator / effective_weight if effective_weight > 0 else 0.0
    coverage = effective_weight

    if isinstance(risk_flags, (str, bytes)) or (
        risk_flags is not None and not isinstance(risk_flags, Sequence)
    ):
        raise RulebookValidationError("risk_flags must be an array of strings")
    flags: list[str] = []
    for flag in risk_flags or []:
        if not isinstance(flag, str) or not flag:
            raise RulebookValidationError("risk_flags must contain non-empty strings")
        if flag not in flags:
            flags.append(flag)

    quality_config = rulebook.data["quality"]
    if coverage == 0:
        if "no_data_coverage" not in flags:
            flags.append("no_data_coverage")
    elif coverage < float(quality_config["minimum_coverage_for_normal_paper_risk"]):
        if "low_data_coverage" not in flags:
            flags.append("low_data_coverage")

    paper_risk = rulebook.data["paper_risk"]
    caps_applied: list[dict[str, Any]] = []
    cap_values = [float(paper_risk["base_multiplier"])]
    for flag in flags:
        known = flag in rulebook.risk_caps
        cap = (
            rulebook.risk_caps[flag]
            if known
            else float(paper_risk["unknown_flag_multiplier"])
        )
        cap_values.append(cap)
        caps_applied.append({"flag": flag, "cap": cap, "known": known})

    risk_multiplier = min(cap_values)
    risk_multiplier = max(float(paper_risk["minimum_multiplier"]), risk_multiplier)
    risk_multiplier = min(float(paper_risk["maximum_multiplier"]), risk_multiplier)

    return {
        "rulebook_id": rulebook.rulebook_id,
        "rulebook_version": rulebook.version,
        "config_digest": rulebook.digest,
        "weighted_score": round(weighted_score, 12),
        "data_coverage": round(coverage, 12),
        "paper_risk_multiplier": risk_multiplier,
        "contributions": contributions,
        "missing_blocks": missing_blocks,
        "risk_caps_applied": caps_applied,
        "calculation": "sum(weight * quality * score) / sum(weight * quality)",
    }


def diff_rulebooks(before: RegimeRulebook, after: RegimeRulebook) -> dict[str, Any]:
    """Return a focused, machine-readable comparison of two rulebooks."""

    block_names = sorted(set(before.weights) | set(after.weights))
    weight_changes = {
        name: {
            "before": before.weights.get(name),
            "after": after.weights.get(name),
            "delta": (
                None
                if name not in before.weights or name not in after.weights
                else after.weights[name] - before.weights[name]
            ),
        }
        for name in block_names
        if before.weights.get(name) != after.weights.get(name)
    }

    cap_names = sorted(set(before.risk_caps) | set(after.risk_caps))
    risk_cap_changes = {
        name: {
            "before": before.risk_caps.get(name),
            "after": after.risk_caps.get(name),
        }
        for name in cap_names
        if before.risk_caps.get(name) != after.risk_caps.get(name)
    }

    return {
        "before": {"version": before.version, "digest": before.digest},
        "after": {"version": after.version, "digest": after.digest},
        "weight_changes": weight_changes,
        "feature_weight_changes": diff_feature_weights(before.feature_weights, after.feature_weights),
        "risk_cap_changes": risk_cap_changes,
        "compression_k": {
            "before": before.compression_k,
            "after": after.compression_k,
        },
    }


def _read_inputs(path: str | Path) -> Mapping[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise RulebookValidationError("score input root must be an object")
    return value


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tradesync_core.regime_weights",
        description="Validate, explain, score, and compare TradeSync regime rulebooks.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate one rulebook")
    validate.add_argument("rulebook")

    explain = commands.add_parser("explain", help="show the active mathematical choices")
    explain.add_argument("rulebook")

    score = commands.add_parser("score", help="score one block-input fixture")
    score.add_argument("rulebook")
    score.add_argument("inputs")

    diff = commands.add_parser("diff", help="compare two rulebook versions")
    diff.add_argument("before")
    diff.add_argument("after")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_cli().parse_args(argv)
    try:
        if args.command == "validate":
            rulebook = load_rulebook(args.rulebook)
            _print_json(
                {
                    "valid": True,
                    "rulebook_id": rulebook.rulebook_id,
                    "version": rulebook.version,
                    "digest": rulebook.digest,
                    "block_count": len(rulebook.weights),
                    "weight_sum": sum(rulebook.weights.values()),
                }
            )
            return 0

        if args.command == "explain":
            rulebook = load_rulebook(args.rulebook)
            _print_json(
                {
                    "rulebook_id": rulebook.rulebook_id,
                    "version": rulebook.version,
                    "normalization": f"tanh(z / {rulebook.compression_k:g})",
                    "weights": rulebook.weights,
                    "paper_risk_rule": "minimum active cap wins",
                    "paper_risk_caps": rulebook.risk_caps,
                    "activation_mode": rulebook.data["governance"]["activation_mode"],
                }
            )
            return 0

        if args.command == "score":
            rulebook = load_rulebook(args.rulebook)
            inputs = _read_inputs(args.inputs)
            _print_json(
                evaluate_blocks(
                    rulebook,
                    inputs.get("block_scores", {}),
                    inputs.get("data_quality", {}),
                    inputs.get("risk_flags", []),
                )
            )
            return 0

        if args.command == "diff":
            _print_json(diff_rulebooks(load_rulebook(args.before), load_rulebook(args.after)))
            return 0
    except (OSError, json.JSONDecodeError, RulebookValidationError) as exc:
        print(f"ERROR: {exc}")
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
