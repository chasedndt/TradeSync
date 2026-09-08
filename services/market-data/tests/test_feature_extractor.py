from pathlib import Path

import pytest

from app.feature_extractor import (
    _repository_catalog_path,
    attach_derived_features,
    derive_return_1h_pct,
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


HOUR_MS = 60 * 60 * 1000


def _snapshot(ts: int, mark: float) -> dict:
    return {
        "venue": "hyperliquid",
        "symbol": "BTC-PERP",
        "ts": ts,
        "price": {"mark_price_usd": mark},
    }


def test_return_1h_uses_anchor_at_or_before_the_one_hour_target():
    now = 1767297600000
    history = [
        {"ts": now - HOUR_MS - 30_000, "value": 100.0},
        {"ts": now - HOUR_MS + 30_000, "value": 999.0},
        {"ts": now - 60_000, "value": 111.0},
    ]
    observation = derive_return_1h_pct(_snapshot(now, 101.0), history)
    assert observation is not None
    # The 999.0 point sits after t-1h and must not become the comparator.
    assert observation["comparator"]["anchor_value"] == 100.0
    assert observation["value"] == pytest.approx(1.0)
    assert observation["feature_id"] == "hl_return_1h_pct"


def test_return_1h_prefers_the_newest_admissible_anchor():
    now = 1767297600000
    history = [
        {"ts": now - HOUR_MS - 200_000, "value": 50.0},
        {"ts": now - HOUR_MS - 10_000, "value": 200.0},
    ]
    observation = derive_return_1h_pct(_snapshot(now, 220.0), history)
    assert observation["comparator"]["anchor_value"] == 200.0
    assert observation["value"] == pytest.approx(10.0)


def test_return_1h_suppressed_when_the_gap_exceeds_the_tolerance():
    now = 1767297600000
    history = [{"ts": now - HOUR_MS - (10 * 60 * 1000), "value": 100.0}]
    assert derive_return_1h_pct(_snapshot(now, 101.0), history) is None


def test_return_1h_suppressed_without_history():
    now = 1767297600000
    assert derive_return_1h_pct(_snapshot(now, 101.0), []) is None


def test_return_1h_suppressed_when_history_is_all_newer_than_the_target():
    now = 1767297600000
    history = [{"ts": now - 120_000, "value": 100.0}]
    assert derive_return_1h_pct(_snapshot(now, 101.0), history) is None


def test_return_1h_rejects_non_positive_or_non_finite_inputs():
    now = 1767297600000
    zero_anchor = [{"ts": now - HOUR_MS, "value": 0.0}]
    assert derive_return_1h_pct(_snapshot(now, 101.0), zero_anchor) is None

    good_anchor = [{"ts": now - HOUR_MS, "value": 100.0}]
    missing_price = {
        "venue": "hyperliquid",
        "symbol": "BTC-PERP",
        "ts": now,
        "price": {},
    }
    assert derive_return_1h_pct(missing_price, good_anchor) is None
    assert derive_return_1h_pct(_snapshot(0, 101.0), good_anchor) is None


def test_return_1h_ignores_malformed_history_points():
    now = 1767297600000
    history = [
        "not-a-point",
        {"ts": None, "value": 100.0},
        {"ts": now - HOUR_MS, "value": "abc"},
        {"ts": now - HOUR_MS - 5_000, "value": 100.0},
    ]
    observation = derive_return_1h_pct(_snapshot(now, 102.0), history)
    assert observation["comparator"]["anchor_value"] == 100.0


def test_return_1h_is_negative_when_price_fell():
    now = 1767297600000
    history = [{"ts": now - HOUR_MS, "value": 100.0}]
    observation = derive_return_1h_pct(_snapshot(now, 97.5), history)
    assert observation["value"] == pytest.approx(-2.5)


def test_catalog_now_samples_the_return_feature():
    intervals = load_sampling_intervals()
    assert intervals["hl_return_1h_pct"] == 60000


def test_attach_derived_writes_the_return_onto_the_snapshot():
    now = 1767297600000
    snapshot = _snapshot(now, 101.0)
    history = [{"ts": now - HOUR_MS, "value": 100.0}]
    attached = attach_derived_features(snapshot, history)
    derived = attached["derived"]["return_1h_pct"]
    assert derived["value"] == pytest.approx(1.0)
    assert derived["comparator"]["anchor_value"] == 100.0


def test_attach_derived_leaves_the_snapshot_alone_without_an_anchor():
    now = 1767297600000
    snapshot = _snapshot(now, 101.0)
    assert "derived" not in attach_derived_features(snapshot, [])


def test_extractor_reads_the_attached_return_without_touching_history():
    now = 1767297600000
    snapshot = _snapshot(now, 101.0)
    attach_derived_features(snapshot, [{"ts": now - HOUR_MS, "value": 100.0}])
    values = {item["feature_id"]: item["value"] for item in
              extract_feature_observations(snapshot)}
    assert values["hl_return_1h_pct"] == pytest.approx(1.0)


def test_extractor_omits_the_return_when_nothing_was_derived():
    now = 1767297600000
    observations = extract_feature_observations(_snapshot(now, 101.0))
    assert "hl_return_1h_pct" not in {o["feature_id"] for o in observations}


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
