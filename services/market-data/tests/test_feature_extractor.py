from pathlib import Path

import pytest

from app.feature_extractor import (
    _repository_catalog_path,
    extract_feature_observations,
    load_sampling_intervals,
)


def test_extracts_only_explicit_snapshot_fields():
    snapshot = {
        "venue": "hyperliquid",
        "symbol": "BTC-PERP",
        "ts": 1767297600000,
        "price": {
            "mark_price_usd": 100250.0,
            "oracle_price_usd": 100000.0,
            "oracle_premium_bps": 25.0,
        },
        "orderbook": {"spread_bps": 0.9, "imbalance_1pct": 0.12, "mid_price": 100000},
        "microstructure": {
            "depth_usd": {"25bp": 2500000},
            "impact_est_bps": {"5000": 0.8},
        },
        "funding": {"horizons": {"now": 0.0001}, "annualized_24h": 0.876},
        "oi": {"horizons": {"4h": {"delta_pct": 2.4}}},
        "volume": {"horizons": {"24h": 1500000000}},
        "liquidations": {"horizons": {"1h": {"total_usd": 42000}}},
    }
    observations = extract_feature_observations(snapshot)
    values = {item["feature_id"]: item["value"] for item in observations}
    assert len(values) == 11
    assert values["hl_mark_price_usd"] == 100250.0
    assert values["hl_spread_bps"] == 0.9
    assert values["hl_open_interest_4h_pct"] == 2.4
    assert values["hl_oracle_premium_bps"] == 25.0


def test_catalog_declares_sampler_cadences_for_normalized_features():
    intervals = load_sampling_intervals()
    assert intervals["hl_spread_bps"] == 15000
    assert intervals["hl_funding_hourly_rate"] == 3600000
    assert intervals["hl_oracle_premium_bps"] == 300000
    assert "hl_liquidation_total_proxy_usd" not in intervals


def test_repository_catalog_fallback_tolerates_shallow_container_layout():
    assert _repository_catalog_path(Path("/app/app/feature_extractor.py")) is None


def test_batch_history_window_table_matches_the_single_endpoint():
    from app.main import (
        DEFAULT_FEATURE_HISTORY_WINDOW_MS,
        FEATURE_HISTORY_WINDOWS_MS,
    )

    assert FEATURE_HISTORY_WINDOWS_MS["1h"] == 60 * 60 * 1000
    assert FEATURE_HISTORY_WINDOWS_MS["7d"] == 7 * 24 * 60 * 60 * 1000
    # An unknown window falls back to the widest, matching prior behaviour.
    assert (
        FEATURE_HISTORY_WINDOWS_MS.get("nonsense", DEFAULT_FEATURE_HISTORY_WINDOW_MS)
        == FEATURE_HISTORY_WINDOWS_MS["7d"]
    )
