"""Observed-quote paper position lifecycle; no venue/wallet/approval dependency.

Stops/targets are evaluated only at received executable-side book observations.
Missed intervals are never silently reconstructed. Funding below is a frozen
adverse scenario, not actual settled venue funding or a guaranteed upper bound.
"""
import copy

from .paper_observations import atr, available_size, finite, quote
from .paper_opening import PROFILES, VERSION, open_position

__all__ = ['VERSION', 'PROFILES', 'finite', 'quote', 'atr', 'available_size', 'open_position', 'advance']


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
