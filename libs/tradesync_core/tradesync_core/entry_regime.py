"""Classify the market regime from information that existed before a signal.

The first regime split labelled each hour "rising" or "falling" from the average
forward return of that hour's own outcomes — the very returns then being scored.
That is a hindsight label. It describes what happened well enough, but nobody
could have known it when a signal fired, and it quietly puts the outcome inside
the grouping that is meant to explain it. Codex's review of 2026-09-09 found
this, correctly.

This module labels a regime from the trailing price move *before* entry, using
only candles that had fully closed by the time the signal was recorded. A candle
that opened before the signal but closed after it contains prices from after the
decision, so it is excluded even though its open time is earlier.

The label is descriptive. Being in a "rising" regime says nothing about whether
the next move is up, and nothing here may reach a paper signal or a gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "entry_regime_v1"

# One hour of trailing price. Long enough that one candle's noise does not set
# the label, short enough to describe the market the signal actually fired into.
DEFAULT_LOOKBACK_MINUTES = 60

# Same tolerance the outcome measurement uses: a small shortfall at the window
# boundary is allowed, a real hole is not.
DEFAULT_COVERAGE_TOLERANCE = 0.90

# Zero keeps the split binary, comparable with the retired hindsight split. A
# positive band sets aside near-flat markets as their own regime.
DEFAULT_FLAT_BAND_PCT = 0.0

REGIMES = ("rising", "falling", "flat", "unknown")


class EntryRegimeError(ValueError):
    """Raised for malformed parameters, never for an unclassifiable window."""


@dataclass(frozen=True)
class EntryRegime:
    regime: str  # rising | falling | flat | unknown
    trailing_return_pct: float | None
    lookback_minutes: int
    candles_used: int
    window_start_s: int | None = None
    window_end_s: int | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "regime": self.regime,
            "trailing_return_pct": self.trailing_return_pct,
            "lookback_minutes": self.lookback_minutes,
            "candles_used": self.candles_used,
            "window_start_s": self.window_start_s,
            "window_end_s": self.window_end_s,
            "reason": self.reason,
            "basis": "candles fully closed before entry; no post-decision price",
        }


def _unknown(lookback_minutes: int, reason: str, used: int = 0) -> EntryRegime:
    return EntryRegime(
        regime="unknown",
        trailing_return_pct=None,
        lookback_minutes=lookback_minutes,
        candles_used=used,
        reason=reason,
    )


def classify_entry_regime(
    candles: Sequence[Mapping[str, Any]],
    opened_at_s: int,
    candle_interval_s: int,
    lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
    flat_band_pct: float = DEFAULT_FLAT_BAND_PCT,
    coverage_tolerance: float = DEFAULT_COVERAGE_TOLERANCE,
) -> EntryRegime:
    """Label the regime a signal at ``opened_at_s`` fired into.

    ``candles`` carry ``time`` as the candle *open* in UNIX seconds, plus
    ``open`` and ``close``. ``candle_interval_s`` is required rather than
    inferred: without it there is no way to tell whether a candle had closed.
    """
    if candle_interval_s <= 0:
        raise EntryRegimeError("candle_interval_s must be positive")
    if lookback_minutes <= 0:
        raise EntryRegimeError("lookback_minutes must be positive")
    if flat_band_pct < 0:
        raise EntryRegimeError("flat_band_pct cannot be negative")
    if not 0 < coverage_tolerance <= 1:
        raise EntryRegimeError("coverage_tolerance must be in (0, 1]")

    start_s = opened_at_s - lookback_minutes * 60
    closed = sorted(
        (
            c
            for c in candles
            if isinstance(c, Mapping)
            and isinstance(c.get("time"), int)
            and not isinstance(c.get("time"), bool)
            and c["time"] >= start_s
            # Closed before the decision, not merely opened before it.
            and c["time"] + candle_interval_s <= opened_at_s
        ),
        key=lambda c: c["time"],
    )
    if not closed:
        return _unknown(lookback_minutes, "no candle closed inside the lookback before entry")

    # Both the span and the count must be nearly complete. The span alone would
    # accept two candles at either end of the window with a hole between them.
    lookback_s = lookback_minutes * 60
    covered_s = closed[-1]["time"] + candle_interval_s - closed[0]["time"]
    expected = lookback_s / candle_interval_s
    if covered_s < lookback_s * coverage_tolerance or len(closed) < expected * coverage_tolerance:
        return _unknown(
            lookback_minutes,
            f"{len(closed)} closed candles covering {covered_s}s of a {lookback_s}s "
            "lookback; the gap is reported rather than interpolated",
            used=len(closed),
        )

    try:
        first_open = float(closed[0]["open"])
        last_close = float(closed[-1]["close"])
    except (KeyError, TypeError, ValueError):
        return _unknown(lookback_minutes, "candle prices were missing or malformed", len(closed))
    if first_open <= 0:
        return _unknown(lookback_minutes, "first open price was not positive", len(closed))

    trailing = (last_close - first_open) / first_open * 100.0
    if trailing > flat_band_pct:
        regime = "rising"
    elif trailing < -flat_band_pct:
        regime = "falling"
    else:
        regime = "flat"

    return EntryRegime(
        regime=regime,
        trailing_return_pct=round(trailing, 6),
        lookback_minutes=lookback_minutes,
        candles_used=len(closed),
        window_start_s=closed[0]["time"],
        window_end_s=closed[-1]["time"] + candle_interval_s,
    )
