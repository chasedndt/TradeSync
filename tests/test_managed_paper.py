import copy
import pytest
from tradesync_core.managed_paper import advance, open_position, atr


def book(at=1000, bid=99.9, ask=100.1):
    return {'poll_ts': at*1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': 100}], 'asks': [{'price': ask, 'size': 100}]}


def position(side='long', style='scalp'):
    return open_position(side, style, 1000, 1, book(bid=99.99, ask=100.01), 1000)


def test_profiles_and_costs_are_frozen_and_no_execution_authority():
    for style in ('scalp','intraday','swing'):
        result = position(style=style)
        assert result['target'] > result['entry_price'] > result['stop']
        assert result['entry_fee_usdc'] == .45
        assert result['execution_authority'] is False
        assert result['net_estimate_usdc'] is None


def test_target_closes_long_and_does_not_double_subtract_slippage():
    initial = position()
    before = copy.deepcopy(initial)
    result = advance(initial, book(at=1010, bid=104, ask=104.01), 1010)
    assert initial == before
    assert result['exit_reason'] == 'target'
    assert result['net_estimate_usdc'] == pytest.approx(result['gross_pnl_usdc']-result['fees_usdc']-result['funding_scenario_usdc'])
    assert advance(result, {}, 1100) == result


def test_gap_stop_fills_at_observed_worse_price_and_flags_coverage():
    result = advance(position(), book(at=1100, bid=95, ask=95.01), 1100)
    assert result['exit_reason'] == 'stop'
    assert result['exit_price'] < result['stop']
    assert result['observation_gap'] is True


def test_short_uses_ask_to_close_and_can_stop():
    result = advance(position('short'), book(at=1010, bid=103, ask=103.01), 1010)
    assert result['exit_reason'] == 'stop'
    assert result['exit_price'] > 103.01
    assert result['net_estimate_usdc'] < 0


def test_manual_close_and_expiry_are_distinct():
    initial = position()
    assert advance(initial, book(at=1010, bid=100, ask=100.01), 1010, manual_close=True)['exit_reason'] == 'operator_close'
    at = initial['expiry']
    assert advance(initial, book(at=at, bid=100, ask=100.01), at)['exit_reason'] == 'time_exit'


def test_stale_duplicate_and_insufficient_depth_never_invent_fill():
    initial = position()
    for current, now in [(book(), 1100), (book(), 1000), (dict(book(at=1010), bids=[]), 1010)]:
        with pytest.raises(ValueError): advance(initial, current, now)


def test_invalid_notional_and_wide_quote_refused():
    for notional in (float('nan'), -1, 1001):
        with pytest.raises(ValueError): open_position('long', 'scalp', notional, 1, book(), 1000)
    with pytest.raises(ValueError): open_position('long', 'scalp', 1000, 1, book(bid=99, ask=101), 1000)


def test_atr_uses_only_closed_contiguous_bars():
    bars = [dict(time=1000+i*900, open=100, high=101, low=99, close=100) for i in range(20)]
    now = bars[-1]['time']+900
    assert atr(bars, 900, now) == 2
    assert atr(bars+[dict(time=now, open=100, high=9999, low=1, close=100)], 900, now) == 2
    with pytest.raises(ValueError): atr(bars[:10]+bars[11:], 900, now)
