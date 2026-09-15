import math

import pytest

from tradesync_core.paper_correlation import BAR_SECONDS, bucket_view, buckets, closed_returns, measure, pearson

START = 1_700_000_000 // BAR_SECONDS * BAR_SECONDS


def series(returns, start=START):
    level, bars = 100.0, [{'time': start, 'close': 100.0}]
    for i, r in enumerate(returns, start=1):
        level *= math.exp(r)
        bars.append({'time': start + i * BAR_SECONDS, 'close': level})
    return bars


def test_only_closed_contiguous_bars_become_returns():
    bars = series([0.01, -0.02, 0.03])
    now = bars[-1]['time'] + BAR_SECONDS  # the last bar has just closed
    assert len(closed_returns(bars, now)) == 3
    assert len(closed_returns(bars, now - 1)) == 2  # last bar still open
    assert len(closed_returns([b for i, b in enumerate(bars) if i != 2], now)) == 1  # a missing bar breaks two returns
    assert len(closed_returns(bars + [{'time': 'x', 'close': 1}, {'time': 0, 'close': -1}], now)) == 3


def test_pearson_edges():
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1)
    assert pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1)
    assert pearson([1, 1, 1], [1, 2, 3]) is None
    assert pearson([1], [1]) is None


def test_measured_buckets_link_absolute_correlation_and_leave_short_history_unmeasured():
    n = 170
    base = [0.01 * math.sin(t * 1.3) + 0.004 * math.sin(t * 0.37) for t in range(n)]
    candles = {
        'BTC-PERP': series(base),
        'ETH-PERP': series([r + 0.002 * math.sin(t * 5.1) for t, r in enumerate(base)]),
        'HYPE-PERP': series([0.01 * math.cos(t * 0.71 + 1) for t in range(n)]),
        'ZEC-PERP': series([-r for r in base]),
        'PUMP-PERP': series(base[:50]),
    }
    now = START + (n + 1) * BAR_SECONDS
    result = measure(candles, now)
    matrix = result['matrix']
    assert matrix['BTC-PERP']['ETH-PERP'] > 0.9
    assert matrix['BTC-PERP']['ZEC-PERP'] < -0.99
    assert abs(matrix['BTC-PERP']['HYPE-PERP']) < 0.5
    assert matrix['BTC-PERP']['PUMP-PERP'] is None
    assert result['unmeasured'] == ['PUMP-PERP']
    assert result['overlaps']['BTC-PERP']['ETH-PERP'] == 168
    groups = buckets(result['symbols'], matrix, 0.7, result['unmeasured'])
    assert groups == [['BTC-PERP', 'ETH-PERP', 'ZEC-PERP'], ['HYPE-PERP']]
    # An exact mirror still reaches a threshold of 1.0: absolute correlation, not signed.
    assert buckets(result['symbols'], matrix, 1.0, result['unmeasured']) == [['BTC-PERP', 'ZEC-PERP'], ['ETH-PERP'], ['HYPE-PERP']]

    view = bucket_view(result, now, 0.7)
    assert view.members('ETH-PERP') == ('BTC-PERP', 'ETH-PERP', 'ZEC-PERP')
    assert view.members('PUMP-PERP') is None
    assert view.unmeasured == frozenset({'PUMP-PERP'})
    assert 'HYPE-PERP' in view.grouped()
