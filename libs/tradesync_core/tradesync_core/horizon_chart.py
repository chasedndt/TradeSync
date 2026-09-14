"""What a horizon chart draws: a window of candles, every feature's overlay, and the record's cone forward.

The cone spreads the percentiles of past moves over the horizon from bars in
the same trend and momentum state as today (falling back to the trend state
alone, then to all history, whichever the outlook used), widening with the
square root of time from the last close. It shows the range the record spans,
not a forecast.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from .horizon_bars import Bars
from .horizon_features import FEATURES
from .horizon_spec import Horizon

# Candles shown per horizon: two days of 15-minute bars for one hour ahead up to two years of daily bars for six months.
WINDOW_BARS = {"1h": 192, "4h": 384, "8h": 240, "1d": 336, "3d": 120, "1w": 180, "2w": 270, "1m": 365, "3m": 548, "6m": 730}
CONE = (("p10_pct", "10th percentile"), ("p25_pct", "25th percentile"), ("median_pct", "median"),
        ("p75_pct", "75th percentile"), ("p90_pct", "90th percentile"))


def cone_record(read: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    record = read.get("record") or {}
    for basis in (read.get("lean_basis") or "same_state", "same_trend", "all_history"):
        stats = record.get(basis) or {}
        if stats.get("median_pct") is not None:
            return basis, stats
    return "none", {}


def projection(bars: Bars, h: Horizon, read: Mapping[str, Any]) -> dict[str, Any]:
    basis, stats = cone_record(read)
    if not stats or not len(bars):
        return {"basis": basis, "lines": []}
    last_time, last_close = bars.times[-1], bars.closes[-1]
    step = max(1, h.steps // 40)
    ks = list(range(0, h.steps + 1, step))
    if ks[-1] != h.steps:
        ks.append(h.steps)
    lines = []
    for field, label in CONE:
        q = float(stats[field]) / 100
        points = [[last_time + k * h.bar_seconds, round(last_close * (1 + q * math.sqrt(k / h.steps)), 8)] for k in ks]
        lines.append({"quantile": field, "label": label, "points": points})
    return {
        "basis": basis, "windows": stats.get("days"), "independent_windows": stats.get("independent_windows"),
        "end_time": last_time + h.steps * h.bar_seconds, "lines": lines,
        "note": f"Past {h.adjective} moves from {basis.replace('_', ' ')}, spread from the last close; a record, not a forecast.",
    }


def chart_payload(bars: Bars, h: Horizon, read: Mapping[str, Any]) -> dict[str, Any]:
    start = max(0, len(bars) - WINDOW_BARS.get(h.key, 365))
    candles = [{"time": bars.times[i], "open": bars.opens[i], "high": bars.highs[i], "low": bars.lows[i],
                "close": bars.closes[i], "volume": bars.volumes[i]} for i in range(start, len(bars))]
    return {
        "horizon": h.key,
        "interval": h.interval,
        "candles": candles,
        "overlays": {f.key: f.overlays(bars, h, start) for f in FEATURES},
        "projection": projection(bars, h, read),
    }
