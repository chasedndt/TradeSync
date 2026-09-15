"""Opening a managed paper position, moved unchanged from ``managed_paper``."""
from .paper_observations import available_size, finite, quote

VERSION = 'managed-paper-observed-quotes-v1'
PROFILES = {
    'scalp': {'interval': '15m', 'seconds': 900, 'max_hold_s': 10800, 'stop_atr': 1.5, 'reward_risk': 2., 'min_target_pct': .4},
    'intraday': {'interval': '1h', 'seconds': 3600, 'max_hold_s': 86400, 'stop_atr': 1.5, 'reward_risk': 2., 'min_target_pct': .8},
    'swing': {'interval': '4h', 'seconds': 14400, 'max_hold_s': 604800, 'stop_atr': 2., 'reward_risk': 2., 'min_target_pct': 2.},
}


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
