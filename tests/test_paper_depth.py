"""Depth-walk slippage: fills for the position's own size from the observed book, with the snapshot recorded."""

import pytest

from tradesync_core import paper_depth as depth

BOOK = {'bids': [{'price': 99.9, 'size': 1.0}, {'price': 99.8, 'size': 2.0}, {'price': 99.5, 'size': 10.0}],
        'asks': [{'price': 100.1, 'size': 1.0}, {'price': 100.2, 'size': 2.0}, {'price': 100.6, 'size': 10.0}]}


def test_buy_walks_asks_by_notional_past_the_touch():
    walked = depth.walk(BOOK, 'buy', notional=300.0, source={'source': 'test'})
    assert walked['levels_taken'][0] == [100.1, 1.0] and walked['levels_taken'][1][0] == 100.2
    assert walked['notional_usdc'] == pytest.approx(300.0)
    assert walked['price'] == pytest.approx(300.0 / walked['quantity']) and 100.1 < walked['price'] < 100.2
    assert walked['mid'] == pytest.approx(100.0) and walked['half_spread_bps'] == pytest.approx(10.0)
    assert walked['depth_bps'] > 0
    assert walked['total_bps'] == pytest.approx((walked['price'] - 100.0) / 100.0 * 1e4)
    assert walked['snapshot'] == {'source': 'test'}


def test_sell_walks_bids_by_quantity():
    walked = depth.walk(BOOK, 'sell', quantity=2.5)
    assert walked['levels_taken'] == [[99.9, 1.0], [99.8, 1.5]]
    assert walked['price'] == pytest.approx((99.9 + 99.8 * 1.5) / 2.5)
    assert walked['depth_bps'] > 0 and walked['half_spread_bps'] == pytest.approx(10.0)
    assert walked['total_usdc'] == pytest.approx((100.0 - walked['price']) * 2.5)


def test_a_size_inside_the_touch_has_no_depth_cost():
    walked = depth.walk(BOOK, 'buy', quantity=0.5)
    assert walked['depth_bps'] == 0 and walked['levels_taken'] == [[100.1, 0.5]]


def test_insufficient_displayed_depth_is_refused_not_extrapolated():
    with pytest.raises(depth.InsufficientDepth, match='fills'):
        depth.walk(BOOK, 'sell', quantity=13.5)
    with pytest.raises(depth.InsufficientDepth):
        depth.walk({'bids': []}, 'sell', quantity=1)


def test_malformed_or_unordered_books_are_refused():
    with pytest.raises(ValueError):
        depth.walk({'asks': [{'price': 100.2, 'size': 1}, {'price': 100.1, 'size': 1}]}, 'buy', quantity=1.5)
    with pytest.raises(ValueError):
        depth.walk({'asks': [{'price': float('nan'), 'size': 1}]}, 'buy', quantity=0.5)
    with pytest.raises(ValueError):
        depth.walk(BOOK, 'buy', quantity=1, notional=1)


def test_aggregated_levels_price_a_reference_and_keep_their_precision():
    aggregated = {'bids': [[99.0, 50.0]], 'asks': [[101.0, 50.0]]}
    source = depth.snapshot(aggregated, observed_at=10, received_at=11, source='market_depth_snapshots', precision='aggregated_3_sig_figs')
    walked = depth.walk(aggregated, 'sell', quantity=1.0, source=source)
    assert walked['total_bps'] == pytest.approx(100.0)
    assert depth.priced(100.0, walked) == pytest.approx(99.0)
    fill = depth.reference_fill(walked, 100.0, 2.0)
    assert fill['fill_price'] == pytest.approx(99.0) and fill['cost_usdc'] == pytest.approx(2.0)
    assert fill['snapshot'] == {'source': 'market_depth_snapshots', 'precision': 'aggregated_3_sig_figs', 'observed_at': 10,
                                'received_at': 11, 'best_bid': 99.0, 'best_ask': 101.0, 'bid_levels': 1, 'ask_levels': 1}
    with pytest.raises(ValueError, match='no mid'):
        depth.priced(100.0, depth.walk({'bids': [[99.0, 5.0]]}, 'sell', quantity=1.0))
