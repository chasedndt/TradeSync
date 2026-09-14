"""The liquidity heatmap averages recorded books per bucket; the liquidation map adds, trims and clears estimated levels."""

from __future__ import annotations

from datetime import datetime, timezone

from tradesync_core.liquidation_map import Bar, PriceGrid, estimate, liquidation_price, skew
from tradesync_core.liquidity_heatmap import build, walls

T0 = 1_789_380_000


def book(minute, bids, asks, mid):
    return {"observed_at": datetime.fromtimestamp(T0 + minute * 60, timezone.utc), "mid_price": mid, "bids": bids, "asks": asks}


def test_heatmap_cells_average_resting_notional_per_bucket_and_side() -> None:
    rows = [
        book(0, [[99.0, 10.0]], [[101.0, 4.0]], 100.0),
        book(1, [[99.0, 30.0]], [[101.0, 4.0]], 100.2),
        book(6, [[98.0, 5.0]], [[102.0, 1.0]], 100.0),
        book(99, [[1.0, 1.0]], [[2.0, 1.0]], 1.5),  # outside the window
    ]
    out = build(rows, bucket_seconds=300, start_s=T0, end_s=T0 + 600)
    assert out["times"] == [T0, T0 + 300] and out["books_per_bucket"] == [2, 1]
    prices = out["prices"]
    assert prices == [98.0, 99.0, 101.0, 102.0]
    assert [0, prices.index(99.0), 1980] in out["bids"]  # (990 + 2970) / 2 books
    assert [0, prices.index(101.0), 404] in out["asks"]
    assert [1, prices.index(98.0), 490] in out["bids"] and out["max_usd"] == 1980
    assert out["mid"][0] == [T0, 100.1] and out["price_step"] == 1.0


def test_walls_find_the_largest_levels_near_price_and_the_balance() -> None:
    out = walls([[99.0, 10.0], [96.0, 50.0], [80.0, 1000.0]], [[101.0, 2.0], [104.0, 1.0]], mid=100.0)
    assert out["below"] == {"price": 96.0, "usd": 4800, "distance_bps": -400.0}  # 80 is beyond 5%
    assert out["above"]["price"] == 101.0 and out["bid_usd"] == 5790 and out["ask_usd"] == 306
    assert 0.89 < out["imbalance"] < 0.9


def test_liquidation_prices_sit_below_longs_and_above_shorts() -> None:
    assert round(liquidation_price(100.0, 10, 0.005, "long"), 6) == 90.5
    assert round(liquidation_price(100.0, 10, 0.005, "short"), 6) == 109.5
    grid = PriceGrid(50.0, 200.0, bins=100)
    assert grid.index(49.0) is None and grid.index(100.0) == 50


def test_rising_open_interest_adds_levels_and_price_clears_them() -> None:
    bars = [Bar(0, 101, 99, 100, 1_000_000), Bar(3600, 101, 99, 100, 2_000_000), Bar(7200, 101, 99, 100, 2_000_000)]
    out = estimate(bars, leverage=((10, 1.0),), maintenance=0.0, bins=400)
    assert out["times"] == [0, 3600, 7200]
    long_levels = [p for p, usd in out["profile"]["long"]]
    short_levels = [p for p, usd in out["profile"]["short"]]
    assert all(89 < p < 91 for p in long_levels) and all(109 < p < 111 for p in short_levels)
    assert sum(usd for _, usd in out["profile"]["long"]) == 1_000_000
    assert out["clusters"]["below"][0]["distance_pct"] < -8 and out["clusters"]["above"][0]["distance_pct"] > 8

    crash = bars + [Bar(10800, 100, 89, 95, 2_000_000)]  # the low trades through the long levels
    after = estimate(crash, leverage=((10, 1.0),), maintenance=0.0, bins=400)
    assert after["profile"]["long"] == [] and sum(usd for _, usd in after["profile"]["short"]) == 1_000_000


def test_falling_open_interest_trims_levels_in_proportion_and_skew_reads_the_sides() -> None:
    bars = [Bar(0, 101, 99, 100, 1_000_000), Bar(3600, 101, 99, 100, 2_000_000), Bar(7200, 101, 99, 100, 1_500_000)]
    out = estimate(bars, leverage=((10, 1.0),), maintenance=0.0, bins=400)
    assert sum(usd for _, usd in out["profile"]["long"]) == 750_000  # a quarter of open interest closed
    assert skew(out["profile"], within_pct=12) == 0.0 and skew(out["profile"], within_pct=3) is None
    assert estimate(bars[:1])["cells"] == []
