"""Frozen descriptive source ablation; not causal attribution or promotion.

Compare baseline and a hypothetical abstention policy on the SAME clean closed
paper entries. Selection remains operator-driven and costs are paper assumptions.
"""
import math

VERSION = 'book-alignment-ablation-v1'
THRESHOLD = 0.2


def numeric(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def book_alignment(evidence, position):
    if not isinstance(evidence, dict) or not isinstance(position, dict): return None
    external = evidence.get('external_context')
    if not isinstance(external, dict): return None
    context = external.get('hyperliquid_book_history')
    if not isinstance(context, dict) or context.get('status') != 'observed':
        return None
    cutoff, entry = context.get('cutoff'), position.get('entry_time')
    if not numeric(cutoff) or not numeric(entry) or cutoff > entry or entry-cutoff > 30:
        return None
    samples = context.get('samples')
    if not isinstance(samples, list) or not samples:
        return None
    last = samples[-1]
    at = last.get('time') if isinstance(last, dict) else None
    if not numeric(at) or not 0 <= entry-at <= 30:
        return None
    totals = {'bids': 0., 'asks': 0.}
    levels = last.get('levels')
    if not isinstance(levels, list):
        return None
    for level in levels:
        if not isinstance(level, dict): return None
        side, amount = level.get('side'), level.get('notional_usd')
        if side not in totals or not numeric(amount) or amount <= 0: return None
        totals[side] += amount
    if min(totals.values()) <= 0 or not math.isfinite(sum(totals.values())):
        return None
    direction = position.get('side')
    if direction not in ('long', 'short'): return None
    imbalance = (totals['bids']-totals['asks'])/sum(totals.values())
    return imbalance*(1 if direction == 'long' else -1)


def compare(rows):
    baseline, filtered, covered, selected, excluded = [], [], 0, 0, {}
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            excluded['invalid_record'] = excluded.get('invalid_record', 0)+1
            continue
        identity = row.get('id')
        p = row.get('position_state', {})
        if not isinstance(p, dict):
            excluded['invalid_record'] = excluded.get('invalid_record', 0)+1
            continue
        reason = ('duplicate_or_missing_id' if not isinstance(identity, str) or not identity or identity in seen else
                  'not_closed' if p.get('status') != 'closed' else
                  'observation_gap' if p.get('observation_gap') is not False else
                  'invalid_outcome' if not numeric(p.get('net_estimate_usdc')) or not numeric(p.get('notional')) or p['notional'] <= 0 else None)
        if reason:
            excluded[reason] = excluded.get(reason, 0)+1
            continue
        seen.add(identity)
        outcome = p['net_estimate_usdc']/p['notional']*10000
        if not math.isfinite(outcome):
            excluded['invalid_outcome'] = excluded.get('invalid_outcome', 0)+1
            continue
        baseline.append(outcome)
        alignment = book_alignment(row.get('entry_evidence', {}), p)
        if alignment is not None: covered += 1
        take = alignment is not None and alignment >= THRESHOLD
        if take: selected += 1
        filtered.append(outcome if take else 0.)
    n = len(baseline)
    return {'version': VERSION, 'alignment_threshold': THRESHOLD, 'eligible': n,
            'context_available': covered, 'selected': selected, 'abstained': n-selected,
            'excluded': excluded, 'baseline_mean_bps_per_opportunity': sum(baseline)/n if n else None,
            'filter_mean_bps_per_opportunity': sum(filtered)/n if n else None,
            'paired_mean_difference_bps': sum(b-a for a,b in zip(baseline,filtered))/n if n else None,
            'authority': 'research_only', 'promotion_allowed': False,
            'note': 'Same-entry retrospective abstention diagnostic. Missing context abstains and is counted separately. Not an independent forward trial, causal source benefit, capital return or profitability proof. No confidence interval; overlapping/operator-selected trades and scenario costs limit inference.'}
