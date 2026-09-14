"""Causal receipt filtering for frozen paper-entry context, not scoring authority."""
import math
import copy


def timestamp(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def liquidation_snapshot(payload, cutoff):
    if not timestamp(cutoff):
        raise ValueError('Finite positive entry cutoff required')
    if not isinstance(payload, dict) or payload.get('receipt_schema') != 'first-received-v2':
        return {'status': 'unavailable', 'reason': 'First-received provenance unavailable', 'events': [], 'cutoff': cutoff, 'authority': 'context_only', 'scoring_influence': False}
    rows = payload.get('events')
    if not isinstance(rows, list):
        return {'status': 'unavailable', 'reason': 'Malformed event collection', 'events': [], 'cutoff': cutoff, 'authority': 'context_only', 'scoring_influence': False}
    events, excluded, seen = [], 0, set()
    for row in rows:
        if not isinstance(row, dict):
            excluded += 1
            continue
        received, occurred, identity = row.get('received_at'), row.get('event_time'), row.get('id')
        if (not timestamp(received) or not timestamp(occurred) or not isinstance(identity, str)
                or not identity or identity in seen or not cutoff-3600 <= occurred <= received <= cutoff):
            excluded += 1
            continue
        seen.add(identity)
        events.append(copy.deepcopy(row))
    return {'status': 'observed' if events else 'no_eligible_receipts',
            'cutoff': cutoff, 'events': events, 'excluded': excluded,
            'connection_at_capture': payload.get('connection'), 'authority': 'context_only',
            'coverage': 'At most one hour / 1000 received Bybit events; gaps and truncation possible. Empty is not zero market liquidations.',
            'scoring_influence': False}


def book_snapshot(payload, cutoff, symbol):
    if not timestamp(cutoff):
        raise ValueError('Finite positive entry cutoff required')
    unavailable = {'status': 'unavailable', 'samples': [], 'cutoff': cutoff,
                   'authority': 'context_only', 'scoring_influence': False}
    if (not isinstance(payload, dict) or payload.get('venue') != 'hyperliquid'
            or payload.get('symbol') != symbol or not isinstance(payload.get('samples'), list)):
        return {**unavailable, 'reason': 'Book-history source, symbol or collection invalid'}
    samples, excluded, seen = [], 0, set()
    for row in payload['samples']:
        if not isinstance(row, dict):
            excluded += 1
            continue
        at, levels = row.get('time'), row.get('levels')
        if (not timestamp(at) or not cutoff-3600 <= at <= cutoff or at in seen
                or not isinstance(levels, list) or not 2 <= len(levels) <= 20):
            excluded += 1
            continue
        if (any(not isinstance(level, dict) or level.get('side') not in ('bids', 'asks')
                or not timestamp(level.get('price')) or not timestamp(level.get('notional_usd')) for level in levels)
                or {level['side'] for level in levels} != {'bids', 'asks'}):
            excluded += 1
            continue
        seen.add(at)
        samples.append(copy.deepcopy(row))
    samples.sort(key=lambda row: row['time'])
    truncated = len(samples) > 240
    samples = samples[-240:]
    age = cutoff-samples[-1]['time'] if samples else None
    return {'status': 'no_eligible_samples' if not samples else 'stale' if age > 30 else 'observed',
            'samples': samples, 'cutoff': cutoff, 'age_seconds': age, 'excluded': excluded,
            'truncated': truncated, 'authority': 'context_only', 'scoring_influence': False,
            'coverage': 'Top 10 levels per side, 15-second receipt-time buckets, at most one hour. Gaps are not filled. Orders may cancel; not executable depth or a predicted liquidation map.'}
