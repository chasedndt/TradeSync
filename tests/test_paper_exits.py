"""Exit rules per observation: stops, trailing stops, targets, expiry and gap fills, on quotes and candles."""

import pytest

from tradesync_core import paper_depth as depth
from tradesync_core import paper_funding as funding
from tradesync_core.managed_paper import advance, advance_on_candle, open_position, open_position_on_candle, settle_funding

# Buying from 100.1 or selling into 99.9 costs 10 bps against the 100 mid.
COST_BOOK = {'bids': [[99.9, 1000.0]], 'asks': [[100.1, 1000.0]]}
COST_SOURCE = depth.snapshot(COST_BOOK, observed_at=900, received_at=901, source='market_depth_snapshots', precision='aggregated_3_sig_figs')


def book(at, bid, ask, size=100.0):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': size}], 'asks': [{'price': ask, 'size': size}]}


def bar(time, open, high, low, close):
    return {'time': time, 'open': open, 'high': high, 'low': low, 'close': close}


def long_scalp(at=1000):
    # ATR 1: entry 100.01, stop 98.51, target 103.01; the trail starts at 101.51 and follows 1.0 behind.
    return open_position('long', 'scalp', 1000, 1, book(at, 99.99, 100.01), at)


def test_the_plan_declares_stop_target_trail_and_expiry():
    p = long_scalp()
    assert (p['stop'], p['target'], p['expiry']) == (pytest.approx(98.51), pytest.approx(103.01), 1000 + 3 * 3600)
    assert p['trail'] == {'activate_price': pytest.approx(101.51), 'distance': 1.0, 'best': None, 'active': False, 'stop': None}


def test_stop_fires_at_the_observed_price_and_records_the_observation():
    closed = advance(long_scalp(), book(1010, 98.0, 98.01), 1010)
    assert closed['exit_reason'] == 'stop' and closed['exit_time'] == 1010
    assert closed['exit']['level'] == pytest.approx(98.51) and closed['exit']['trigger_price'] == 98.0
    assert closed['exit']['gap_fill'] is True and closed['exit_price'] == 98.0
    assert closed['exit']['trigger_observation'] == {'kind': 'quote', 'observed_at': 1010, 'received_at': 1010,
                                                     'best_bid': 98.0, 'best_ask': 98.01, 'touch': 98.0}
    assert closed['slippage']['exit']['snapshot']['observed_at'] == 1010


def test_target_fires_on_the_exit_side_touch_only():
    assert advance(long_scalp(), book(1010, 103.0, 103.02), 1010)['status'] == 'open'
    hit = advance(long_scalp(), book(1010, 103.01, 103.02), 1010)
    assert hit['exit_reason'] == 'target' and hit['exit']['gap_fill'] is False


def test_trailing_stop_activates_ratchets_and_fires_on_the_retreat():
    p = long_scalp()
    p = advance(p, book(1010, 101.0, 101.01), 1010)
    assert p['trail']['active'] is False and p['current_stop_rule'] == 'stop'
    p = advance(p, book(1020, 101.6, 101.61), 1020)
    assert p['trail']['active'] is True and p['current_stop'] == pytest.approx(100.6) and p['current_stop_rule'] == 'trailing_stop'
    p = advance(p, book(1030, 102.5, 102.51), 1030)
    assert p['current_stop'] == pytest.approx(101.5)
    p = advance(p, book(1040, 101.9, 101.91), 1040)
    assert p['status'] == 'open' and p['current_stop'] == pytest.approx(101.5) and p['trail']['best'] == 102.5
    closed = advance(p, book(1050, 101.4, 101.41), 1050)
    assert closed['exit_reason'] == 'trailing_stop' and closed['exit']['level'] == pytest.approx(101.5)
    assert closed['exit']['gap_fill'] is True and closed['exit_price'] == 101.4
    assert closed['net_estimate_usdc'] > 0


def test_expiry_operator_close_and_rule_order():
    p = long_scalp()
    assert advance(p, book(p['expiry'], 100.0, 100.01), p['expiry'])['exit_reason'] == 'time_expiry'
    assert advance(p, book(1010, 100.0, 100.01), 1010, manual_close=True)['exit_reason'] == 'operator_close'
    assert advance(p, book(1010, 98.0, 98.01), 1010, manual_close=True)['exit_reason'] == 'stop'


def test_short_rules_mirror_the_long_rules():
    short = open_position('short', 'scalp', 1000, 1, book(1000, 99.99, 100.01), 1000)
    assert short['stop'] == pytest.approx(101.49) and short['target'] == pytest.approx(96.99)
    closed = advance(short, book(1010, 101.5, 101.51), 1010)
    assert closed['exit_reason'] == 'stop' and closed['exit']['gap_fill'] is True and closed['exit_price'] == 101.51
    trailed = advance(advance(short, book(1010, 98.4, 98.41), 1010), book(1020, 99.5, 99.52), 1020)
    assert trailed['exit_reason'] == 'trailing_stop' and trailed['exit']['level'] == pytest.approx(99.41)


def test_an_exit_the_book_cannot_fill_stays_owed_and_records_both_observations():
    owed = advance(long_scalp(), book(1010, 98.0, 98.01, size=5), 1010)
    assert owed['status'] == 'open' and owed['pending_exit']['rule'] == 'stop' and 'fills' in owed['pending_exit']['unfilled']
    closed = advance(owed, book(1020, 99.0, 99.01), 1020)
    assert closed['exit_reason'] == 'stop' and closed['exit_price'] == 99.0 and closed['exit_time'] == 1020
    assert closed['exit']['trigger_observation']['observed_at'] == 1010 and closed['exit']['fill_observation']['observed_at'] == 1020


def test_candle_gap_through_the_stop_fills_at_the_open_not_the_stop():
    closed = advance_on_candle(long_scalp(), bar(1020, 97.0, 97.5, 96.5, 97.2), 60, COST_BOOK, 1080, cost_source=COST_SOURCE)
    assert closed['exit_reason'] == 'stop' and closed['exit']['path'] == 'open' and closed['exit']['gap_fill'] is True
    assert closed['exit']['trigger_price'] == 97.0 and closed['exit_price'] == pytest.approx(97.0 * 0.999)
    assert closed['exit_time'] == 1020 and closed['slippage']['exit']['snapshot']['precision'] == 'aggregated_3_sig_figs'
    assert closed['exit']['trigger_observation']['kind'] == 'candle'


def test_candle_reaching_stop_and_target_counts_as_the_stop():
    closed = advance_on_candle(long_scalp(), bar(1020, 100.5, 104.0, 98.0, 101.0), 60, COST_BOOK, 1080, cost_source=COST_SOURCE)
    assert closed['exit_reason'] == 'stop' and closed['exit']['ambiguous_candle'] is True
    assert closed['exit']['trigger_price'] == pytest.approx(98.51) and closed['exit_price'] == pytest.approx(98.51 * 0.999)


def test_a_candles_own_high_cannot_tighten_the_stop_its_low_then_hits():
    p = advance_on_candle(long_scalp(), bar(1020, 101.0, 102.6, 100.8, 102.0), 60, COST_BOOK, 1080)
    assert p['status'] == 'open' and p['current_stop'] == pytest.approx(101.6) and p['current_stop_rule'] == 'trailing_stop'
    closed = advance_on_candle(p, bar(1080, 102.0, 102.2, 101.5, 101.8), 60, COST_BOOK, 1140)
    assert closed['exit_reason'] == 'trailing_stop' and closed['exit']['path'] == 'inside'
    assert closed['exit_price'] == pytest.approx(101.6 * 0.999)


def test_candle_expiry_inside_a_quiet_candle_exits_at_its_close():
    p = long_scalp()
    closed = advance_on_candle(p, bar(p['expiry'] - 40, 100.2, 100.4, 100.0, 100.3), 60, COST_BOOK, p['expiry'] + 20)
    assert closed['exit_reason'] == 'time_expiry' and closed['exit']['path'] == 'close'
    assert closed['exit_time'] == p['expiry'] + 20 and closed['exit']['trigger_price'] == 100.3


def test_candles_still_open_overlapping_or_inconsistent_are_refused():
    p = long_scalp()
    with pytest.raises(ValueError, match='not closed'):
        advance_on_candle(p, bar(1020, 100.2, 100.4, 100.0, 100.3), 60, COST_BOOK, 1050)
    observed = advance(p, book(1030, 100.0, 100.01), 1030)
    with pytest.raises(ValueError, match='overlaps'):
        advance_on_candle(observed, bar(1020, 100.2, 100.4, 100.0, 100.3), 60, COST_BOOK, 1080)
    with pytest.raises(ValueError, match='Inconsistent'):
        advance_on_candle(p, bar(1020, 100.2, 100.4, 100.3, 100.1), 60, COST_BOOK, 1080)


def test_candle_entry_prices_the_open_with_the_recorded_books_cost():
    p = open_position_on_candle('long', 'scalp', 1000, 1, bar(2000, 100.0, 100.2, 99.9, 100.1), COST_BOOK, cost_source=COST_SOURCE)
    assert p['entry_time'] == 2000 and p['evaluated_through'] == 2000
    assert p['entry_price'] == pytest.approx(100.1) and p['quantity'] == pytest.approx(1000 / 100.1)
    assert p['slippage']['entry']['basis'] == 'reference_moved_by_book_cost' and p['slippage']['entry']['cost_bps'] == pytest.approx(10.0)
    assert advance_on_candle(p, bar(2000, 100.0, 100.2, 99.9, 100.1), 60, COST_BOOK, 2060)['candles'] == 1


def test_net_subtracts_settled_funding_and_late_rows_settle_a_closed_position():
    p = long_scalp(at=3500)
    row = funding.settle('long', p['quantity'], 3600, {'funding_rate': 1e-4, 'premium': 0.0},
                         {'value': 100.0, 'source': 'market_open_interest.oracle_price', 'observed_at': 3590})
    marked = advance(p, book(3610, 100.5, 100.51), 3610, funding_rows=[row])
    assert marked['funding']['status'] == 'complete' and marked['funding_usdc'] == pytest.approx(p['quantity'] * 100 * 1e-4)
    assert marked['net_estimate_usdc'] == pytest.approx(marked['gross_pnl_usdc'] - marked['fees_usdc'] - marked['funding_usdc'])
    closed = advance(p, book(3610, 100.5, 100.51), 3610, manual_close=True)
    assert closed['funding']['missing_hours'] == [3600] and closed['funding_usdc'] == 0
    settled = settle_funding(closed, [row])
    assert settled['funding']['status'] == 'complete'
    assert settled['net_estimate_usdc'] == pytest.approx(closed['net_estimate_usdc'] - row['payment_usdc'])
