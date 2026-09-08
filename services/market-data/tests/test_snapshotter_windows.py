import pytest
import time

from app.processors.snapshotter import MarketSnapshotter


def test_window_orders_and_deduplicates_backfilled_timestamps():
    snapshotter = MarketSnapshotter()
    now = int(time.time() * 1000)

    snapshotter._add_to_window(
        "hyperliquid", "BTC-PERP", "funding", {"ts": now, "value": {"rate": 1}}
    )
    snapshotter._add_to_window(
        "hyperliquid",
        "BTC-PERP",
        "funding",
        {"ts": now - 3_600_000, "value": {"rate": 2}},
    )
    snapshotter._add_to_window(
        "hyperliquid", "BTC-PERP", "funding", {"ts": now, "value": {"rate": 3}}
    )

    window = snapshotter._windows["hyperliquid"]["BTC-PERP"]["funding"]
    assert [item["ts"] for item in window] == [now - 3_600_000, now]
    assert window[-1]["value"]["rate"] == 3


def test_change_24h_is_derived_from_the_venue_prev_day_price():
    """Hyperliquid publishes prevDayPx beside the mark in the same response."""
    from app.models import PriceData

    mark, prev = 79017.7, 80297.0
    price = PriceData(
        mark_price_usd=mark,
        oracle_price_usd=79064.4,
        oracle_premium_bps=((mark - 79064.4) / 79064.4) * 10000,
        prev_day_price_usd=prev,
        change_24h_pct=((mark - prev) / prev) * 100,
    )
    assert price.change_24h_pct == pytest.approx(-1.5932, abs=1e-4)


def test_change_24h_is_none_rather_than_zero_when_prev_day_is_missing():
    """A missing reference must read as unavailable, never as a flat 0%."""
    from app.models import PriceData

    price = PriceData(
        mark_price_usd=79017.7,
        oracle_price_usd=79064.4,
        oracle_premium_bps=-5.9,
    )
    assert price.prev_day_price_usd is None
    assert price.change_24h_pct is None
