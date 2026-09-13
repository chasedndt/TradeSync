"""Every horizon feature at every horizon: today's reading, the record behind it, and a tally.

For each feature the record asks what followed past days in the same state as
today over the same horizon (share ending higher, median, bands, independent
windows). The tally counts which way those records lean. It is a count of
evidence, not a vote with weights: none of these features has measured skill
at these horizons, so none is weighted above another.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .horizon_features import FEATURES, Bars, HorizonFeature
from .horizon_outlook import HORIZONS, Horizon, lean_of
from .horizon_stats import forward_returns, summarize


def feature_evaluation(bars: Bars, h: Horizon, feature: HorizonFeature, forward: list[float | None]) -> dict[str, Any]:
    reading = feature.read(bars, h)
    record = summarize([], [], h.days)
    if reading.state is not None:
        states = feature.states(bars, h)
        indices = [t for t in range(len(bars)) if forward[t] is not None and states[t] == reading.state]
        record = summarize([forward[t] for t in indices], indices, h.days)
    return {
        "key": feature.key, "label": feature.label, "kind": feature.kind, "measures": feature.measures,
        "state": reading.state, "lean": reading.lean, "value": reading.value, "text": reading.text,
        "record": record, "record_lean": lean_of(record) if reading.state is not None else "unavailable",
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
    forward = forward_returns(bars.closes, h.days)
    features = [feature_evaluation(bars, h, f, forward) for f in FEATURES]
    counts = Counter(f["record_lean"] for f in features)
    return {
        "horizon": h.key,
        "features": features,
        "record_tally": {k: counts.get(k, 0) for k in ("up", "down", "mixed", "too_few", "unavailable")},
        "summary": tally_sentence(h, features),
    }


def evaluate_all(bars: Bars) -> dict[str, dict[str, Any]]:
    return {h.key: evaluate_horizon(bars, h) for h in HORIZONS}
