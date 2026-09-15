"""The one-hour mark-price return: comparator, anchor selection and derivation.

Moved out of ``feature_extractor`` so the extractor keeps one job: reading
catalog measurements off a snapshot.
"""

from __future__ import annotations

import math
import os
from typing import Any, Mapping, Sequence

from .snapshot_values import finite as _finite, value_at as _path


# ``hl_return_1h_pct`` is the only price/volatility feature the regime rulebook
# admits for a generic directional score, so its comparator is defined here
# rather than inferred at call sites. The catalog comparator is "mark price at
# or immediately before t minus 1 hour"; a gap wider than the tolerance below
# means the anchor is no longer a one-hour comparator and no value is emitted.
RETURN_1H_WINDOW_MS = 60 * 60 * 1000
RETURN_1H_ANCHOR_TOLERANCE_MS = int(
    os.getenv("RETURN_1H_ANCHOR_TOLERANCE_MS", str(5 * 60 * 1000))
)


def select_return_anchor(
    history: Sequence[Mapping[str, Any]],
    observed_at_ms: int,
    window_ms: int = RETURN_1H_WINDOW_MS,
    tolerance_ms: int = RETURN_1H_ANCHOR_TOLERANCE_MS,
) -> dict[str, Any] | None:
    """Return the newest history point at or before ``observed_at_ms - window_ms``.

    Selecting at-or-before rather than nearest keeps the comparator from
    reaching forward into a shorter interval when sampling is irregular. The
    tolerance rejects an anchor stranded on the far side of a data gap.
    """

    target_ms = observed_at_ms - window_ms
    earliest_ms = target_ms - tolerance_ms
    anchor: dict[str, Any] | None = None
    for point in history:
        if not isinstance(point, Mapping):
            continue
        ts = point.get("ts")
        value = _finite(point.get("value"))
        if not isinstance(ts, int) or isinstance(ts, bool) or value is None:
            continue
        if ts > target_ms or ts < earliest_ms:
            continue
        if anchor is None or ts > anchor["ts"]:
            anchor = {"ts": ts, "value": value}
    return anchor


def derive_return_1h_pct(
    snapshot: Mapping[str, Any],
    mark_price_history: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Derive the one-hour mark-price return as a percent change.

    Returns ``None`` when the snapshot is not usable or no admissible anchor
    exists, so the price/volatility block loses coverage instead of scoring a
    fabricated zero.
    """

    venue = str(snapshot.get("venue") or "")
    symbol = str(snapshot.get("symbol") or "")
    observed_at_ms = int(snapshot.get("ts") or 0)
    if venue != "hyperliquid" or not symbol or observed_at_ms <= 0:
        return None

    current = _finite(_path(snapshot, "price", "mark_price_usd"))
    if current is None:
        return None

    anchor = select_return_anchor(mark_price_history, observed_at_ms)
    if anchor is None or anchor["value"] <= 0:
        return None

    value = (current - anchor["value"]) / anchor["value"] * 100.0
    if not math.isfinite(value):
        return None

    return {
        "feature_id": "hl_return_1h_pct",
        "venue": venue,
        "symbol": symbol,
        "timeframe": "snapshot",
        "observed_at_ms": observed_at_ms,
        "value": value,
        "source_event_id": (
            f"return1h:{venue}:{symbol}:{anchor['ts']}:{observed_at_ms}"
        ),
        "comparator": {
            "anchor_ts_ms": anchor["ts"],
            "anchor_value": anchor["value"],
            "anchor_lag_ms": observed_at_ms - anchor["ts"],
            "current_value": current,
        },
    }


def attach_derived_features(
    snapshot: dict[str, Any],
    mark_price_history: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Write history-backed derivations onto the snapshot before it is stored.

    Deriving here rather than on every read keeps ``/features`` a stateless
    lookup. The regime engine fans out one history request per normalized
    feature, so an extra round trip on that first hop is paid by every one of
    them.
    """

    observation = derive_return_1h_pct(snapshot, mark_price_history)
    if observation is None:
        return snapshot
    derived = snapshot.setdefault("derived", {})
    derived["return_1h_pct"] = {
        "value": observation["value"],
        "comparator": observation["comparator"],
        "source_event_id": observation["source_event_id"],
    }
    return snapshot
