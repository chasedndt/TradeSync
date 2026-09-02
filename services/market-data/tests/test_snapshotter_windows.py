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
