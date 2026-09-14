"""Recorded trade economics, not a strategy recommendation or a profitability claim."""
from __future__ import annotations

from collections import Counter
from statistics import median

from .strikezone_ledger import num


def economics(row: dict) -> dict:
    entry, stop, target = (num(row.get(k)) for k in ('entry_price', 'invalidation_price', 'target_price'))
    side = 1 if row.get('direction') == 'long' else -1 if row.get('direction') == 'short' else 0
    valid = bool(side and entry and entry > 0 and stop and stop > 0 and target and target > 0 and side * (entry - stop) > 0 and side * (target - entry) > 0)
    fill, exit_price = num(row.get('entry_fill_price')), num(row.get('exit_fill_price'))
    quantity = num(row.get('quantity'))
    notional = fill * quantity if fill and fill > 0 and quantity and quantity > 0 else None
    net = num(row.get('net_pnl_usdc'))
    gross = num(row.get('gross_pnl_usdc'))
    # Gross minus net uses the ledger's own accounting, avoiding double-counted
    # slippage where it is already included in fill prices.
    return {
        'valid_levels': valid,
        'target_move_pct': side * (target / entry - 1) * 100 if valid else None,
        'stop_move_pct': side * (1 - stop / entry) * 100 if valid else None,
        'realized_price_move_pct': side * (exit_price / fill - 1) * 100 if side and fill and fill > 0 and exit_price else None,
        'net_return_pct': net / notional * 100 if net is not None and notional else None,
        'cost_drag_usdc': gross - net if gross is not None and net is not None else None,
    }


def summarize(rows: list[dict]) -> dict:
    """One record per signal; denominator excludes unresolved/null-P&L outcomes."""
    resolved = [r for r in rows if r.get('outcome_id') and num(r.get('net_pnl_usdc')) is not None]
    values = [float(r['net_pnl_usdc']) for r in resolved]
    measured = [economics(r) for r in rows]
    outcomes = [economics(r) for r in resolved]
    def med(values):
        valid = [v for v in values if v is not None]
        return round(median(valid), 4) if valid else None
    gains, losses = sum(v for v in values if v > 0), -sum(v for v in values if v < 0)
    moves = [r['realized_price_move_pct'] for r in outcomes if r['realized_price_move_pct'] is not None]
    return {
        'trades': len(rows), 'resolved': len(resolved), 'unresolved_or_missing_pnl': len(rows) - len(resolved),
        'net_usdc': round(sum(values), 4) if values else None,
        'expectancy_usdc': round(sum(values) / len(values), 4) if values else None,
        'win_rate': sum(v > 0 for v in values) / len(values) if values else None,
        'profit_factor': round(gains / losses, 4) if losses else None,
        'median_target_pct': med([r['target_move_pct'] for r in measured]),
        'median_move_pct': med(moves), 'measured_moves': len(moves),
        'moves_at_least_3pct': sum(v >= 3 for v in moves),
        'median_holding_minutes': med([num(r.get('holding_minutes')) for r in resolved]),
        'median_net_return_pct': med([r['net_return_pct'] for r in outcomes]),
        'invalid_level_rows': sum(not r['valid_levels'] for r in measured),
        'exit_reasons': dict(Counter(r.get('exit_reason') or 'unknown' for r in resolved)),
        'cost_drag_usdc': round(sum(r['cost_drag_usdc'] for r in outcomes), 4) if outcomes and all(r['cost_drag_usdc'] is not None for r in outcomes) else None,
        'cost_measured': sum(r['cost_drag_usdc'] is not None for r in outcomes),
    }
