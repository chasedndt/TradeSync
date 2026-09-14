"""Hourly-source intraday records. No forecast, learned weight or order authority."""
from __future__ import annotations

import math
from statistics import median

HORIZONS = ((1, '1 hour'), (4, '4 hours'), (8, '8 hours'), (24, '1 day'))


def measure(candles: list[dict], now_s: float) -> dict:
    bars = sorted((c for c in candles if c['time'] + 3600 <= now_s), key=lambda c: c['time'])
    if len(bars) < 120:
        raise ValueError('At least 120 closed hourly candles are required')
    for c in bars:
        if any(not isinstance(c.get(k), (int, float)) or not math.isfinite(c[k]) or c[k] <= 0 for k in ('time', 'open', 'high', 'low', 'close')):
            raise ValueError('Invalid hourly candle')
        if c['low'] > min(c['open'], c['close']) or c['high'] < max(c['open'], c['close']):
            raise ValueError('Inconsistent OHLC')
    if any(b['time'] - a['time'] != 3600 for a, b in zip(bars, bars[1:])):
        raise ValueError('Hourly gaps or duplicate timestamps; history refused')
    if now_s - (bars[-1]['time'] + 3600) >= 7200:
        raise ValueError('Hourly candles are stale')
    closes = [c['close'] for c in bars]
    avgs = [None if i < 19 else sum(closes[i-19:i+1])/20 for i in range(len(bars))]
    def state(i, hours):
        if i < max(24, hours):
            return None
        def compare(a, b, positive, negative, neutral):
            return neutral if math.isclose(a, b, rel_tol=1e-12) else positive if a > b else negative
        return (compare(closes[i], avgs[i], 'above', 'below', 'aligned'),
                compare(avgs[i], avgs[i-5], 'rising', 'falling', 'flat'),
                compare(closes[i], closes[i-hours], 'up', 'down', 'flat'))
    def record(indices, hours):
        # Thin chronologically: adjacent retained return windows share an endpoint,
        # but no hourly return increment. This does NOT establish independence.
        retained, end = [], -1
        for i in indices:
            if i >= end:
                retained.append((closes[i+hours]/closes[i]-1)*100)
                end = i + hours
        return {'matching_windows': len(indices), 'non_overlapping_windows': len(retained),
                'share_up': sum(x > 0 for x in retained)/len(retained) if retained else None,
                'median_move_pct': median(retained) if retained else None}
    result = []
    for hours, label in HORIZONS:
        current = state(len(bars)-1, hours)
        usable = range(max(24, hours), len(bars)-hours)
        matches = [i for i in usable if state(i, hours) == current]
        result.append({'hours': hours, 'label': label, 'state': ' / '.join(current),
                       'momentum_pct': (closes[-1]/closes[-1-hours]-1)*100,
                       'same_state': record(matches, hours), 'baseline': record(usable, hours),
                       'status': 'descriptive_only', 'execution_authority': False})
    return {'schema_version': 'intraday_horizons_v1', 'source_interval': '1h',
            'closed_candles': len(bars), 'from': bars[0]['time'],
            'last_closed_at': bars[-1]['time']+3600, 'last_close': closes[-1],
            'ma20': avgs[-1], 'horizons': result,
            'note': 'Hourly candles, closed bars only. State = close versus 20-hour mean / mean slope over five hours / momentum over the selected horizon. Records use non-overlapping return windows, not independent trials. No fees, funding or execution model: these are price observations, not profitable trades or calibrated forecasts.'}
