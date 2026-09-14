import math
import pytest

from tradesync_core.trade_economics import economics, summarize
from tradesync_core.trade_replay import PROFILES, replay


def bars(style='scalp', n=1000):
    seconds = PROFILES[style].seconds
    rows = []
    for i in range(n):
        value = 100 * math.exp(.005*i + .05*math.sin(i/15))
        opened = rows[-1]['close'] if rows else value
        rows.append(dict(time=1600000000+i*seconds, open=opened, high=max(value, opened)*1.001, low=min(value, opened)*.999, close=value))
    return rows


@pytest.mark.parametrize('style', ['scalp', 'swing'])
def test_replay_is_deterministic_disjoint_and_never_grants_authority(style):
    candles = bars(style)
    end = candles[-1]['time'] + PROFILES[style].seconds
    r = replay(candles, style, now_s=end)
    assert r == replay(candles, style, now_s=end)
    assert r['execution_authority'] is False and r['promotion'] == 'unproven'
    assert r['trades']
    assert all(a['exit_time'] <= b['entry_time'] for a,b in zip(r['trades'], r['trades'][1:]))
    assert all(t['exit_time'] <= r['split_time'] for t in r['trades'] if t['segment']=='development')
    assert all(t['entry_time'] >= r['split_time'] for t in r['trades'] if t['segment']=='holdout')


def test_future_holdout_cannot_rewrite_development_trades():
    candles = bars()
    original = replay(candles, 'scalp', now_s=10**12)
    changed = [dict(c) for c in candles]
    for c in changed[700:]:
        for key in ('open','high','low','close'):
            c[key] *= 2
    after = replay(changed, 'scalp', now_s=10**12)
    assert [t for t in original['trades'] if t['segment']=='development'] == [t for t in after['trades'] if t['segment']=='development']


def test_gaps_are_refused_and_partial_bars_excluded():
    candles = bars()
    with pytest.raises(ValueError, match='gaps'):
        replay(candles[:100]+candles[101:], 'scalp', now_s=10**12)
    r = replay(candles, 'scalp', now_s=candles[-1]['time']+1)
    assert r['candles']==999


def test_increasing_costs_does_not_manufacture_profit():
    candles = bars()
    baseline = replay(candles, 'scalp', now_s=10**12)
    costly = replay(candles, 'scalp', now_s=10**12, fee_bps=100)
    assert costly['skipped']['cost_gate'] >= baseline['skipped']['cost_gate']


def test_diagnostics_do_not_confuse_dollars_with_price_moves_or_double_count_slippage():
    row = dict(direction='long', entry_price=100, invalidation_price=99, target_price=103,
               entry_fill_price=100, exit_fill_price=103, quantity=10, outcome_id='one',
               gross_pnl_usdc=30, net_pnl_usdc=28, holding_minutes=60)
    e = economics(row)
    assert e['target_move_pct'] == pytest.approx(3)
    assert e['net_return_pct'] == pytest.approx(2.8)
    assert e['cost_drag_usdc'] == 2
    total = summarize([row, dict(direction='long')])
    assert total['resolved']==1 and total['trades']==2 and total['expectancy_usdc']==28
    assert total['profit_factor'] is None


def test_empty_and_invalid_levels_are_not_zero_or_reward():
    assert summarize([])['net_usdc'] is None
    assert economics(dict(direction='long', entry_price=100, invalidation_price=101, target_price=103))['valid_levels'] is False
    assert economics(dict(direction='long', entry_price=100, invalidation_price=-1, target_price=103))['valid_levels'] is False
    assert summarize([dict(outcome_id='x', net_pnl_usdc=1)])['cost_drag_usdc'] is None


def test_both_stop_and_target_in_same_bar_uses_stop_first():
    candles = bars()
    first = replay(candles, 'scalp', now_s=10**12)['trades'][0]
    bar = next(c for c in candles if c['time']==first['entry_time'])
    bar['high'] = max(first['stop'], first['target'], bar['high']) * 1.01
    bar['low'] = min(first['stop'], first['target'], bar['low']) * .99
    measured = replay(candles, 'scalp', now_s=10**12)['trades'][0]
    assert measured['exit_reason']=='ambiguous_stop_first'
    assert measured['net_usdc'] < 0
