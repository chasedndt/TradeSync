import math
import pytest
from tradesync_core.intraday_horizons import measure


def candles():
    return [dict(time=1700002800+i*3600, open=100+math.sin(i/8), high=102, low=98, close=100+math.sin(i/8)) for i in range(400)]


def test_horizons_and_closed_only():
    bars = candles()
    now = bars[-1]['time']+3600
    result = measure(bars, now)
    assert [h['hours'] for h in result['horizons']] == [1,4,8,24]
    assert result['closed_candles'] == 400
    assert all(h['execution_authority'] is False for h in result['horizons'])
    assert result['horizons'][-1]['baseline']['non_overlapping_windows'] <= 16


def test_future_mutation_cannot_change_current_measurement():
    bars = candles()
    now = bars[299]['time']+3600
    expected = measure(bars[:300], now)
    for b in bars[300:]:
        b.update(open=999, close=999, high=9999, low=1)
    assert measure(bars, now) == expected


def test_flat_market_is_neutral_not_bearish():
    bars = candles()
    for bar in bars:
        bar.update(open=100, high=100, low=100, close=100)
    result = measure(bars, bars[-1]['time']+3600)
    assert all(h['state'] == 'aligned / flat / flat' for h in result['horizons'])


@pytest.mark.parametrize('kind', ['gap','duplicate','stale','invalid'])
def test_invalid_history_fails_closed(kind):
    bars = candles()
    now = bars[-1]['time']+3600
    if kind == 'gap': del bars[200]
    if kind == 'duplicate': bars.append(dict(bars[200]))
    if kind == 'stale': now += 7200
    if kind == 'invalid': bars[100]['close'] = float('nan')
    with pytest.raises(ValueError): measure(bars, now)
