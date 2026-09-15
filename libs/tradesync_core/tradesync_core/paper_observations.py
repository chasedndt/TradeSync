"""Book and candle validation for managed paper positions, moved unchanged from ``managed_paper``."""
import math


def finite(value, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError('Invalid numeric input')
    return value


def quote(book, now_s):
    timestamp = finite(book.get('poll_ts'), True)/1000
    if not -2 <= now_s-timestamp <= 30:
        raise ValueError('Quote stale or future-dated')
    bid, ask = finite(book.get('best_bid'), True), finite(book.get('best_ask'), True)
    if ask < bid or (ask-bid)/((ask+bid)/2)*10000 > 20:
        raise ValueError('Crossed or excessively wide book')
    return timestamp, bid, ask


def atr(candles, seconds, now_s):
    bars = sorted([c for c in candles if finite(c.get('time'), True)+seconds <= now_s], key=lambda c: c['time'])
    if len(bars) < 15:
        raise ValueError('At least 15 closed candles needed for ATR')
    bars = bars[-15:]
    if now_s-(bars[-1]['time']+seconds) > seconds*2:
        raise ValueError('ATR source stale')
    for bar in bars:
        for key in ('open', 'high', 'low', 'close'):
            finite(bar.get(key), True)
        if bar['low'] > min(bar['open'], bar['close']) or bar['high'] < max(bar['open'], bar['close']):
            raise ValueError('Inconsistent candle range')
    if any(b['time']-a['time'] != seconds for a,b in zip(bars,bars[1:])):
        raise ValueError('ATR source has gaps or duplicates')
    return sum(max(b['high']-b['low'], abs(b['high']-a['close']), abs(b['low']-a['close'])) for a,b in zip(bars,bars[1:]))/14


def available_size(book, side):
    rows = book.get('asks' if side == 'long' else 'bids')
    if not rows:
        raise ValueError('Displayed touch size unavailable')
    expected = book['best_ask' if side == 'long' else 'best_bid']
    if finite(rows[0].get('price'), True) != expected:
        raise ValueError('Touch and ladder disagree')
    return finite(rows[0].get('size'), True)
