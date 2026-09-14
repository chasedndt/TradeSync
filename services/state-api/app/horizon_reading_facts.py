"""The measured facts a Hermes reading of one band is drafted from, as plain lines.

Numbers only, named exactly as the page names them, so every feature name in
the reading links back to its row: trend, momentum, the record behind them,
the ordinary range, the levels, and every feature with its record and the
weight it earned out of sample, plus the weighted reading per horizon.
"""

from __future__ import annotations

from typing import Any, Mapping

from tradesync_core.horizon_features.base import fmt_price
from tradesync_core.horizon_spec import BANDS, HORIZONS, INTERVAL_WORDS

FEATURE_NAMES = ("Trend", "Momentum", "Volatility", "Range position", "Drawdown", "RSI", "Participation", "Funding", "Premium")


def record_line(stats: Mapping[str, Any] | None) -> str:
    if not stats or not stats.get("days"):
        return "no comparable bars"
    return (f"{stats['days']} comparable bars, {stats['independent_windows']} non-overlapping windows (not proof of independence), "
            f"higher {round(float(stats['share_up']) * 100)}% of the time, median {float(stats['median_pct']):+.2f}%, "
            f"middle half {float(stats['p25_pct']):+.2f}% to {float(stats['p75_pct']):+.2f}%")


def weight_line(feature: Mapping[str, Any]) -> str:
    held = feature.get("held_out") or {}
    if float(feature.get("weight") or 0) <= 0:
        reason = {"measured": "no skill above chance on the newest 30% of history",
                  "too_few_test_windows": "too few test windows", "no_leaning_state": "no state leaned in the older 70%",
                  "too_little_history": "too little history"}.get(held.get("status"), "not measured")
        return f"weight 0 ({reason})"
    return (f"weight {float(feature['weight']):.2f} (hit rate {float(held['hit_rate']) * 100:.0f}% against "
            f"{float(held['chance']) * 100:.0f}% by chance over {held['test_windows']} test windows)")


def facts(symbol: str, scope: str, outlook: Mapping[str, Any], evaluation: Mapping[str, Any]) -> str:
    lines = [f"Market {symbol}; last close {fmt_price(float(outlook['last_close']))}; band {BANDS[scope]}."]
    for interval, history in (outlook.get("history") or {}).items():
        lines.append(f"{INTERVAL_WORDS.get(interval, interval)} candles {history.get('from')} to {history.get('to')} ({history.get('bars')} bars).")
    reads = {r["key"]: r for r in outlook.get("horizons") or []}
    for h in (h for h in HORIZONS if h.band == scope):
        read = reads.get(h.key) or {}
        if not read.get("available"):
            lines.append(f"- {h.label}: not measurable ({read.get('reason')}).")
            continue
        trend, momentum, implied = read["trend"], read["momentum"], read.get("implied_range") or {}
        basis = read.get("lean_basis") or "same_state"
        line = (f"- {h.label} on {INTERVAL_WORDS[h.interval]} bars: close {trend['state'].replace('_', ' ')} its "
                f"{trend['ma_label']} average {fmt_price(float(trend['ma']))}; momentum {float(momentum['change_pct']):+.2f}% "
                f"over the last {h.label}; record ({basis.replace('_', ' ')}): {record_line(read['record'][basis])}; "
                f"lean {read['lean'].replace('_', ' ')}")
        if implied:
            line += f"; one ordinary move spans {fmt_price(float(implied['low']))} to {fmt_price(float(implied['high']))}"
        lines.append(line + f"; the trend state flips at {fmt_price(float(read['levels']['trend_flips_at']))}.")
        horizon_eval = evaluation.get(h.key) or {}
        if horizon_eval.get("combined"):
            lines.append(f"  Weighted reading: {horizon_eval['combined']['sentence']}")
        for feature in horizon_eval.get("features") or []:
            lines.append(f"  - {feature['label']}: {feature['text']} Record: {record_line(feature['record'])}; "
                         f"lean {str(feature['record_lean']).replace('_', ' ')}; {weight_line(feature)}.")
    return "\n".join(lines)
