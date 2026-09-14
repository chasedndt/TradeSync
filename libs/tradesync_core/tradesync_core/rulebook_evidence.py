"""Evaluate normalised feature results under one rulebook: suitability and direction.

The regime engine normalises every feature once. Which rulebook then weighs
those results is a separate choice: the rulebook file, or a version the operator
adopted. This is the one composition every caller uses, so the Regime Lab and
the paper scorer cannot weigh the same readings two different ways.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .market_features import FeatureCatalog
from .regime_lab import aggregate_directional_evidence, aggregate_feature_evidence
from .regime_weights import RegimeRulebook, evaluate_blocks


def evaluate_rulebook_evidence(
    catalog: FeatureCatalog,
    rulebook: RegimeRulebook,
    feature_results: Sequence[Mapping[str, Any]],
    risk_flags: Sequence[str] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(evaluation, directional)`` exactly as the producer consumes them."""

    evidence = aggregate_feature_evidence(catalog, rulebook, feature_results)
    evaluation = evaluate_blocks(rulebook, evidence.block_scores, evidence.data_quality, list(risk_flags))
    directional = aggregate_directional_evidence(catalog, feature_results, rulebook.feature_weights)
    return evaluation, directional.to_dict()
