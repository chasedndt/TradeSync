"""The StrikeZone closed-candle forward test, read as a ledger.

The quant lab in the Hermes fleet writes every closed-candle call (long,
short or no trade) to a signal ledger and, once a paper trade exits, an
outcome with fills, fees, slippage and funding. Neither record carries a
status. A trade call is resolved when an outcome names it, open until it
expires, resolving during the hour the resolver needs after expiry, and
overdue after that. Numbers arrive as decimal strings.

This module turns both records into rows for storage and gives each call
its status. It grants nothing: every record is paper-only.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

DIRECTIONS = ("long", "short", "no_trade")
TRADE_DIRECTIONS = ("long", "short")
RESOLVE_GRACE = timedelta(minutes=60)


def num(value: Any) -> float | None:
    """A decimal string or number as a float; None for blanks, booleans and non-finite values."""
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def normalize_signal(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """A signal-ledger line as a storable row, or None when it lacks identity, market or time."""
    direction = _text(raw.get("direction")).lower()
    signal_id, asset, timeframe = raw.get("signal_id"), raw.get("asset"), raw.get("timeframe")
    signal_at = parse_ts(raw.get("signal_at_utc")) or parse_ts(raw.get("candle_close_utc"))
    if not signal_id or not asset or not timeframe or direction not in DIRECTIONS or signal_at is None:
        return None
    trade = direction in TRADE_DIRECTIONS
    regime = raw.get("regime")
    return {
        "signal_id": str(signal_id),
        "asset": str(asset).upper(),
        "timeframe": str(timeframe),
        "direction": direction,
        "strategy_id": _text(raw.get("strategy_id")),
        "strategy_version": _text(raw.get("strategy_version")),
        "methodology_version": _text(raw.get("methodology_version")),
        "signal_at": signal_at,
        "candle_close_at": parse_ts(raw.get("candle_close_utc")),
        "expiry_at": parse_ts(raw.get("expiry_utc")),
        "entry_price": num(raw.get("entry_reference_price")) if trade else None,
        "invalidation_price": num(raw.get("invalidation_price")) if trade else None,
        "target_price": num(raw.get("target_price")) if trade else None,
        "confidence": num(raw.get("confidence")),
        "regime": {str(k): str(v) for k, v in regime.items()} if isinstance(regime, Mapping) else {},
        "analysis_eligible": raw.get("analysis_eligible") is not False,
        "exclusion_reason": _text(raw.get("analysis_exclusion_reason")) or None,
    }


def normalize_outcome(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """A paper-outcome line as a storable row, or None when it cannot be tied to a signal and market."""
    outcome_id, signal_id = raw.get("outcome_id"), raw.get("signal_id")
    if not outcome_id or not signal_id or not raw.get("asset") or not raw.get("timeframe"):
        return None
    fees = [f for f in (num(raw.get("entry_fee_usdc")), num(raw.get("exit_fee_usdc"))) if f is not None]
    coverage = raw.get("funding_coverage")
    coverage_status = _text(coverage.get("status")) if isinstance(coverage, Mapping) else ""
    return {
        "outcome_id": str(outcome_id),
        "signal_id": str(signal_id),
        "asset": str(raw["asset"]).upper(),
        "timeframe": str(raw["timeframe"]),
        "direction": _text(raw.get("direction")).lower(),
        "methodology_version": _text(raw.get("methodology_version")),
        "exit_reason": _text(raw.get("exit_reason")) or None,
        "exit_at": parse_ts(raw.get("exit_at_utc")),
        "holding_minutes": num(raw.get("holding_duration_minutes")),
        "entry_fill_price": num(raw.get("entry_fill_price")),
        "exit_fill_price": num(raw.get("exit_fill_price")),
        "quantity": num(raw.get("quantity")),
        "gross_pnl_usdc": num(raw.get("gross_pnl_usdc")),
        "net_pnl_usdc": num(raw.get("net_pnl_usdc")),
        "fees_usdc": sum(fees) if fees else None,
        "slippage_usdc": num(raw.get("slippage_cost_usdc")),
        "funding_usdc": num(raw.get("funding_cost_usdc")),
        "funding_coverage": coverage_status or None,
        "correlation_group_id": _text(raw.get("correlation_group_id")) or None,
        "analysis_eligible": raw.get("analysis_eligible") is not False,
    }


def ledger_status(direction: str, expiry_at: datetime | None, has_outcome: bool, now: datetime) -> str:
    """no_trade, resolved, open, resolving (expired within the resolver's hour) or overdue."""
    if direction not in TRADE_DIRECTIONS:
        return "no_trade"
    if has_outcome:
        return "resolved"
    if expiry_at is None or expiry_at > now:
        return "open"
    return "resolving" if now - expiry_at <= RESOLVE_GRACE else "overdue"


def planned_reward_risk(entry: float | None, stop: float | None, target: float | None) -> float | None:
    """Distance to target over distance to the stop, as planned at the call."""
    if entry is None or stop is None or target is None:
        return None
    risk = abs(entry - stop)
    return round(abs(target - entry) / risk, 2) if risk > 0 else None
