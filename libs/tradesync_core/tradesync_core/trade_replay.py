"""Frozen, unoptimised scalp/swing research candidates. No live order authority.

Closed-bar breakout with a trend filter, next-open entry, adverse fills,
stop-first ambiguous bars, one concurrent position, and an untouched final
30% temporal test segment. Funding is a disclosed adverse scenario, not history.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Profile:
    interval: str
    seconds: int
    trend_bars: int
    breakout_bars: int
    hold_bars: int
    min_target_pct: float
    atr_stop: float = 1.5
    reward_risk: float = 2.0


PROFILES = {
    'scalp': Profile('15m', 900, 50, 20, 12, 0.4),
    'swing': Profile('4h', 14400, 50, 20, 42, 2.0),
}
VERSION = 'breakout-trend-research-v1'


def replay(candles: list[dict], style: str, *, fee_bps: float = 4.5,
           slippage_bps: float = 2.0, funding_bps_hour: float = 0.125,
           now_s: float, notional: float = 1000.0) -> dict:
    profile = PROFILES[style]
    for value in (fee_bps, slippage_bps, funding_bps_hour, notional):
        if not math.isfinite(value) or value < 0:
            raise ValueError('costs and notional must be finite and non-negative')
    if notional <= 0:
        raise ValueError('notional must be positive')
    bars = sorted((c for c in candles if c['time'] + profile.seconds <= now_s), key=lambda c: c['time'])
    for c in bars:
        if any(not isinstance(c[k], (int, float)) or not math.isfinite(c[k]) or c[k] <= 0 for k in ('open', 'high', 'low', 'close')):
            raise ValueError('invalid OHLC')
        if c['low'] > min(c['open'], c['close']) or c['high'] < max(c['open'], c['close']) or c['low'] > c['high']:
            raise ValueError('inconsistent OHLC')
    if len(bars) < 200:
        raise ValueError('at least 200 closed candles are required')
    if any(b['time'] - a['time'] != profile.seconds for a, b in zip(bars, bars[1:])):
        raise ValueError('candle gaps or duplicates: replay refused')
    split = int(len(bars) * .7)
    results, skipped = [], {'cost_gate': 0, 'gap_entry': 0, 'boundary': 0}
    i = profile.trend_bars
    while i < len(bars) - 1:
        prior = bars[i-profile.breakout_bars:i]
        average = sum(c['close'] for c in bars[i-profile.trend_bars+1:i+1]) / profile.trend_bars
        c = bars[i]
        side = 1 if c['close'] > max(p['high'] for p in prior) and c['close'] > average else -1 if c['close'] < min(p['low'] for p in prior) and c['close'] < average else 0
        if not side:
            i += 1
            continue
        entry_index = i + 1
        segment = 'development' if entry_index < split else 'holdout'
        end = entry_index + profile.hold_bars - 1
        boundary = split if segment == 'development' else len(bars)
        if end >= boundary:
            skipped['boundary'] += 1
            i += 1
            continue
        atr = sum(max(bars[j]['high'] - bars[j]['low'], abs(bars[j]['high'] - bars[j-1]['close']), abs(bars[j]['low'] - bars[j-1]['close'])) for j in range(i-13, i+1)) / 14
        distance = max(atr * profile.atr_stop, c['close'] * profile.min_target_pct / 100 / profile.reward_risk)
        stop = c['close'] - side * distance
        target = c['close'] + side * distance * profile.reward_risk
        entry = bars[entry_index]['open'] * (1 + side * slippage_bps / 10000)
        risk, reward = side * (entry - stop), side * (target - entry)
        cost = entry * (2 * (fee_bps + slippage_bps) + funding_bps_hour * profile.hold_bars * profile.seconds / 3600) / 10000
        if stop <= 0 or target <= 0 or risk <= 0 or reward <= 0:
            skipped['gap_entry'] += 1
            i += 1
            continue
        if reward < 3 * cost or (reward - cost) / (risk + cost) < 1.25:
            skipped['cost_gate'] += 1
            i += 1
            continue
        reason, raw_exit, exit_index = 'time_exit', bars[end]['close'], end
        for j in range(entry_index, end + 1):
            bar = bars[j]
            hit_stop = bar['low'] <= stop if side == 1 else bar['high'] >= stop
            hit_target = bar['high'] >= target if side == 1 else bar['low'] <= target
            if hit_stop:
                raw_exit = min(stop, bar['open']) if side == 1 else max(stop, bar['open'])
                reason, exit_index = 'ambiguous_stop_first' if hit_target else 'stop', j
                break
            if hit_target:
                raw_exit, reason, exit_index = target, 'target', j
                break
        exit_price = raw_exit * (1 - side * slippage_bps / 10000)
        quantity = notional / entry
        gross = side * (exit_price - entry) * quantity
        fees = (entry + exit_price) * quantity * fee_bps / 10000
        hours = (exit_index - entry_index + 1) * profile.seconds / 3600
        funding = notional * funding_bps_hour / 10000 * hours
        results.append({'segment': segment, 'direction': 'long' if side == 1 else 'short',
                        'entry_time': bars[entry_index]['time'], 'exit_time': bars[exit_index]['time'] + profile.seconds,
                        'entry': entry, 'stop': stop, 'target': target, 'exit': exit_price,
                        'holding_hours_upper_bound': hours, 'exit_reason': reason,
                        'net_usdc': gross - fees - funding, 'fees_usdc': fees, 'funding_scenario_usdc': funding,
                        'price_move_pct': side * (exit_price / entry - 1) * 100})
        i = exit_index + 1
    def summary(segment):
        selected = [r for r in results if r['segment'] == segment]
        pnl = [r['net_usdc'] for r in selected]
        wins, losses = sum(p for p in pnl if p > 0), -sum(p for p in pnl if p < 0)
        return {'trades': len(pnl), 'net_usdc': sum(pnl) if pnl else None,
                'expectancy_usdc': sum(pnl)/len(pnl) if pnl else None,
                'win_rate': sum(p > 0 for p in pnl)/len(pnl) if pnl else None,
                'profit_factor': wins/losses if losses else None,
                'moves_at_least_3pct': sum(r['price_move_pct'] >= 3 for r in selected)}
    return {'version': VERSION, 'style': style, 'profile': asdict(profile),
            'candles': len(bars), 'from': bars[0]['time'], 'to': bars[-1]['time'], 'split_time': bars[split]['time'],
            'input_sha256': hashlib.sha256(json.dumps(bars, sort_keys=True).encode()).hexdigest(),
            'assumptions': {'fee_bps_each_fill': fee_bps, 'slippage_bps_each_fill': slippage_bps,
                            'adverse_funding_bps_hour': funding_bps_hour, 'notional_usdc': notional},
            'development': summary('development'), 'holdout': summary('holdout'),
            'skipped': skipped, 'trades': results, 'execution_authority': False,
            'promotion': 'unproven',
            'note': 'Unoptimised research, not a forecast. Final 30% is a temporal diagnostic, not independent proof after repeated inspection. Funding is an adverse assumption, not actual historical funding. OHLC cannot establish fill liquidity. No external evidence was used: historical as-of evidence is not available to this candidate.'}
