"""Exit rules for a managed paper position, evaluated on observations in time order.

Two kinds of observation reach a position:

- a quote: the executable touch at one instant, the bid a long sells into or the
  ask a short buys back from;
- a closed candle: open, high, low and close over an interval whose instants in
  between were not seen one by one.

Rules are checked in one order: the stop in force (the initial stop, or the
trailing stop once it is tighter), then the target, then the time expiry, then an
operator close. Every exit is a market exit at the observation that fired it. When
price gaps through a stop between observations, the exit is priced at the first
observed price past it, which is worse than the stop, never at the stop itself.

Inside one candle the order of the high and the low is unknown. A candle that
reaches both the stop and the target counts as the stop, and the trailing stop
moves only after an observation has been checked, so a candle's own high cannot
tighten the stop its own low then hits. An exit inside a candle is dated at the
candle's open, the earliest instant it could have happened.
"""

from __future__ import annotations

from typing import Any, Mapping

RULE_ORDER = ("stop", "trailing_stop", "target", "time_expiry", "operator_close")


def direction(position: Mapping[str, Any]) -> int:
    return 1 if position["side"] == "long" else -1


def stop_in_force(position: Mapping[str, Any]) -> tuple[float, str]:
    """The stop that applies now, and whether it is the initial or the trailing stop."""
    trail = position["trail"]
    sign = direction(position)
    if trail.get("stop") is not None and sign * (trail["stop"] - position["stop"]) > 0:
        return trail["stop"], "trailing_stop"
    return position["stop"], "stop"


def ratchet(position: Mapping[str, Any], favourable_price: float) -> dict[str, Any]:
    """The trail after an exit-side price that fired nothing: best price, activation, and a stop that only tightens."""
    sign = direction(position)
    trail = dict(position["trail"])
    best = trail.get("best")
    if best is None or sign * (favourable_price - best) > 0:
        best = favourable_price
    active = bool(trail.get("active")) or sign * (best - trail["activate_price"]) >= 0
    stop = trail.get("stop")
    if active:
        candidate = best - sign * trail["distance"]
        if stop is None or sign * (candidate - stop) > 0:
            stop = candidate
    trail.update(best=best, active=active, stop=stop)
    return trail


def _fired(rule: str, level: float | None, trigger_price: float, at: float, *, gap_fill: bool = False, **extra: Any) -> dict[str, Any]:
    return {"rule": rule, "level": level, "trigger_price": trigger_price, "at": at, "gap_fill": gap_fill, **extra}


def on_quote(position: Mapping[str, Any], touch: float, observed_at: float, *, operator_close: bool = False) -> dict[str, Any] | None:
    """The rule an executable touch fires at ``observed_at``, or None."""
    sign = direction(position)
    level, rule = stop_in_force(position)
    if sign * (touch - level) <= 0:
        return _fired(rule, level, touch, observed_at, gap_fill=sign * (touch - level) < 0)
    if sign * (touch - position["target"]) >= 0:
        return _fired("target", position["target"], touch, observed_at)
    if observed_at >= position["expiry"]:
        return _fired("time_expiry", position["expiry"], touch, observed_at)
    if operator_close:
        return _fired("operator_close", None, touch, observed_at)
    return None


def on_candle(position: Mapping[str, Any], bar: Mapping[str, Any], interval_s: float) -> dict[str, Any] | None:
    """The rule a closed candle fires and the price it fires at, or None.

    The open is an observed instant and is checked first, so a gap through a level
    fires at the open. Inside the candle the stop in force comes before the target.
    A time expiry falling inside a candle that fired nothing is taken at its close.
    """
    open_time = bar["time"]
    fired = on_quote(position, bar["open"], open_time)
    if fired:
        return {**fired, "path": "open"}
    sign = direction(position)
    level, rule = stop_in_force(position)
    adverse = bar["low"] if sign == 1 else bar["high"]
    favourable = bar["high"] if sign == 1 else bar["low"]
    reached_stop = sign * (adverse - level) <= 0
    reached_target = sign * (favourable - position["target"]) >= 0
    if reached_stop:
        return _fired(rule, level, level, open_time, path="inside", ambiguous=reached_target)
    if reached_target:
        return _fired("target", position["target"], position["target"], open_time, path="inside")
    close_time = open_time + interval_s
    if close_time >= position["expiry"]:
        return _fired("time_expiry", position["expiry"], bar["close"], close_time, path="close")
    return None


def favourable_extreme(position: Mapping[str, Any], bar: Mapping[str, Any]) -> float:
    """The exit-side price most in the position's favour within a candle: the high for a long, the low for a short."""
    return bar["high"] if direction(position) == 1 else bar["low"]
