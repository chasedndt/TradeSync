"""Order book shape: the arithmetic behind the canvas depth panel."""

from __future__ import annotations

from app.depth import WALL_MIN_SHARE, cumulative_ladder, resting_walls, summarise_book


def level(price: float, size: float, orders: int = 1) -> dict:
    return {"price": price, "size": size, "orders": orders}


def test_cumulative_notional_answers_the_cost_to_sweep_to_a_level() -> None:
    ladder = cumulative_ladder([level(100.0, 2.0), level(99.0, 1.0), level(98.0, 3.0)])
    assert [entry["notional_usd"] for entry in ladder] == [200.0, 99.0, 294.0]
    assert [entry["cumulative_usd"] for entry in ladder] == [200.0, 299.0, 593.0]


def test_a_malformed_level_is_skipped_rather_than_priced_at_zero() -> None:
    ladder = cumulative_ladder(
        [level(100.0, 2.0), {"price": "x", "size": 1.0}, {"size": 5.0}, level(98.0, 1.0)]
    )
    assert [entry["price"] for entry in ladder] == [100.0, 98.0]
    # The bad rows contribute nothing to the running total.
    assert ladder[-1]["cumulative_usd"] == 298.0


def test_an_evenly_spread_book_has_no_walls() -> None:
    """The honest answer for ordinary lumpiness is an empty list.

    Reporting "the biggest level" regardless would dress noise as a finding.
    """
    bids = [level(100.0 - index, 1.0) for index in range(10)]
    asks = [level(101.0 + index, 1.0) for index in range(10)]
    assert resting_walls(bids, asks) == []


def test_an_outsized_level_is_reported_with_its_share() -> None:
    bids = [level(100.0, 1.0), level(99.0, 1.0), level(98.0, 20.0)]
    walls = resting_walls(bids, [])
    assert len(walls) == 1
    assert walls[0]["side"] == "bid"
    assert walls[0]["price"] == 98.0
    assert walls[0]["share_of_side"] > WALL_MIN_SHARE


def test_share_is_measured_against_the_level_s_own_side() -> None:
    """A thin ask book must not promote an ordinary bid into a wall.

    Both sides here are internally even, so neither has a wall — even though
    every bid dwarfs every ask in absolute notional.
    """
    bids = [level(100.0, 10.0) for _ in range(10)]
    asks = [level(101.0, 0.01) for _ in range(10)]
    assert resting_walls(bids, asks) == []


def test_walls_are_capped_per_side_and_ordered_by_size() -> None:
    bids = [level(100.0, 5.0), level(99.0, 4.0), level(98.0, 3.0), level(97.0, 0.1)]
    walls = resting_walls(bids, [], limit=2)
    assert [wall["price"] for wall in walls] == [100.0, 99.0]


def test_a_missing_book_summarises_to_none_not_an_empty_market() -> None:
    """The UI must be able to say the venue did not answer."""
    assert summarise_book(None) is None
    assert summarise_book({}) is None


def test_the_summary_restates_that_it_carries_no_authority() -> None:
    book = {
        "venue": "hyperliquid",
        "symbol": "BTC-PERP",
        "poll_ts": 1,
        "best_bid": 100.0,
        "best_ask": 101.0,
        "mid_price": 100.5,
        "spread_bps": 99.5,
        "imbalance_1pct": 0.0,
        "depth": {"bid_1pct_usd": 1.0, "ask_1pct_usd": 1.0},
        "bids": [level(100.0, 1.0)],
        "asks": [level(101.0, 1.0)],
    }
    summary = summarise_book(book)
    assert summary is not None
    assert summary["authority"] == "display_only"
    assert summary["bids"][0]["cumulative_usd"] == 100.0
    assert summary["asks"][0]["cumulative_usd"] == 101.0
