"""Coverage explains itself: each reading's age against its limit, one reason, and per-feed health."""

from __future__ import annotations

from app import regime_lab_health as health
from app.regime_lab import RegimeLabEngine

NOW = 1_789_400_000_000
ENGINE = RegimeLabEngine()


def definition(feature_id):
    return ENGINE.catalog.features[feature_id]


def test_every_catalog_feature_belongs_to_a_named_feed():
    feeds = {feature_id: health.feed_of(spec) for feature_id, spec in ENGINE.catalog.features.items()}
    assert feeds["hl_spread_bps"] == "Hyperliquid order book"
    assert feeds["hl_direct_cvd"] == "Hyperliquid trades"
    assert feeds["coinbase_premium_bps"] == "Coinbase"
    assert feeds["funding_spread_vs_binance_bps"] == "Binance"
    assert feeds["gdelt_news_tone"] == "GDELT"
    assert feeds["hl_liquidation_total_proxy_usd"] == "Hyperliquid market context"
    assert feeds["bitcoin_etf_net_flow_usd"] == health.NO_ADAPTER
    known = {feed for _, feed in health.FEEDS} | {health.NO_ADAPTER}
    assert set(feeds.values()) <= known


def test_age_is_judged_against_the_features_own_stale_limit():
    spread = definition("hl_spread_bps")  # stale after 15 s
    fresh = health.annotate({"status": "ready"}, spread, NOW - 14_999, NOW)
    stale = health.annotate({"status": "ready"}, spread, NOW - 15_000, NOW)
    missing = health.annotate({"status": "unavailable"}, spread, None, NOW)
    future = health.annotate({"status": "ready"}, spread, NOW + 500, NOW)
    assert (fresh["freshness"], fresh["age_ms"], fresh["stale_after_ms"]) == ("fresh", 14_999, 15_000)
    assert fresh["coverage_reason"] == "usable"
    assert (stale["freshness"], stale["coverage_reason"]) == ("stale", "stale")
    assert (missing["freshness"], missing["age_ms"], missing["coverage_reason"]) == ("missing", None, "unavailable")
    assert future["age_ms"] == 0 and future["freshness"] == "fresh"
    no_limit = health.annotate({"status": "not_normalized"}, definition("hl_liquidation_total_proxy_usd"), NOW, NOW)
    assert no_limit["freshness"] == "stale" and no_limit["coverage_reason"] == "display_only"


def test_each_reading_gets_exactly_one_reason_in_order():
    reason = health.coverage_reason
    assert reason({"status": "not_normalized"}, "stale") == "display_only"
    assert reason({"status": "unavailable", "reason": "flat: every recent value identical"}, "stale") == "stale"
    assert reason({"status": "collecting_history"}, "fresh") == "collecting_history"
    assert reason({"status": "ready"}, "fresh") == "usable"
    assert reason({"status": "unavailable", "reason": "flat: every recent value identical"}, "fresh") == "flat"
    assert reason({"status": "unavailable", "reason": "feature is planned in catalog v1.9"}, "fresh") == "unavailable"


def test_fresh_names_an_age_never_a_reason():
    # A fresh reading can be flat, display only or collecting history, so no reason may share the word.
    assert "fresh" not in health.REASONS
    assert set(health.REASONS) == {"usable", "stale", "flat", "collecting_history", "display_only", "unavailable"}


def test_summary_counts_reasons_and_calls_only_fresh_readings_live():
    results = [
        {"feed": "Hyperliquid order book", "freshness": "fresh", "coverage_reason": "usable", "age_ms": 4_000, "stale_after_ms": 15_000},
        {"feed": "Hyperliquid order book", "freshness": "stale", "coverage_reason": "stale", "age_ms": 22_000, "stale_after_ms": 15_000},
        {"feed": "Coinbase", "freshness": "fresh", "coverage_reason": "flat", "age_ms": 4_000, "stale_after_ms": 60_000},
        {"feed": "GDELT", "freshness": "missing", "coverage_reason": "unavailable", "age_ms": None, "stale_after_ms": 3_600_000},
    ]
    summary = health.summarize(results, {"status": "live", "observation_count": 3}, NOW)
    assert summary["live"] is True and summary["fresh_features"] == 2 and summary["feature_count"] == 4
    assert summary["coverage_reasons"] == {
        "usable": 1, "stale": 1, "flat": 1, "collecting_history": 0, "display_only": 0, "unavailable": 1,
    }
    feeds = {feed["feed"]: feed for feed in summary["feeds"]}
    book = feeds["Hyperliquid order book"]
    assert (book["status"], book["newest_age_ms"], book["stale_after_ms"]) == ("partly_stale", 4_000, 15_000)
    assert feeds["Coinbase"]["status"] == "fresh" and feeds["GDELT"]["status"] == "missing"
    assert summary["feeds"][-1]["feed"] == "GDELT"  # missing feeds sort last


def test_nothing_is_live_without_a_fresh_reading_or_without_market_data():
    stale_only = [{"feed": "Coinbase", "freshness": "stale", "coverage_reason": "stale", "age_ms": 90_000, "stale_after_ms": 60_000}]
    assert health.summarize(stale_only, {"status": "live"}, NOW)["live"] is False
    fresh = [{**stale_only[0], "freshness": "fresh", "coverage_reason": "usable"}]
    down = health.summarize(fresh, {"status": "unavailable", "reason": "ConnectError"}, NOW)
    assert down["live"] is False and down["market_data"] == {"status": "unavailable", "reason": "ConnectError", "observation_count": 0}


def test_the_engine_annotates_every_reading_and_the_overview_carries_health():
    tick = [0.13] * 20 + [0.14] * 10
    observations = [
        {"feature_id": "hl_spread_bps", "symbol": "BTC-PERP", "observed_at_ms": NOW - 3_000, "value": 0.14, "source_event_id": "s"},
        {"feature_id": "hl_depth_25bp_usd", "symbol": "BTC-PERP", "observed_at_ms": NOW - 40_000, "value": 3.4e6, "source_event_id": "d"},
        {"feature_id": "hl_mark_price_usd", "symbol": "BTC-PERP", "observed_at_ms": NOW - 3_000, "value": 77_000.0, "source_event_id": "m"},
        {"feature_id": "hl_buy_impact_5k_bps", "symbol": "BTC-PERP", "observed_at_ms": NOW - 3_000, "value": 0.06, "source_event_id": "i"},
    ]
    histories = {
        "hl_spread_bps": [{"ts": NOW - 400_000 + i * 10_000, "value": v} for i, v in enumerate(tick)],
        "hl_depth_25bp_usd": [{"ts": NOW - 400_000 + i * 10_000, "value": 3e6 + i * 1_000} for i in range(30)],
        "hl_buy_impact_5k_bps": [{"ts": NOW - 400_000 + i * 10_000, "value": 0.06} for i in range(30)],
    }
    results = {r["feature_id"]: r for r in ENGINE.normalize_observations(observations, histories, evaluated_at_ms=NOW)}
    assert results["hl_spread_bps"]["coverage_reason"] == "usable"
    assert results["hl_spread_bps"]["normalization"]["method"] == "ordinary_zscore"
    assert results["hl_depth_25bp_usd"]["coverage_reason"] == "stale" and results["hl_depth_25bp_usd"]["age_ms"] == 40_000
    assert results["hl_mark_price_usd"]["coverage_reason"] == "display_only"
    assert results["hl_buy_impact_5k_bps"]["coverage_reason"] == "flat"
    assert results["gdelt_news_tone"]["coverage_reason"] == "unavailable" and results["gdelt_news_tone"]["score_mode"]
    overview = ENGINE.build_overview(list(results.values()), {"status": "live", "observation_count": 4})
    counts = overview["health"]["coverage_reasons"]
    assert sum(counts.values()) == len(ENGINE.catalog.features)
    assert overview["health"]["fresh_features"] == 3 and overview["health"]["live"] is True
