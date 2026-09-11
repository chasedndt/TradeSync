"""Hyperliquid candle retrieval for the Market Canvas.

Candles are a *display and annotation* surface. They are deliberately not part
of the feature catalog: nothing here can reach the regime rulebook or create a
paper signal. Keeping that boundary explicit matters, because a chart is the
easiest place in the product to accidentally invent authority.

The venue is the only source. No candle is ever synthesised from stored
snapshots, and a gap in venue history stays a gap.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

# Intervals Hyperliquid accepts, mapped to their millisecond duration so a
# lookback can be expressed in candles rather than in raw epoch arithmetic.
SUPPORTED_INTERVALS: dict[str, int] = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}

DEFAULT_INTERVAL = "15m"
DEFAULT_LIMIT = 300
MAX_LIMIT = 1000


class CandleRequestError(ValueError):
    """Raised for a malformed request, never for an empty venue response."""


def resolve_window(
    interval: str,
    limit: int,
    now_ms: int | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> tuple[str, int, int, int]:
    """Return (interval, limit, start_ms, end_ms) for a candle request.

    Without ``start_ms``/``end_ms`` the window is the most recent ``limit``
    candles. With them it is that explicit range, so a measurement that needs
    candles from two days ago can ask for exactly those. The outcome job used
    to have no way to say that: it could only ask for "the last N", and any
    window older than N candles was reported as having no candles at all.
    """

    if interval not in SUPPORTED_INTERVALS:
        raise CandleRequestError(
            f"unsupported interval '{interval}'; expected one of "
            + ", ".join(SUPPORTED_INTERVALS)
        )
    if limit <= 0:
        raise CandleRequestError("limit must be positive")
    if (start_ms is None) != (end_ms is None):
        raise CandleRequestError("start_ms and end_ms must be given together")

    step_ms = SUPPORTED_INTERVALS[interval]
    if start_ms is not None and end_ms is not None:
        if end_ms <= start_ms:
            raise CandleRequestError("end_ms must be after start_ms")
        span = (end_ms - start_ms + step_ms - 1) // step_ms
        if span > MAX_LIMIT:
            raise CandleRequestError(
                f"range covers {span} {interval} candles; at most {MAX_LIMIT} "
                "per request, so split the range"
            )
        return interval, span, start_ms, end_ms

    bounded = min(limit, MAX_LIMIT)
    end = now_ms if now_ms is not None else int(time.time() * 1000)
    return interval, bounded, end - step_ms * bounded, end


def _number(value: Any) -> float | None:
    """Hyperliquid returns OHLCV as strings; refuse anything unparseable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and parsed not in (float("inf"), float("-inf")) else None


def normalize_candles(raw: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Convert the venue payload into the chart contract.

    Seconds, not milliseconds: the charting library expects UNIX seconds, and
    converting once here keeps that detail out of the UI.
    """

    candles: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        open_ms = entry.get("t")
        if not isinstance(open_ms, int) or isinstance(open_ms, bool):
            continue
        values = {key: _number(entry.get(key)) for key in ("o", "h", "l", "c", "v")}
        if any(values[key] is None for key in ("o", "h", "l", "c")):
            continue
        candles.append(
            {
                "time": open_ms // 1000,
                "open": values["o"],
                "high": values["h"],
                "low": values["l"],
                "close": values["c"],
                "volume": values["v"] or 0.0,
            }
        )

    # The venue does not guarantee ordering, and a chart with unsorted or
    # duplicated timestamps renders as a scribble rather than an error.
    candles.sort(key=lambda item: item["time"])
    deduped: list[dict[str, Any]] = []
    for candle in candles:
        if deduped and deduped[-1]["time"] == candle["time"]:
            deduped[-1] = candle
        else:
            deduped.append(candle)
    return deduped
