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
from typing import Any, Mapping, Sequence


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


# ``hl_return_1h_pct`` is the only price/volatility feature the regime rulebook
# admits for a generic directional score, so its comparator is defined here
# rather than inferred at call sites. The catalog comparator is "mark price at
# or immediately before t minus 1 hour"; a gap wider than the tolerance below
# means the anchor is no longer a one-hour comparator and no value is emitted.
RETURN_1H_WINDOW_MS = 60 * 60 * 1000
RETURN_1H_ANCHOR_TOLERANCE_MS = int(
    os.getenv("RETURN_1H_ANCHOR_TOLERANCE_MS", str(5 * 60 * 1000))
)


def select_return_anchor(
    history: Sequence[Mapping[str, Any]],
    observed_at_ms: int,
    window_ms: int = RETURN_1H_WINDOW_MS,
    tolerance_ms: int = RETURN_1H_ANCHOR_TOLERANCE_MS,
) -> dict[str, Any] | None:
    """Return the newest history point at or before ``observed_at_ms - window_ms``.

    Selecting at-or-before rather than nearest keeps the comparator from
    reaching forward into a shorter interval when sampling is irregular. The
    tolerance rejects an anchor stranded on the far side of a data gap.
    """

    target_ms = observed_at_ms - window_ms
    earliest_ms = target_ms - tolerance_ms
    anchor: dict[str, Any] | None = None
    for point in history:
        if not isinstance(point, Mapping):
            continue
        ts = point.get("ts")
        value = _finite(point.get("value"))
        if not isinstance(ts, int) or isinstance(ts, bool) or value is None:
            continue
        if ts > target_ms or ts < earliest_ms:
            continue
        if anchor is None or ts > anchor["ts"]:
            anchor = {"ts": ts, "value": value}
    return anchor


def derive_return_1h_pct(
    snapshot: Mapping[str, Any],
    mark_price_history: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Derive the one-hour mark-price return as a percent change.

    Returns ``None`` when the snapshot is not usable or no admissible anchor
    exists, so the price/volatility block loses coverage instead of scoring a
    fabricated zero.
    """

    venue = str(snapshot.get("venue") or "")
    symbol = str(snapshot.get("symbol") or "")
    observed_at_ms = int(snapshot.get("ts") or 0)
    if venue != "hyperliquid" or not symbol or observed_at_ms <= 0:
        return None

    current = _finite(_path(snapshot, "price", "mark_price_usd"))
    if current is None:
        return None

    anchor = select_return_anchor(mark_price_history, observed_at_ms)
    if anchor is None or anchor["value"] <= 0:
        return None

    value = (current - anchor["value"]) / anchor["value"] * 100.0
    if not math.isfinite(value):
        return None

    return {
        "feature_id": "hl_return_1h_pct",
        "venue": venue,
        "symbol": symbol,
        "timeframe": "snapshot",
        "observed_at_ms": observed_at_ms,
        "value": value,
        "source_event_id": (
            f"return1h:{venue}:{symbol}:{anchor['ts']}:{observed_at_ms}"
        ),
        "comparator": {
            "anchor_ts_ms": anchor["ts"],
            "anchor_value": anchor["value"],
            "anchor_lag_ms": observed_at_ms - anchor["ts"],
            "current_value": current,
        },
    }


def attach_derived_features(
    snapshot: dict[str, Any],
    mark_price_history: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Write history-backed derivations onto the snapshot before it is stored.

    Deriving here rather than on every read keeps ``/features`` a stateless
    lookup. The regime engine fans out one history request per normalized
    feature, so an extra round trip on that first hop is paid by every one of
    them.
    """

    observation = derive_return_1h_pct(snapshot, mark_price_history)
    if observation is None:
        return snapshot
    derived = snapshot.setdefault("derived", {})
    derived["return_1h_pct"] = {
        "value": observation["value"],
        "comparator": observation["comparator"],
        "source_event_id": observation["source_event_id"],
    }
    return snapshot
