"""Extract catalog-admitted measurements from a MarketSnapshot payload.

This module deliberately extracts values only. Normalization and regime scoring
remain in ``tradesync_core`` so the API, replay runner, and future backtests use
one mathematical implementation.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Mapping


def _repository_catalog_path(module_file: Path | None = None) -> Path | None:
    """Return the checkout catalog path when the module is nested deeply enough.

    The source checkout places this module four levels below the repository
    root. The Docker image deliberately uses the shallower ``/app/app`` layout,
    so indexing ``parents[3]`` there must not abort startup before the copied
    container catalog can be checked.
    """

    module_path = (module_file or Path(__file__)).resolve()
    if len(module_path.parents) <= 3:
        return None
    return (
        module_path.parents[3]
        / "config"
        / "features"
        / "market-feature-catalog-v1.json"
    )


def _catalog_path() -> Path:
    configured = os.getenv("MARKET_FEATURE_CATALOG_PATH")
    candidates = [
        Path(configured) if configured else None,
        Path("/app/config/features/market-feature-catalog-v1.json"),
        _repository_catalog_path(),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise FileNotFoundError("market feature catalog was not found")


def load_sampling_intervals(path: Path | None = None) -> dict[str, int]:
    with (path or _catalog_path()).open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)
    return {
        feature_id: int(definition.get("sampling_interval_ms", 0))
        for feature_id, definition in catalog["features"].items()
        if definition.get("availability") == "implemented"
        and int(definition.get("sampling_interval_ms", 0)) > 0
    }


def _path(payload: Mapping[str, Any], *parts: str) -> Any:
    value: Any = payload
    for part in parts:
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def extract_feature_observations(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return finite feature observations already present in one snapshot."""

    venue = str(snapshot.get("venue") or "")
    symbol = str(snapshot.get("symbol") or "")
    observed_at_ms = int(snapshot.get("ts") or 0)
    if venue != "hyperliquid" or not symbol or observed_at_ms <= 0:
        return []

    candidates = {
        "hl_mark_price_usd": _path(snapshot, "price", "mark_price_usd"),
        "hl_spread_bps": _path(snapshot, "orderbook", "spread_bps"),
        "hl_depth_25bp_usd": _path(snapshot, "microstructure", "depth_usd", "25bp"),
        "hl_buy_impact_5k_bps": _path(
            snapshot, "microstructure", "impact_est_bps", "5000"
        ),
        "hl_funding_hourly_rate": _path(snapshot, "funding", "horizons", "now"),
        "hl_funding_apr_24h": _path(snapshot, "funding", "annualized_24h"),
        "hl_open_interest_4h_pct": _path(snapshot, "oi", "horizons", "4h", "delta_pct"),
        "hl_volume_24h_usd": _path(snapshot, "volume", "horizons", "24h"),
        "hl_orderbook_imbalance_1pct": _path(snapshot, "orderbook", "imbalance_1pct"),
        "hl_oracle_premium_bps": _path(snapshot, "price", "oracle_premium_bps"),
        "hl_liquidation_total_proxy_usd": _path(
            snapshot, "liquidations", "horizons", "1h", "total_usd"
        ),
    }

    observations = []
    for feature_id, raw_value in candidates.items():
        value = _finite(raw_value)
        if value is None:
            continue
        observations.append(
            {
                "feature_id": feature_id,
                "venue": venue,
                "symbol": symbol,
                "timeframe": "snapshot",
                "observed_at_ms": observed_at_ms,
                "value": value,
                "source_event_id": (
                    f"snapshot:{venue}:{symbol}:{observed_at_ms}:{feature_id}"
                ),
            }
        )
    return observations
