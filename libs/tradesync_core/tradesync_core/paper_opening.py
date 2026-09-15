"""Opening a managed paper position: the entry fill, the frozen plan and every entry gate.

Two ways in. ``open_position`` walks an observed order book for the notional: the
live path. ``open_position_on_candle`` enters at a closed candle's open moved against
the order by a recorded book's cost: for replays, where no full book exists for that
moment. Both freeze the same plan: the style's versioned rules, the stop, target,
trail and expiry, the fee schedule, the entry fill with the snapshot it came from, and
the planning budget the gates used.

Gates: the notional cap, a valid stop distance, reward against the cost budget, and
the planned-risk cap. The budget counts both fees, both fills' cost against the mid
and funding over the whole hold at the planning rate. It is deliberately conservative
(the entry fill already holds half of the spread) and never enters profit and loss.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import paper_depth as depth
from . import paper_funding as funding
from .paper_lifecycle_rules import COMMON, LIFECYCLE_VERSION, RULES
from .paper_observations import finite, quote
from .paper_rehearsal import HYPERLIQUID_BASE_FEES


def order_sides(side: str) -> tuple[str, str]:
    """(entry order side, exit order side) for a position side."""
    return ("buy", "sell") if side == "long" else ("sell", "buy")


def _check_request(side, style, notional, volatility):
    if side not in ("long", "short") or style not in RULES:
        raise ValueError("Unsupported side or style")
    finite(notional, True)
    finite(volatility, True)
    if notional > COMMON.max_notional_usdc:
        raise ValueError(f"Initial managed-paper cap is {COMMON.max_notional_usdc:g} USDC per position")


def _planning(planning_funding: Mapping[str, Any] | None) -> dict[str, Any]:
    if planning_funding is not None:
        return dict(planning_funding)
    return funding.planning_bps_hour({}, COMMON.planning_funding_floor_bps_hour)


def _plan(side, style, notional, volatility, *, entry_fill, exit_estimate, entry_cost, exit_cost, entry_time, observed_at, planning_funding):
    rules = RULES[style]
    sign = 1 if side == "long" else -1
    entry, quantity = entry_fill["fill_price"], entry_fill["quantity"]
    distance = max(volatility * rules.stop_atr, entry * rules.min_target_pct / 100 / rules.reward_risk)
    stop, target = entry - sign * distance, entry + sign * distance * rules.reward_risk
    if min(stop, target) <= 0 or distance / entry > COMMON.max_stop_share:
        raise ValueError("Invalid stop distance")
    fee = HYPERLIQUID_BASE_FEES.taker_fee
    budget = (entry * 2 * fee + entry_cost + exit_cost
              + entry * planning_funding["bps_hour"] * rules.max_hold_s / 3600 / 10000)
    reward = distance * rules.reward_risk
    if reward < COMMON.min_reward_cost_multiple * budget or (reward - budget) / (distance + budget) < COMMON.min_net_reward_risk:
        raise ValueError("Insufficient reward after declared costs")
    planned_risk = (distance + budget) * quantity
    if planned_risk > COMMON.max_planned_risk_usdc:
        raise ValueError(f"Initial planned paper-risk cap is {COMMON.max_planned_risk_usdc:g} USDC; gaps can exceed it")
    entry_fee = entry * quantity * fee
    return {
        "version": LIFECYCLE_VERSION, "side": side, "style": style, "status": "open",
        "rules": rules.to_dict(), "atr": volatility,
        "entry_time": entry_time, "entry_quote_time": observed_at, "last_quote_time": observed_at, "evaluated_through": observed_at,
        "entry_price": entry, "quantity": quantity, "notional": notional,
        "stop": stop, "target": target, "expiry": entry_time + rules.max_hold_s,
        "current_stop": stop, "current_stop_rule": "stop",
        "trail": {"activate_price": entry + sign * distance * rules.trail_activate_r, "distance": volatility * rules.trail_atr,
                  "best": None, "active": False, "stop": None},
        "fees": {"schedule": HYPERLIQUID_BASE_FEES.to_dict(), "liquidity": "taker", "rate": fee,
                 "entry_usdc": entry_fee, "exit_usdc": None, "exit_estimate_usdc": None},
        "slippage": {"model": depth.MODEL, "entry": entry_fill, "exit": None},
        "funding": funding.summary(entry_time, entry_time, []),
        "planning": {"cost_budget_usdc": budget * quantity, "reward_usdc": reward * quantity, "stop_distance": distance,
                     "funding": planning_funding, "exit_estimate": exit_estimate},
        "planned_risk_usdc": planned_risk, "entry_fee_usdc": entry_fee,
        "gross_pnl_usdc": None, "fees_usdc": entry_fee, "funding_usdc": 0.0, "net_estimate_usdc": None, "mark_exit_price": None,
        "observations": 0, "candles": 0, "observation_gap": False, "max_observation_gap_s": 0,
        "pending_exit": None, "exit": None, "execution_authority": False,
    }


def open_position(side, style, notional, volatility, book, now_s, *, planning_funding=None):
    """Open from an observed book: the entry walks the book for the notional; any failed gate refuses it."""
    _check_request(side, style, notional, volatility)
    at, _bid, _ask = quote(book, now_s)
    source = depth.snapshot(book, observed_at=at, received_at=now_s)
    buy, sell = order_sides(side)
    try:
        entry_fill = depth.book_fill(depth.walk(book, buy, notional=notional, source=source))
        exit_estimate = depth.book_fill(depth.walk(book, sell, quantity=entry_fill["quantity"], source=source))
    except depth.InsufficientDepth as exc:
        raise ValueError(f"Paper size exceeds displayed depth: {exc}") from None
    return _plan(side, style, notional, volatility, entry_fill=entry_fill, exit_estimate=exit_estimate,
                 entry_cost=abs(entry_fill["fill_price"] - entry_fill["mid"]),
                 exit_cost=abs(exit_estimate["fill_price"] - exit_estimate["mid"]),
                 entry_time=now_s, observed_at=at, planning_funding=_planning(planning_funding))


def open_position_on_candle(side, style, notional, volatility, bar, cost_book, *, cost_source=None, planning_funding=None):
    """Open at a candle's open, for replays: the open moved against the order by a recorded book's cost."""
    _check_request(side, style, notional, volatility)
    at, reference = finite(bar.get("time"), True), finite(bar.get("open"), True)
    buy, sell = order_sides(side)
    try:
        entry_walk = depth.walk(cost_book, buy, notional=notional, source=cost_source)
        entry_price = depth.priced(reference, entry_walk)
        quantity = notional / entry_price
        exit_walk = depth.walk(cost_book, sell, quantity=quantity, source=cost_source)
    except depth.InsufficientDepth as exc:
        raise ValueError(f"Paper size exceeds recorded depth: {exc}") from None
    entry_fill = depth.reference_fill(entry_walk, reference, quantity)
    exit_estimate = depth.reference_fill(exit_walk, entry_price, quantity)
    return _plan(side, style, notional, volatility, entry_fill=entry_fill, exit_estimate=exit_estimate,
                 entry_cost=abs(entry_price - reference), exit_cost=abs(exit_estimate["fill_price"] - entry_price),
                 entry_time=at, observed_at=at, planning_funding=_planning(planning_funding))
