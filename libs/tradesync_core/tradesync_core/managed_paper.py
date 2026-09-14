"""Observed-quote paper position lifecycle; no venue/wallet/approval dependency.

Stops/targets are evaluated only at received executable-side book observations.
Missed intervals are never silently reconstructed. Funding below is a frozen
adverse scenario, not actual settled venue funding or a guaranteed upper bound.
"""
import copy
import math

VERSION = 'managed-paper-observed-quotes-v1'
PROFILES = {
    'scalp': {'interval': '15m', 'seconds': 900, 'max_hold_s': 10800, 'stop_atr': 1.5, 'reward_risk': 2., 'min_target_pct': .4},
    'intraday': {'interval': '1h', 'seconds': 3600, 'max_hold_s': 86400, 'stop_atr': 1.5, 'reward_risk': 2., 'min_target_pct': .8},
    'swing': {'interval': '4h', 'seconds': 14400, 'max_hold_s': 604800, 'stop_atr': 2., 'reward_risk': 2., 'min_target_pct': 2.},
}


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


def open_position(side, style, notional, volatility, book, now_s):
    if side not in ('long', 'short') or style not in PROFILES:
        raise ValueError('Unsupported side or style')
    finite(notional, True); finite(volatility, True)
    if notional > 1000:
        raise ValueError('Initial managed-paper cap is 1000 USDC per position')
    at, bid, ask = quote(book, now_s)
    sign = 1 if side == 'long' else -1
    profile = dict(PROFILES[style])
    fee_bps, slippage_bps, funding_bps_hour = 4.5, 2., .125
    entry = (ask if sign == 1 else bid)*(1+sign*slippage_bps/10000)
    quantity = notional/entry
    if quantity > available_size(book, side):
        raise ValueError('Paper size exceeds displayed touch liquidity')
    distance = max(volatility*profile['stop_atr'], entry*profile['min_target_pct']/100/profile['reward_risk'])
    stop, target = entry-sign*distance, entry+sign*distance*profile['reward_risk']
    if min(stop, target) <= 0 or distance/entry > .1:
        raise ValueError('Invalid stop distance')
    budget = entry*(2*(fee_bps+slippage_bps)+funding_bps_hour*profile['max_hold_s']/3600)/10000 + (ask-bid)
    reward = distance*profile['reward_risk']
    if reward < 3*budget or (reward-budget)/(distance+budget) < 1.25:
        raise ValueError('Insufficient reward after declared cost scenario')
    if (distance+budget)*quantity > 50:
        raise ValueError('Initial planned paper-risk cap is 50 USDC; gaps can exceed it')
    return {'version': VERSION, 'side': side, 'style': style, 'status': 'open',
            'entry_time': now_s, 'entry_quote_time': at, 'last_quote_time': at,
            'entry_price': entry, 'quantity': quantity, 'notional': notional,
            'stop': stop, 'target': target, 'expiry': now_s+profile['max_hold_s'],
            'profile': profile, 'fee_bps': fee_bps, 'slippage_bps': slippage_bps,
            'funding_bps_hour': funding_bps_hour, 'planned_risk_usdc': (distance+budget)*quantity,
            'entry_fee_usdc': notional*fee_bps/10000, 'net_estimate_usdc': None,
            'observation_gap': False, 'max_observation_gap_s': 0, 'observations': 0,
            'execution_authority': False, 'funding_model': 'adverse_constant_scenario_not_settled_funding'}


def advance(position, book, now_s, *, manual_close=False):
    if position['status'] != 'open':
        return copy.deepcopy(position)
    at, bid, ask = quote(book, now_s)
    if at <= position['last_quote_time']:
        raise ValueError('Duplicate or out-of-order observation')
    result = copy.deepcopy(position)
    sign = 1 if position['side'] == 'long' else -1
    exit_side = 'short' if sign == 1 else 'long'
    if position['quantity'] > available_size(book, exit_side):
        raise ValueError('Exit exceeds observed touch size; fill not assumed')
    touch = bid if sign == 1 else ask
    exit_price = touch*(1-sign*position['slippage_bps']/10000)
    gap = at-position['last_quote_time']
    result.update(last_quote_time=at, observations=position['observations']+1,
                  observation_gap=position['observation_gap'] or gap > 45,
                  max_observation_gap_s=max(position['max_observation_gap_s'], gap))
    gross = sign*(exit_price-position['entry_price'])*position['quantity']
    fees = position['entry_fee_usdc']+exit_price*position['quantity']*position['fee_bps']/10000
    funding = position['notional']*position['funding_bps_hour']/10000*max(0, now_s-position['entry_time'])/3600
    result.update(mark_exit_price=exit_price, gross_pnl_usdc=gross, fees_usdc=fees,
                  funding_scenario_usdc=funding, net_estimate_usdc=gross-fees-funding)
    stop = sign*(touch-position['stop']) <= 0
    target = sign*(touch-position['target']) >= 0
    reason = 'stop' if stop else 'target' if target else 'operator_close' if manual_close else 'time_exit' if now_s >= position['expiry'] else None
    if reason:
        result.update(status='closed', exit_reason=reason, exit_time=now_s, exit_price=exit_price)
    return result
