"""Extract catalog-admitted measurements from a MarketSnapshot payload.

This module deliberately extracts values only. Normalization and regime scoring
remain in ``tradesync_core`` so the API, replay runner, and future backtests use
one mathematical implementation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .snapshot_values import finite as _finite, value_at as _path

# The one-hour return lives in ``return_1h``; ``main`` imports these from here.
from .return_1h import (  # noqa: F401
    RETURN_1H_ANCHOR_TOLERANCE_MS,
    RETURN_1H_WINDOW_MS,
    attach_derived_features,
)


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


# The snapshot metric each feature is read from. A feature carries the time that
# metric was actually read, not the time the snapshot was assembled, so a slow
# or stalled poll can never present an old value as a fresh observation. Derived
# features keep the snapshot time: they are computed when the snapshot is built.
FEATURE_METRIC: dict[str, str] = {
    "hl_mark_price_usd": "price",
    "hl_oracle_premium_bps": "price",
    "hl_spread_bps": "orderbook",
    "hl_orderbook_imbalance_1pct": "orderbook",
    "hl_depth_25bp_usd": "microstructure",
    "hl_buy_impact_5k_bps": "microstructure",
    "hl_funding_hourly_rate": "funding",
    "hl_funding_apr_24h": "funding",
    "hl_open_interest_4h_pct": "oi",
    "hl_volume_24h_usd": "volume",
    "hl_liquidation_total_proxy_usd": "liquidations",
}

# Liquidity context features carry the time their own block was computed
# (app/liquidity_context.py): a book, a liquidation tally or a liquidation map.
DERIVED_BLOCK: dict[str, str] = {
    "hl_resting_liquidity_imbalance": "resting_liquidity",
    "hl_bid_wall_distance_bps": "resting_liquidity",
    "hl_ask_wall_distance_bps": "resting_liquidity",
    "cex_liquidations_net_1h_usd": "cex_liquidations_1h",
    "liq_map_skew_3pct": "liquidation_map",
    "liq_map_largest_above_pct": "liquidation_map",
    "liq_map_largest_below_pct": "liquidation_map",
}


def metric_read_times(snapshot: Mapping[str, Any]) -> dict[str, int]:
    """``{metric: last_updated_ms}`` from the snapshot's ``available_metrics``."""
    times: dict[str, int] = {}
    for metric in snapshot.get("available_metrics") or []:
        if isinstance(metric, Mapping) and isinstance(metric.get("metric"), str):
            read_at = _finite(metric.get("last_updated"))
            if read_at is not None and read_at > 0:
                times[metric["metric"]] = int(read_at)
    return times


def extract_feature_observations(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return finite feature observations already present in one snapshot, each at its metric's read time."""

    venue = str(snapshot.get("venue") or "")
    symbol = str(snapshot.get("symbol") or "")
    snapshot_ms = int(snapshot.get("ts") or 0)
    if venue != "hyperliquid" or not symbol or snapshot_ms <= 0:
        return []
    read_times = metric_read_times(snapshot)

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
        # Derived once in the polling path and written onto the snapshot, so
        # this read stays stateless and cheap. See ``attach_derived_features``.
        "hl_return_1h_pct": _path(snapshot, "derived", "return_1h_pct", "value"),
        # Context only: an external reference venue, visible but not scoring.
        "coinbase_premium_bps": _path(
            snapshot, "derived", "coinbase_premium_bps", "value_bps"
        ),
        # Observed taker flow from the venue trade stream. Absent, not zero,
        # until trades have actually been seen.
        "hl_direct_cvd": _path(snapshot, "derived", "cvd_window_usd", "value"),
        # Context only: GDELT news tone for the coin, recorded so its skill can
        # be measured; it cannot score until it earns a weight.
        "gdelt_news_tone": _path(snapshot, "derived", "gdelt_news_tone", "value"),
        # Context only: Binance perpetual funding and OI, and the funding
        # spread between the two venues. External reference venue, not a
        # trading venue; none of the three can score until it earns a weight.
        "binance_funding_rate_8h": _path(snapshot, "derived", "binance_funding_rate_8h", "value"),
        "binance_open_interest_usd": _path(snapshot, "derived", "binance_open_interest_usd", "value"),
        "funding_spread_vs_binance_bps": _path(
            snapshot, "derived", "funding_spread_vs_binance_bps", "value"
        ),
        "hl_liquidation_total_proxy_usd": _path(
            snapshot, "liquidations", "horizons", "1h", "total_usd"
        ),
        # Liquidity and liquidation context: recorded so their skill can be
        # measured; none scores until it earns a weight.
        "hl_resting_liquidity_imbalance": _path(snapshot, "derived", "resting_liquidity", "imbalance"),
        "hl_bid_wall_distance_bps": _path(snapshot, "derived", "resting_liquidity", "bid_wall_bps"),
        "hl_ask_wall_distance_bps": _path(snapshot, "derived", "resting_liquidity", "ask_wall_bps"),
        "cex_liquidations_net_1h_usd": _path(snapshot, "derived", "cex_liquidations_1h", "net_usd"),
        "liq_map_skew_3pct": _path(snapshot, "derived", "liquidation_map", "skew_3pct"),
        "liq_map_largest_above_pct": _path(snapshot, "derived", "liquidation_map", "largest_above_pct"),
        "liq_map_largest_below_pct": _path(snapshot, "derived", "liquidation_map", "largest_below_pct"),
    }

    observations = []
    for feature_id, raw_value in candidates.items():
        value = _finite(raw_value)
        if value is None:
            continue
        observed_at_ms = min(snapshot_ms, read_times.get(FEATURE_METRIC.get(feature_id, ""), snapshot_ms))
        block_time = _finite(_path(snapshot, "derived", DERIVED_BLOCK[feature_id], "observed_at_ms")) if feature_id in DERIVED_BLOCK else None
        if block_time is not None and block_time > 0:
            observed_at_ms = min(snapshot_ms, int(block_time))
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
