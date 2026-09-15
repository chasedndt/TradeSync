"""Managed paper positions: advanced on observations in time order, costs settled as they are known.

The pieces, one responsibility each:

- ``paper_lifecycle_rules``: every parameter, versioned;
- ``paper_observations``: what counts as a usable book or candle;
- ``paper_opening``: the entry fill, the frozen plan and the entry gates;
- ``paper_exits``: which rule an observation fires;
- ``paper_depth``: fills walked through observed books;
- ``paper_funding``: Hyperliquid's settled hourly funding;
- fees: the published base schedule the rehearsal journal already uses
  (``paper_rehearsal.HYPERLIQUID_BASE_FEES``).

This module advances an open position on a quote or a closed candle and keeps its
accounts. Profit and loss is gross from the fill prices (spread and depth already
inside them), minus the taker fee on both fills, minus settled funding. While open,
the exit is marked by walking the latest book for the position's quantity, with the
exit fee estimated at that mark. No venue, wallet or approval dependency.

Missed intervals are never reconstructed: a silence between quote observations
longer than the common threshold is latched and disqualifies the position as clean
evidence. Closed candles are a separate, explicit observation kind.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from . import paper_depth as depth
from . import paper_exits as exits
from . import paper_funding as funding
from .paper_lifecycle_rules import COMMON, LIFECYCLE_VERSION, RULES
from .paper_observations import atr, candle, finite, quote
from .paper_opening import open_position, open_position_on_candle, order_sides

__all__ = ["VERSION", "PROFILES", "finite", "quote", "atr", "open_position", "open_position_on_candle",
           "advance", "advance_on_candle", "settle_funding"]

VERSION = LIFECYCLE_VERSION
# Interval, holding time and stop parameters per style, in the shape earlier callers read.
PROFILES = {style: {"interval": r.atr_interval, "seconds": r.atr_seconds, "max_hold_s": r.max_hold_s,
                    "stop_atr": r.stop_atr, "reward_risk": r.reward_risk, "min_target_pct": r.min_target_pct}
            for style, r in RULES.items()}


def _trail(result, favourable_price):
    result["trail"] = exits.ratchet(result, favourable_price)
    level, rule = exits.stop_in_force(result)
    result.update(current_stop=level, current_stop_rule=rule)


def _close(result, fired, fill, fill_observation, at):
    result["fees"].update(exit_usdc=result["fees"]["rate"] * fill["fill_price"] * result["quantity"], exit_estimate_usdc=None)
    result["slippage"]["exit"] = fill
    result["exit"] = {"rule": fired["rule"], "level": fired["level"], "trigger_price": fired["trigger_price"],
                      "gap_fill": fired["gap_fill"], "path": fired.get("path"), "ambiguous_candle": fired.get("ambiguous", False),
                      "trigger_observation": fired["observation"], "fill_observation": fill_observation,
                      "fill_price": fill["fill_price"], "at": at}
    result.update(status="closed", exit_reason=fired["rule"], exit_time=at, exit_price=fill["fill_price"], pending_exit=None)


def _account(result, mark_price, funding_rows):
    sign = 1 if result["side"] == "long" else -1
    quantity = result["quantity"]
    closed = result["status"] == "closed"
    gross = sign * (mark_price - result["entry_price"]) * quantity
    exit_fee = result["fees"]["exit_usdc"] if closed else result["fees"]["rate"] * mark_price * quantity
    if not closed:
        result["fees"]["exit_estimate_usdc"] = exit_fee
    settled = funding.summary(result["entry_time"], result["exit_time"] if closed else result["evaluated_through"], funding_rows)
    fees = result["fees"]["entry_usdc"] + exit_fee
    result.update(funding=settled, mark_exit_price=mark_price, gross_pnl_usdc=gross, fees_usdc=fees,
                  funding_usdc=settled["accrued_usdc"], net_estimate_usdc=gross - fees - settled["accrued_usdc"])
    return result


def advance(position, book, now_s, *, manual_close=False, funding_rows: Sequence[Mapping[str, Any]] | None = None):
    """Advance on one observed book: gap latch, exit rules, trailing stop, mark and costs."""
    if position["status"] != "open":
        return copy.deepcopy(position)
    at, bid, ask = quote(book, now_s)
    if at <= position["evaluated_through"]:
        raise ValueError("Duplicate or out-of-order observation")
    result = copy.deepcopy(position)
    gap = at - position["last_quote_time"]
    result.update(last_quote_time=at, evaluated_through=at, observations=position["observations"] + 1,
                  observation_gap=position["observation_gap"] or gap > COMMON.observation_gap_s,
                  max_observation_gap_s=max(position["max_observation_gap_s"], gap))
    touch = bid if position["side"] == "long" else ask
    observation = {"kind": "quote", "observed_at": at, "received_at": now_s, "best_bid": bid, "best_ask": ask, "touch": touch}
    source = depth.snapshot(book, observed_at=at, received_at=now_s)
    try:
        fill, unfilled = depth.book_fill(depth.walk(book, order_sides(position["side"])[1], quantity=position["quantity"], source=source)), None
    except depth.InsufficientDepth as exc:
        fill, unfilled = None, str(exc)
    pending = position.get("pending_exit")
    fired = pending or exits.on_quote(result, touch, at, operator_close=manual_close)
    if fired and fill:
        _close(result, fired if pending else {**fired, "observation": observation}, fill, observation, at)
    elif fired:
        # The rule fired but the displayed book cannot take the whole quantity: the exit stays
        # owed and fills at the first later observation that can, both observations recorded.
        result["pending_exit"] = pending or {**fired, "observation": observation, "unfilled": unfilled}
    else:
        _trail(result, touch)
    mark = result["exit_price"] if result["status"] == "closed" else fill["fill_price"] if fill else touch
    return _account(result, mark, funding_rows)


def advance_on_candle(position, bar, interval_s, cost_book, now_s, *, cost_source=None,
                      funding_rows: Sequence[Mapping[str, Any]] | None = None):
    """Advance on one closed candle: a gap at the open, the stop before the target inside it, the trail after it."""
    if position["status"] != "open":
        return copy.deepcopy(position)
    candle(bar)
    open_time, interval = bar["time"], finite(interval_s, True)
    if open_time + interval > now_s:
        raise ValueError("Candle not closed")
    if open_time < position["evaluated_through"]:
        raise ValueError("Candle overlaps evaluated observations or is out of order")
    result = copy.deepcopy(position)
    observation = {"kind": "candle", "interval_s": interval, "open_time": open_time, "close_time": open_time + interval,
                   "open": bar["open"], "high": bar["high"], "low": bar["low"], "close": bar["close"], "received_at": now_s}
    result.update(candles=position.get("candles", 0) + 1, evaluated_through=open_time + interval)
    try:
        walked = depth.walk(cost_book, order_sides(position["side"])[1], quantity=position["quantity"], source=cost_source)
    except depth.InsufficientDepth as exc:
        raise ValueError(f"Recorded book cannot price the exit: {exc}") from None
    fired = exits.on_candle(result, bar, interval)
    if fired:
        fill = depth.reference_fill(walked, fired["trigger_price"], position["quantity"])
        _close(result, {**fired, "observation": observation}, fill, observation, fired["at"])
        mark = result["exit_price"]
    else:
        _trail(result, exits.favourable_extreme(result, bar))
        mark = depth.priced(bar["close"], walked)
    return _account(result, mark, funding_rows)


def settle_funding(position, funding_rows: Sequence[Mapping[str, Any]] | None):
    """The position with settled funding brought up to date: through its exit when closed, its last observation when open."""
    result = copy.deepcopy(position)
    mark = result["exit_price"] if result["status"] == "closed" else result.get("mark_exit_price")
    if mark is None:
        result["funding"] = funding.summary(result["entry_time"], result["evaluated_through"], funding_rows)
        result["funding_usdc"] = result["funding"]["accrued_usdc"]
        return result
    return _account(result, mark, funding_rows)
