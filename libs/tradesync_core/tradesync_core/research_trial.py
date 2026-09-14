"""Frozen research definitions. Registration does not schedule or approve trades."""
import hashlib
import json
from .source_comparison import VERSION, THRESHOLD, numeric, compare


def specification(style):
    if style not in ('scalp', 'intraday', 'swing'):
        raise ValueError('Unsupported holding style')
    return {
        'schema': 'research-trial-v1', 'candidate': VERSION, 'style': style,
        'threshold': THRESHOLD, 'universe': ['BTC-PERP', 'ETH-PERP', 'SOL-PERP'],
        'population': 'Operator-selected managed-paper entries strictly after registration',
        'window_days': 30, 'evaluation': 'After the entry window and all admitted positions resolve',
        'primary_metric': 'Mean paired net bps difference per original clean eligible entry',
        'missing_context_policy': 'Abstain and report missing coverage separately',
        'observation_gap_policy': 'Exclude and report, never repair unseen crossings',
        'minimum_clean_entries_for_review': 100,
        'sample_gate_note': 'Operational review floor, not a power calculation or significance guarantee',
        'costs': 'Frozen per-position fees/slippage and scenario funding; not settled account costs',
        'promotion': 'Never automatic; no live execution authority',
        'selection_bias': 'Operator selection and overlapping positions remain; not a randomized causal trial',
    }


def fingerprint(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def evaluate(spec, registered_at, now, rows):
    if not numeric(registered_at) or not numeric(now) or registered_at <= 0 or now < registered_at:
        raise ValueError('Invalid evaluation clock')
    # Never silently run a changed implementation against an older definition.
    if spec != specification(spec.get('style')):
        raise ValueError('Stored specification needs its matching evaluator version')
    end = registered_at+spec['window_days']*86400
    admitted, excluded, pending = [], 0, 0
    for row in rows:
        p = row.get('position_state') if isinstance(row, dict) else None
        at = p.get('entry_time') if isinstance(p, dict) else None
        if (not numeric(at) or not registered_at < at <= min(now, end)
                or p.get('style') != spec['style'] or row.get('symbol') not in spec['universe']):
            excluded += 1
            continue
        if p.get('status') != 'closed':
            pending += 1
            continue
        exit_at = p.get('exit_time')
        if not numeric(exit_at) or not at <= exit_at <= now:
            pending += 1
            continue
        admitted.append(row)
    result = compare(admitted)
    state = ('collecting' if now <= end else 'awaiting_outcomes' if pending else
             'insufficient_clean_sample' if result['eligible'] < spec['minimum_clean_entries_for_review'] else 'ready_for_manual_review')
    return {'state':state, 'entry_window_ends_at':end, 'pending_outcomes':pending,
            'outside_population':excluded, 'comparison':result, 'promotion_allowed':False,
            'note':'Descriptive interim results are not final evidence. Manual review readiness is not statistical significance or trading permission.'}
