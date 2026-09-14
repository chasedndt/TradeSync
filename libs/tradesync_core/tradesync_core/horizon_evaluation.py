"""Every horizon feature at every horizon: today's reading, the record behind it, its earned weight, and a tally.

For each feature the record asks what followed past bars in the same state as
today over the same horizon (share ending higher, median, bands, independent
windows). Each feature also carries the weight it earned out of sample
(``horizon_weights``): the earned weights combine today's leans into one
reading per horizon, and a feature that earned nothing adds nothing.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from .horizon_bars import Bars
from .horizon_features import FEATURES, HorizonFeature
from .horizon_outlook import MIN_HISTORY_BARS, lean_of
from .horizon_spec import HORIZONS, INTERVAL_SECONDS, Horizon
from .horizon_stats import forward_returns, summarize
from .horizon_weights import combined, held_out_skill, relative_lean, share_up


def feature_evaluation(bars: Bars, h: Horizon, feature: HorizonFeature, forward: list[float | None],
                       base_share: float | None) -> dict[str, Any]:
    reading = feature.read(bars, h)
    states = feature.states(bars, h)
    record = summarize([], [], h.steps)
    if reading.state is not None:
        indices = [t for t in range(len(bars)) if forward[t] is not None and states[t] == reading.state]
        record = summarize([forward[t] for t in indices], indices, h.steps)
    skill = held_out_skill(states, forward, h.steps)
    current = relative_lean(record, base_share) if reading.state is not None else 0
    return {
        "key": feature.key, "label": feature.label, "kind": feature.kind, "measures": feature.measures,
        "state": reading.state, "lean": reading.lean, "value": reading.value, "text": reading.text,
        "record": record, "record_lean": lean_of(record) if reading.state is not None else "unavailable",
        "held_out": skill, "weight": skill["weight"], "current_lean": current,
        "contribution": round(float(skill["weight"]) * current, 3),
    }


def _names(features: list[dict[str, Any]]) -> str:
    labels = [f["label"] for f in features]
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


def tally_sentence(h: Horizon, features: list[dict[str, Any]]) -> str:
    groups = {lean: [f for f in features if f["record_lean"] == lean] for lean in ("up", "down", "mixed", "too_few", "unavailable")}
    parts = []
    if groups["up"]:
        parts.append(f"leans higher for {_names(groups['up'])}")
    if groups["down"]:
        parts.append(f"leans lower for {_names(groups['down'])}")
    if groups["mixed"]:
        parts.append(f"shows no consistent direction for {_names(groups['mixed'])}")
    thin = groups["too_few"] + groups["unavailable"]
    if thin:
        parts.append(f"is too thin to judge for {_names(thin)}")
    return f"Over {h.label}, the record behind today's reading " + "; ".join(parts) + "." if parts else f"No feature could be read over {h.label}."


def evaluate_horizon(bars: Bars, h: Horizon) -> dict[str, Any]:
    forward = forward_returns(bars.closes, h.steps, last_complete=not bars.last_partial)
    base_share = share_up(forward, range(len(forward)))
    features = [feature_evaluation(bars, h, f, forward, base_share) for f in FEATURES]
    counts = Counter(f["record_lean"] for f in features)
    return {
        "horizon": h.key,
        "features": features,
        "record_tally": {k: counts.get(k, 0) for k in ("up", "down", "mixed", "too_few", "unavailable")},
        "summary": tally_sentence(h, features),
        "base_share_up": round(base_share, 3) if base_share is not None else None,
        "combined": combined(features, h.label),
    }


def _by_interval(bars: Bars | Mapping[str, Bars]) -> Mapping[str, Bars]:
    if isinstance(bars, Bars):
        interval = next((iv for iv, s in INTERVAL_SECONDS.items() if s == bars.bar_seconds), "1d")
        return {interval: bars}
    return bars


def evaluate_all(bars: Bars | Mapping[str, Bars], horizons: tuple[Horizon, ...] = HORIZONS) -> dict[str, dict[str, Any]]:
    by_interval = _by_interval(bars)
    out: dict[str, dict[str, Any]] = {}
    for h in horizons:
        series_bars = by_interval.get(h.interval)
        if series_bars is not None and len(series_bars) >= MIN_HISTORY_BARS:
            out[h.key] = evaluate_horizon(series_bars, h)
    return out
