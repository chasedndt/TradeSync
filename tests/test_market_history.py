"""Market history rows are one per minute, skip stale or broken inputs, and retention downsamples by the clock."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tradesync_core.market_history import (
    RETENTION_SQL,
    depth_rows,
    kept_after_downsampling,
    liquidation_rows,
    minute,
    open_interest_row,
)

T = 1_789_384_697_871  # ms


def test_depth_rows_floor_to_the_minute_and_skip_stale_or_one_sided_books() -> None:
    books = {
        "2": {"n_sig_figs": 2, "time_ms": T, "stale": False, "bids": [[77000.0, 1794.08]], "asks": [[78000.0, 1.81]]},
        "3": {"n_sig_figs": 3, "time_ms": T, "stale": True, "bids": [[77900.0, 3.0]], "asks": [[78000.0, 1.0]]},
        "4": {"n_sig_figs": 4, "time_ms": T, "stale": False, "bids": [], "asks": [[78000.0, 1.0]]},
    }
    [row] = depth_rows("BTC-PERP", books)
    symbol, n, at, mid, bids, asks = row
    assert (symbol, n, mid) == ("BTC-PERP", 2, 77500.0)
    assert at == minute(T) and at.second == 0 and at.tzinfo is timezone.utc
    assert bids == [[77000.0, 1794.08]] and asks == [[78000.0, 1.81]]


def test_open_interest_row_reads_the_snapshot_shape_at_the_metric_time() -> None:
    read_at = T - 120_000  # open interest was read two minutes before the snapshot was assembled
    snapshot = {"symbol": "BTC-PERP", "ts": T, "price": {"mark_price_usd": 77743.0, "oracle_price_usd": 77775.0, "oracle_premium_bps": -4.1},
                "available_metrics": [{"metric": "orderbook", "last_updated": T}, {"metric": "oi", "last_updated": read_at}],
                "oi": {"current_usd": 2.89e9}, "funding": {"horizons": {"now": 1.25e-05}}, "volume": {"horizons": {"24h": 1.7e9}}}
    assert open_interest_row(snapshot) == ("BTC-PERP", minute(read_at), 2.89e9, 77743.0, 77775.0, 1.25e-05, -4.1, 1.7e9)
    assert open_interest_row({**snapshot, "available_metrics": []}) is None  # no read time, no row
    assert open_interest_row({**snapshot, "oi": {}}) is None
    assert open_interest_row({**snapshot, "price": {"mark_price_usd": 0}}) is None


def test_liquidation_rows_keep_only_complete_events() -> None:
    good = {"id": "x", "source": "binance", "symbol": "BTC-PERP", "event_time": 100.0, "received_at": 100.4,
            "position_side": "long", "price": 77000.0, "size": 0.5, "notional_usd": 38500.0, "price_kind": "average_fill"}
    rows = liquidation_rows([good, {**good, "source": "ftx"}, {**good, "size": 0}, {**good, "position_side": "flat"}])
    assert len(rows) == 1 and rows[0][:3] == ("binance", "x", "BTC-PERP") and rows[0][4] == "long"


def test_downsampling_keeps_every_minute_then_every_fifteenth_then_nothing() -> None:
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    recent = now - timedelta(days=1, minutes=7)
    older_on_quarter = now - timedelta(days=5, minutes=15)
    older_off_quarter = now - timedelta(days=5, minutes=16)
    assert kept_after_downsampling(recent, now, full_days=3, keep_days=90)
    assert kept_after_downsampling(older_on_quarter, now, full_days=3, keep_days=90)
    assert not kept_after_downsampling(older_off_quarter, now, full_days=3, keep_days=90)
    assert not kept_after_downsampling(now - timedelta(days=91), now, full_days=3, keep_days=90)
    assert {s.split()[2] for s in RETENTION_SQL} == {"market_depth_snapshots", "market_open_interest", "market_liquidation_events"}
