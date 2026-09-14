"""A feature observation carries the time its metric was read, never a later snapshot time."""

from app.feature_extractor import extract_feature_observations, metric_read_times

SNAPSHOT_MS = 1_789_386_150_593
CONTEXT_MS = SNAPSHOT_MS - 37_000  # funding, price, OI and volume were read 37 s before the book


def snapshot(**extra):
    return {
        "venue": "hyperliquid", "symbol": "BTC-PERP", "ts": SNAPSHOT_MS,
        "available_metrics": [
            {"metric": "funding", "last_updated": CONTEXT_MS}, {"metric": "price", "last_updated": CONTEXT_MS},
            {"metric": "oi", "last_updated": CONTEXT_MS}, {"metric": "orderbook", "last_updated": SNAPSHOT_MS},
            {"metric": "microstructure", "last_updated": SNAPSHOT_MS}, {"metric": "bad", "last_updated": "x"},
        ],
        "price": {"mark_price_usd": 77743.0, "oracle_premium_bps": -4.1},
        "funding": {"horizons": {"now": 1.25e-05}},
        "orderbook": {"spread_bps": 0.13, "imbalance_1pct": 0.24},
        "derived": {"return_1h_pct": {"value": 0.4}},
        **extra,
    }


def test_read_times_skip_malformed_metrics() -> None:
    times = metric_read_times(snapshot())
    assert times["funding"] == CONTEXT_MS and times["orderbook"] == SNAPSHOT_MS and "bad" not in times


def test_each_feature_is_stamped_with_its_own_metric_time() -> None:
    by_id = {o["feature_id"]: o for o in extract_feature_observations(snapshot())}
    assert by_id["hl_funding_hourly_rate"]["observed_at_ms"] == CONTEXT_MS
    assert by_id["hl_mark_price_usd"]["observed_at_ms"] == CONTEXT_MS
    assert by_id["hl_spread_bps"]["observed_at_ms"] == SNAPSHOT_MS
    assert by_id["hl_return_1h_pct"]["observed_at_ms"] == SNAPSHOT_MS  # derived at snapshot time
    assert by_id["hl_funding_hourly_rate"]["source_event_id"].endswith(f":{CONTEXT_MS}:hl_funding_hourly_rate")


def test_without_metric_times_the_snapshot_time_is_kept() -> None:
    observations = extract_feature_observations(snapshot(available_metrics=[]))
    assert observations and all(o["observed_at_ms"] == SNAPSHOT_MS for o in observations)
