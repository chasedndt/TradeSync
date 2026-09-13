"""What the record says about each horizon, from three days to six months.

For each horizon, from Hyperliquid daily closes only:

- the trend state at a matching scale: the close above or below its moving
  average, and whether that average is rising (20 days for the lower time
  frame, 50 for the medium, 200 for the higher);
- momentum over the horizon's own length (the last week for one week ahead);
- what followed in the past when both states matched today's: the share of
  windows that ended higher, the median move and its bands, with days and
  independent windows; the same for the trend state alone, and for all history;
- the one-sigma range implied by recent volatility over the horizon;
- the levels where the trend state flips, and the recent high and low.

A description of the record, not a forecast. When a state has too few
independent windows the lean falls back to the trend state alone, and says so;
with too few for that as well it says there is too little history to judge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .horizon_stats import daily_volatility, forward_returns, moving_averages, summarize


@dataclass(frozen=True)
class Horizon:
    key: str
    label: str
    days: int
    band: str
    ma_days: int
    vol_lookback: int


HORIZONS: tuple[Horizon, ...] = (
    Horizon("3d", "3 days", 3, "lower", 20, 30),
    Horizon("1w", "1 week", 7, "lower", 20, 30),
    Horizon("2w", "2 weeks", 14, "medium", 50, 60),
    Horizon("1m", "1 month", 30, "medium", 50, 90),
    Horizon("3m", "3 months", 91, "higher", 200, 180),
    Horizon("6m", "6 months", 182, "higher", 200, 365),
)
BANDS = {"lower": "Lower time frame", "medium": "Medium time frame", "higher": "Higher time frame"}
MIN_INDEPENDENT = 8
MIN_HISTORY_DAYS = 120
LEAN_UP, LEAN_DOWN = 0.6, 0.4


def slope_days(ma_days: int) -> int:
    return max(5, ma_days // 4)


def trend_states(closes: Sequence[float], ma_days: int) -> tuple[list[str | None], list[float | None]]:
    """``above_rising``, ``above_falling``, ``below_rising`` or ``below_falling`` for each day."""
    ma = moving_averages(closes, ma_days)
    k = slope_days(ma_days)
    states: list[str | None] = []
    for t, close in enumerate(closes):
        now, before = ma[t], ma[t - k] if t >= k else None
        if now is None or before is None:
            states.append(None)
            continue
        states.append(f"{'above' if close > now else 'below'}_{'rising' if now > before else 'falling'}")
    return states, ma


def momentum_states(closes: Sequence[float], days: int) -> list[str | None]:
    return [None if t < days else ("up" if closes[t] > closes[t - days] else "down") for t in range(len(closes))]


def lean_of(stats: Mapping[str, Any]) -> str:
    """up, down or mixed from the share of windows that ended higher; too_few below the independence floor."""
    if (stats.get("independent_windows") or 0) < MIN_INDEPENDENT or stats.get("share_up") is None:
        return "too_few"
    share = float(stats["share_up"])
    return "up" if share >= LEAN_UP else "down" if share <= LEAN_DOWN else "mixed"


def horizon_read(closes: Sequence[float], h: Horizon, last_complete: bool = True) -> dict[str, Any]:
    base = {"key": h.key, "label": h.label, "days": h.days, "band": h.band}
    trend, ma = trend_states(closes, h.ma_days)
    momentum = momentum_states(closes, h.days)
    now = len(closes) - 1
    state = (trend[now], momentum[now])
    if state[0] is None or state[1] is None:
        needed = h.ma_days + slope_days(h.ma_days)
        return {**base, "available": False, "reason": f"needs {needed} daily closes, has {len(closes)}"}

    forward = forward_returns(closes, h.days, last_complete)
    usable = [t for t in range(len(closes)) if forward[t] is not None and trend[t] is not None and momentum[t] is not None]

    def record(indices: list[int]) -> dict[str, Any]:
        return summarize([forward[t] for t in indices], indices, h.days)

    same_state = record([t for t in usable if (trend[t], momentum[t]) == state])
    same_trend = record([t for t in usable if trend[t] == state[0]])
    lean, basis = lean_of(same_state), "same_state"
    if lean == "too_few" and lean_of(same_trend) != "too_few":
        lean, basis = lean_of(same_trend), "same_trend"

    last, average = closes[now], float(ma[now] or 0.0)
    before = float(ma[now - slope_days(h.ma_days)] or average)
    sigma = daily_volatility(closes, h.vol_lookback)
    implied = None
    if sigma:
        move = sigma * math.sqrt(h.days)
        implied = {"sigma_pct": round((math.exp(move) - 1) * 100, 2), "low": last * math.exp(-move), "high": last * math.exp(move)}
    recent = closes[-max(h.days * 2, 10):]
    return {
        **base,
        "available": True,
        "trend": {"state": state[0], "ma_days": h.ma_days, "ma": average,
                  "ma_slope_pct": round((average / before - 1) * 100, 2) if before else None,
                  "distance_pct": round((last / average - 1) * 100, 2) if average else None},
        "momentum": {"state": state[1], "change_pct": round((last / closes[now - h.days] - 1) * 100, 2)},
        "record": {"same_state": same_state, "same_trend": same_trend, "all_history": record(usable)},
        "lean": lean,
        "lean_basis": basis,
        "implied_range": implied,
        "levels": {"trend_flips_at": average, "recent_high": max(recent), "recent_low": min(recent), "recent_days": len(recent)},
    }


def band_summaries(reads: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for band, label in BANDS.items():
        members = [r for r in reads if r["band"] == band]
        leans = {r["key"]: (r["lean"] if r.get("available") else "unavailable") for r in members}
        values = set(leans.values()) - {"too_few", "unavailable"}
        agreement = next(iter(values)) if len(values) == 1 else ("split" if values else "unjudged")
        out.append({"band": band, "label": label, "horizons": [r["key"] for r in members], "leans": leans, "agreement": agreement})
    return out


def compose_horizons(symbol: str, candles: Sequence[Mapping[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """The outlook for one symbol from daily candles ({time (epoch seconds), close, ...})."""
    rows = sorted((c for c in candles if isinstance(c.get("close"), (int, float)) and c["close"] > 0), key=lambda c: c["time"])
    generated = (now or datetime.now(timezone.utc)).isoformat()
    base = {"schema_version": "horizon_outlook_v1", "symbol": symbol, "generated_at": generated}
    if len(rows) < MIN_HISTORY_DAYS:
        return {**base, "available": False, "reason": f"{len(rows)} daily closes; at least {MIN_HISTORY_DAYS} are needed"}
    closes = [float(c["close"]) for c in rows]
    # Today's bar is still trading: states read its live close, but no record window ends on it.
    last_complete = not (rows[-1]["time"] + 86400 > (now or datetime.now(timezone.utc)).timestamp())
    reads = [horizon_read(closes, h, last_complete) for h in HORIZONS]
    return {
        **base,
        "available": True,
        "last_close": closes[-1],
        "history": {"days": len(closes),
                    "from": datetime.fromtimestamp(rows[0]["time"], timezone.utc).date().isoformat(),
                    "to": datetime.fromtimestamp(rows[-1]["time"], timezone.utc).date().isoformat(),
                    "last_day_complete": last_complete},
        "horizons": reads,
        "bands": band_summaries(reads),
        "method": {
            "data": "Hyperliquid daily closes",
            "state": "close above or below its 20, 50 or 200-day average and that average's slope, with momentum over the horizon's length",
            "record": "what followed past days in the same state over the same horizon: share ending higher, median, 10th to 90th percentile",
            "independence": f"a lean needs {MIN_INDEPENDENT} non-overlapping windows; otherwise the trend state alone, otherwise none",
            "caveat": "a description of the record, not a forecast",
        },
    }
