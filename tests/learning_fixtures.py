"""Stored paper decisions shaped exactly as core-scorer writes them, for learning tests."""

from __future__ import annotations

from typing import Any

NOW_MS = 1_788_800_000_000

POLICY = {
    "direction_deadband": 0.05,
    "direction_enter_threshold": 0.15,
    "maximum_evidence_age_ms": 120_000,
    "minimum_coverage_to_emit": 0.3,
    "minimum_directional_coverage": 0.5,
    "note": "research settings",
}


def stored_decision(
    direction: str = "LONG",
    ret: float = 0.01,
    cvd: float = 0.47,
    spread: float = -0.6,
    depth: float = 0.2,
    liquidity: bool = True,
    cvd_weight: float | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A ``paper_signal_v1`` payload with two directional and two liquidity readings."""

    weight = 1.0 if cvd_weight is None else cvd_weight
    directional_score = (ret + cvd * weight) / (1.0 + weight)
    contributors = [
        {"feature_id": "hl_return_1h_pct", "score": ret, "quality": 1.0},
        {"feature_id": "hl_direct_cvd", "score": cvd, "quality": 1.0},
    ]
    if cvd_weight is not None:
        contributors[1]["weight"] = cvd_weight
    features = [
        {"feature_id": "hl_return_1h_pct", "block": "price_volatility", "score": ret, "data_quality": 1.0, "provenance": "derived"},
        {"feature_id": "hl_direct_cvd", "block": "price_volatility", "score": cvd, "data_quality": 1.0, "provenance": "observed"},
    ]
    blocks = {
        "price_volatility": {"weight": 0.3, "score": (ret + cvd) / 2, "quality": 1.0, "weighted_quality": 0.3},
        "liquidity": {"weight": 0.25, "score": 0.0, "quality": 0.0, "weighted_quality": 0.0},
        "positioning": {"weight": 0.2, "score": 0.0, "quality": 0.0, "weighted_quality": 0.0},
        "spot_premium": {"weight": 0.15, "score": 0.0, "quality": 0.0, "weighted_quality": 0.0},
        "macro_flows": {"weight": 0.1, "score": 0.0, "quality": 0.0, "weighted_quality": 0.0},
    }
    if liquidity:
        features += [
            {"feature_id": "hl_spread_bps", "block": "liquidity", "score": spread, "data_quality": 0.5, "provenance": "derived"},
            {"feature_id": "hl_depth_25bp_usd", "block": "liquidity", "score": depth, "data_quality": 0.5, "provenance": "derived"},
        ]
        blocks["liquidity"] = {"weight": 0.25, "score": (spread + depth) / 2, "quality": 0.5, "weighted_quality": 0.125}
    return {
        "schema_version": "paper_signal_v1",
        "admitted": True,
        "direction": direction,
        "directional_score": directional_score,
        "directional_coverage": 0.666666666667,
        "contributing_features": features,
        "evidence": {
            "rulebook_id": "tradesync-intraday-regime",
            "rulebook_version": "1.0.0",
            "rulebook_digest": "digest-1",
            "catalog_id": "tradesync-hyperliquid-market-features",
            "catalog_version": "1.7.0",
            "catalog_digest": "catalog-digest",
            "evaluated_at_ms": NOW_MS,
            "policy": dict(POLICY if policy is None else policy),
            "previous_direction": None,
            "contributions": blocks,
            "directional": {
                "score": directional_score,
                "coverage": 0.666666666667,
                "contributors": contributors,
                "admitted_feature_ids": ["hl_return_1h_pct", "hl_direct_cvd", "coinbase_premium_bps"],
            },
        },
    }
