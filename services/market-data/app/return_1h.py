"""The one-hour mark-price return: comparator, anchor selection and derivation.

Moved out of ``feature_extractor`` so the extractor keeps one job: reading
catalog measurements off a snapshot.
"""

from __future__ import annotations

import math
import os
from typing import Any, Mapping, Sequence

from .candle_anchor import ANCHOR_SOURCE as CANDLE_SOURCE, CANDLE_ANCHORS, CandleAnchors
from .snapshot_values import finite as _finite, value_at as _path


# ``hl_return_1h_pct`` is the only price/volatility feature the regime rulebook
# admits for a generic directional score, so its comparator is defined here
# rather than inferred at call sites. The catalog comparator is "mark price at
# or immediately before t minus 1 hour"; a gap wider than the tolerance below
# means the anchor is no longer a one-hour comparator and no value is emitted.
# Across a hole in TradeSync's own mark-price series the venue's 1-minute candle
# close at or before the same target stands in (``candle_anchor``), recorded as
# ``anchor_source``; the window and tolerance never widen.
RETURN_1H_WINDOW_MS = 60 * 60 * 1000
RETURN_1H_ANCHOR_TOLERANCE_MS = int(
    os.getenv("RETURN_1H_ANCHOR_TOLERANCE_MS", str(5 * 60 * 1000))
)
OBSERVED_SOURCE = "observed_mark_price"


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
    candle_anchors: CandleAnchors | None = None,
) -> dict[str, Any] | None:
    """Derive the one-hour mark-price return as a percent change.

    The anchor is the newest observed mark price at or before t minus one hour,
    within the tolerance. When none is admissible and ``candle_anchors`` is
    given, a held venue candle close at or before the same target, within the
    same tolerance, stands in and the comparator says so; when no candle is
    held yet, one fetch is scheduled so a later snapshot can find it.

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
    source = OBSERVED_SOURCE
    if anchor is None and candle_anchors is not None:
        target_ms = observed_at_ms - RETURN_1H_WINDOW_MS
        anchor = candle_anchors.anchor(symbol, target_ms, RETURN_1H_ANCHOR_TOLERANCE_MS)
        if anchor is None:
            candle_anchors.request(symbol, target_ms, RETURN_1H_ANCHOR_TOLERANCE_MS)
            return None
        source = CANDLE_SOURCE
    if anchor is None or anchor["value"] <= 0:
        return None

    value = (current - anchor["value"]) / anchor["value"] * 100.0
    if not math.isfinite(value):
        return None

    comparator = {
        "anchor_ts_ms": anchor["ts"],
        "anchor_value": anchor["value"],
        "anchor_lag_ms": observed_at_ms - anchor["ts"],
        "current_value": current,
        "anchor_source": source,
    }
    event_prefix = "return1h"
    if source == CANDLE_SOURCE:
        comparator["anchor_candle_open_ms"] = anchor["candle_open_ms"]
        comparator["anchor_candle_interval"] = anchor["candle_interval"]
        event_prefix = "return1h-candle"

    return {
        "feature_id": "hl_return_1h_pct",
        "venue": venue,
        "symbol": symbol,
        "timeframe": "snapshot",
        "observed_at_ms": observed_at_ms,
        "value": value,
        "source_event_id": (
            f"{event_prefix}:{venue}:{symbol}:{anchor['ts']}:{observed_at_ms}"
        ),
        "comparator": comparator,
    }


def attach_derived_features(
    snapshot: dict[str, Any],
    mark_price_history: Sequence[Mapping[str, Any]],
    candle_anchors: CandleAnchors | None = CANDLE_ANCHORS,
) -> dict[str, Any]:
    """Write history-backed derivations onto the snapshot before it is stored.

    Deriving here rather than on every read keeps ``/features`` a stateless
    lookup. The regime engine fans out one history request per normalized
    feature, so an extra round trip on that first hop is paid by every one of
    them. The service uses the shared venue candle cache for gaps in the
    mark-price series; ``None`` keeps the derivation to observed marks only.
    """

    observation = derive_return_1h_pct(snapshot, mark_price_history, candle_anchors)
    if observation is None:
        return snapshot
    derived = snapshot.setdefault("derived", {})
    derived["return_1h_pct"] = {
        "value": observation["value"],
        "comparator": observation["comparator"],
        "source_event_id": observation["source_event_id"],
    }
    return snapshot
