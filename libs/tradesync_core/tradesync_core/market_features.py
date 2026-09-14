"""Source-governed market feature catalog and paper-shadow normalization.

The catalog lives in ``feature_catalog``, the dispersion statistics in
``feature_statistics`` and per-request normalization in
``feature_normalization``. This module keeps the names every caller already
imports, the rulebook compatibility check and the command line.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .feature_catalog import (  # noqa: F401 - re-exported for existing callers
    FeatureCatalog,
    FeatureValidationError,
    load_catalog,
    validate_catalog,
)
from .feature_normalization import normalize_feature  # noqa: F401
from .feature_statistics import (  # noqa: F401
    freshness_factor,
    ordinary_statistics,
    robust_statistics,
)
from .regime_weights import RegimeRulebook, load_rulebook


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
