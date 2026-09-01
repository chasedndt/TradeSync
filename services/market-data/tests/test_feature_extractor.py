from app.feature_extractor import extract_feature_observations, load_sampling_intervals


def test_extracts_only_explicit_snapshot_fields():
    snapshot = {
        "venue": "hyperliquid",
        "symbol": "BTC-PERP",
        "ts": 1767297600000,
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
    assert len(values) == 9
    assert values["hl_spread_bps"] == 0.9
    assert values["hl_open_interest_4h_pct"] == 2.4
    assert "hl_mark_price_usd" not in values


def test_catalog_declares_sampler_cadences_for_normalized_features():
    intervals = load_sampling_intervals()
    assert intervals["hl_spread_bps"] == 15000
    assert intervals["hl_funding_hourly_rate"] == 3600000
    assert "hl_liquidation_total_proxy_usd" not in intervals
