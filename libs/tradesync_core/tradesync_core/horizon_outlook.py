"""What the record says about each horizon, from one hour to six months.

For each horizon, on the bars it is read on (``horizon_spec``):

- the trend state at a matching scale: the close above or below its moving
  average, and whether that average is rising;
- momentum over the horizon's own length (the last four hours for four hours ahead);
- what followed in the past when both states matched today's: the share of
  windows that ended higher, the median move and its bands, with bars and
  independent windows; the same for the trend state alone, and for all history;
- the one-sigma range implied by recent volatility over the horizon;
- the levels where the trend state flips, and the recent high and low.

A description of the record, not a forecast. When a state has too few
independent windows the lean falls back to the trend state alone, and says so;
with too few for that as well it says there is too little history to judge.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .horizon_bars import Bars
from .horizon_spec import BANDS, HORIZONS, INTERVAL_WORDS, Horizon
from .horizon_stats import daily_volatility, forward_returns, moving_averages, summarize

MIN_INDEPENDENT = 8
MIN_HISTORY_BARS = 120
MIN_HISTORY_DAYS = MIN_HISTORY_BARS  # the older name, still imported by callers
LEAN_UP, LEAN_DOWN = 0.6, 0.4

__all__ = ["BANDS", "HORIZONS", "Horizon", "MIN_HISTORY_BARS", "MIN_INDEPENDENT", "band_summaries", "compose_horizons",
           "horizon_read", "lean_of", "momentum_states", "slope_bars", "trend_states"]


def slope_bars(ma_bars: int) -> int:
    return max(5, ma_bars // 4)


slope_days = slope_bars  # the older name


def trend_states(closes: Sequence[float], ma_bars: int) -> tuple[list[str | None], list[float | None]]:
    """``above_rising``, ``above_falling``, ``below_rising`` or ``below_falling`` for each bar."""
    ma = moving_averages(closes, ma_bars)
    k = slope_bars(ma_bars)
    states: list[str | None] = []
    for t, close in enumerate(closes):
        now, before = ma[t], ma[t - k] if t >= k else None
        if now is None or before is None:
            states.append(None)
            continue
        states.append(f"{'above' if close > now else 'below'}_{'rising' if now > before else 'falling'}")
    return states, ma


def momentum_states(closes: Sequence[float], steps: int) -> list[str | None]:
    return [None if t < steps else ("up" if closes[t] > closes[t - steps] else "down") for t in range(len(closes))]


def lean_of(stats: Mapping[str, Any]) -> str:
    """up, down or mixed from the share of windows that ended higher; too_few below the independence floor."""
    if (stats.get("independent_windows") or 0) < MIN_INDEPENDENT or stats.get("share_up") is None:
        return "too_few"
    share = float(stats["share_up"])
    return "up" if share >= LEAN_UP else "down" if share <= LEAN_DOWN else "mixed"


def horizon_read(closes: Sequence[float], h: Horizon, last_complete: bool = True) -> dict[str, Any]:
    base = {"key": h.key, "label": h.label, "steps": h.steps, "interval": h.interval, "band": h.band}
    trend, ma = trend_states(closes, h.ma_bars)
    momentum = momentum_states(closes, h.steps)
    now = len(closes) - 1
    state = (trend[now], momentum[now]) if now >= 0 else (None, None)
    if state[0] is None or state[1] is None:
        needed = h.ma_bars + slope_bars(h.ma_bars)
        return {**base, "available": False, "reason": f"needs {needed} {INTERVAL_WORDS[h.interval]} closes, has {len(closes)}"}

    forward = forward_returns(closes, h.steps, last_complete)
    usable = [t for t in range(len(closes)) if forward[t] is not None and trend[t] is not None and momentum[t] is not None]

    def record(indices: list[int]) -> dict[str, Any]:
        return summarize([forward[t] for t in indices], indices, h.steps)

    same_state = record([t for t in usable if (trend[t], momentum[t]) == state])
    same_trend = record([t for t in usable if trend[t] == state[0]])
    lean, basis = lean_of(same_state), "same_state"
    if lean == "too_few" and lean_of(same_trend) != "too_few":
        lean, basis = lean_of(same_trend), "same_trend"

    last, average = closes[now], float(ma[now] or 0.0)
    before = float(ma[now - slope_bars(h.ma_bars)] or average)
    sigma = daily_volatility(closes, h.vol_bars)
    implied = None
    if sigma:
        move = sigma * math.sqrt(h.steps)
        implied = {"sigma_pct": round((math.exp(move) - 1) * 100, 2), "low": last * math.exp(-move), "high": last * math.exp(move)}
    recent = closes[-max(h.steps * 2, 10):]
    return {
        **base,
        "available": True,
        "trend": {"state": state[0], "ma_bars": h.ma_bars, "ma_label": h.span(h.ma_bars), "ma": average,
                  "ma_slope_pct": round((average / before - 1) * 100, 2) if before else None,
                  "distance_pct": round((last / average - 1) * 100, 2) if average else None},
        "momentum": {"state": state[1], "change_pct": round((last / closes[now - h.steps] - 1) * 100, 2)},
        "record": {"same_state": same_state, "same_trend": same_trend, "all_history": record(usable)},
        "lean": lean,
        "lean_basis": basis,
        "implied_range": implied,
        "levels": {"trend_flips_at": average, "recent_high": max(recent), "recent_low": min(recent),
                   "recent_bars": len(recent), "recent_label": h.span(len(recent))},
    }


def band_summaries(reads: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for band, label in BANDS.items():
        members = [r for r in reads if r["band"] == band]
        if not members:
            continue
        leans = {r["key"]: (r["lean"] if r.get("available") else "unavailable") for r in members}
        values = set(leans.values()) - {"too_few", "unavailable"}
        agreement = next(iter(values)) if len(values) == 1 else ("split" if values else "unjudged")
        out.append({"band": band, "label": label, "horizons": [r["key"] for r in members], "leans": leans, "agreement": agreement})
    return out


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def compose_horizons(symbol: str, bars_by_interval: Mapping[str, Bars], now: datetime | None = None,
                     horizons: Sequence[Horizon] = HORIZONS) -> dict[str, Any]:
    """The outlook for one symbol from bars per interval (``15m``, ``1h``, ``1d``)."""
    generated = (now or datetime.now(timezone.utc)).isoformat()
    base = {"schema_version": "horizon_outlook_v2", "symbol": symbol, "generated_at": generated}
    usable = {iv: b for iv, b in bars_by_interval.items() if len(b) >= MIN_HISTORY_BARS}
    if not usable:
        counts = ", ".join(f"{len(b)} {iv}" for iv, b in bars_by_interval.items()) or "no bars"
        return {**base, "available": False, "reason": f"{counts}; at least {MIN_HISTORY_BARS} bars are needed"}
    reads = []
    for h in horizons:
        bars = usable.get(h.interval)
        if bars is None:
            have = len(bars_by_interval.get(h.interval) or ())
            reads.append({"key": h.key, "label": h.label, "steps": h.steps, "interval": h.interval, "band": h.band, "available": False,
                          "reason": f"{have} {INTERVAL_WORDS[h.interval]} candles; at least {MIN_HISTORY_BARS} are needed"})
            continue
        reads.append(horizon_read(bars.closes, h, last_complete=not bars.last_partial))
    finest = min(usable.values(), key=lambda b: b.bar_seconds)
    return {
        **base,
        "available": True,
        "last_close": finest.closes[-1],
        "history": {iv: {"bars": len(b), "from": _iso(b.times[0]), "to": _iso(b.times[-1]), "last_bar_complete": not b.last_partial}
                    for iv, b in usable.items()},
        "horizons": reads,
        "bands": band_summaries(reads),
        "method": {
            "data": "Hyperliquid candles: 15-minute and hourly for the short term, daily from 2020 for longer horizons",
            "state": "close above or below its average (matched to each horizon) and that average's slope, with momentum over the horizon's length",
            "record": "what followed past bars in the same state over the same horizon: share ending higher, median, 10th to 90th percentile",
            "independence": f"a lean needs {MIN_INDEPENDENT} non-overlapping windows; otherwise the trend state alone, otherwise none",
            "weights": "each feature's weight is the skill it showed on the newest 30% of history after learning on the older 70%",
            "caveat": "a description of the record, not a forecast",
        },
    }
