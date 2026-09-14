"""Liquidity context reads the aggregated book, received liquidations and the liquidation map, and leaves stale parts out."""

from app import liquidity_context
from app.feature_extractor import extract_feature_observations
from tradesync_core.liquidation_map import Bar

NOW_MS = 1_789_390_000_000


def books(stale=False, time_ms=NOW_MS - 2_000):
    return {"3": {"n_sig_figs": 3, "time_ms": time_ms, "stale": stale,
                  "bids": [[99.9, 10.0], [99.0, 60.0], [96.0, 5.0]], "asks": [[100.1, 8.0], [101.0, 20.0]]}}


def test_book_context_reads_balance_and_walls() -> None:
    context = liquidity_context.book_context(books())
    assert context["observed_at_ms"] == NOW_MS - 2_000
    assert context["imbalance"] > 0 and context["bid_wall_bps"] < 0 < context["ask_wall_bps"]
    assert liquidity_context.book_context(books(stale=True)) is None and liquidity_context.book_context({}) is None


def test_liquidation_totals_count_the_last_hour_by_side() -> None:
    events = [{"event_time": 1000.0, "position_side": "long", "notional_usd": 500.0},
              {"event_time": 3000.0, "position_side": "short", "notional_usd": 200.0},
              {"event_time": 3500.0, "position_side": "long", "notional_usd": 100.0}]
    totals = liquidity_context.liquidation_totals(events, now_s=5000.0)  # the first event is 4,000 s old: outside the hour
    assert totals == {"observed_at_ms": 5_000_000, "long_usd": 100, "short_usd": 200, "net_usd": -100, "events": 2}


def test_map_context_needs_enough_bars() -> None:
    bars = [Bar(i * 3600, 101 + (i % 3), 99 - (i % 2), 100, 1_000_000 + 40_000 * i) for i in range(60)]
    context = liquidity_context.map_context(bars, now_s=NOW_MS / 1000)
    assert context["observed_at_ms"] == NOW_MS and context["largest_below_pct"] < 0 < context["largest_above_pct"]
    assert liquidity_context.map_context(bars[:10], now_s=0) is None


def test_attach_writes_only_fresh_parts_and_the_extractor_records_them() -> None:
    liquidity_context._liquidations["BTC-PERP"] = {"observed_at_ms": NOW_MS - 10_000, "long_usd": 900, "short_usd": 100, "net_usd": 800, "events": 3}
    liquidity_context._maps["BTC-PERP"] = {"observed_at_ms": NOW_MS - 60 * 60_000, "skew_3pct": 0.4, "largest_above_pct": 2.0, "largest_below_pct": -3.0}
    payload = liquidity_context.attach({"venue": "hyperliquid", "symbol": "BTC-PERP", "ts": NOW_MS}, books(), now_ms=NOW_MS)
    derived = payload["derived"]
    assert "resting_liquidity" in derived and derived["cex_liquidations_1h"]["net_usd"] == 800
    assert "liquidation_map" not in derived  # an hour old: stale, left out rather than zeroed
    by_id = {o["feature_id"]: o for o in extract_feature_observations(payload)}
    assert by_id["cex_liquidations_net_1h_usd"]["value"] == 800
    assert by_id["cex_liquidations_net_1h_usd"]["observed_at_ms"] == NOW_MS - 10_000
    assert by_id["hl_resting_liquidity_imbalance"]["observed_at_ms"] == NOW_MS - 2_000
    assert "liq_map_skew_3pct" not in by_id
