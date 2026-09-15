"""Signed readings at entry: recorded values, store samples, z-scores, changes and price products.

Every rule mirrors a live one. Entry values from the store use
``tradesync_core.entry_features.reading_at_entry`` with the feature's own tolerance, as the
outcome job does; z-scores use ``tradesync_core.feature_statistics.z_score_statistics``, the
scorer's code, over the samples strictly before the entry sample. No sample observed after
entry is ever read.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from tradesync_core.entry_features import reading_at_entry, tolerance_ms
from tradesync_core.feature_catalog import FeatureValidationError
from tradesync_core.feature_statistics import z_score_statistics

from .candidates import CHANGE_4H, CHANGE_4H_WITH_PRICE, PRICE_FEATURE, RAW, RECORDED_AT_ENTRY, WITH_PRICE, Z, Reading

CHANGE_WINDOW_MS = 4 * 3_600_000
CHANGE_MIN_SPAN_MS = 3 * 3_600_000 + 30 * 60_000


def proxy_points(pairs: Sequence[Sequence[float]]) -> list[dict[str, float]]:
    """State-API ``[seconds, value]`` pairs as store points, each at the last millisecond of its second.

    A whole second cannot say when inside it the sample was taken; the latest moment is the only
    choice that can never place a sample taken after entry before it.
    """
    return sorted(({"ts": int(sec) * 1000 + 999, "value": float(value)} for sec, value in pairs), key=lambda p: p["ts"])


@dataclass
class Series:
    """One feature's stored samples for one market, oldest first."""

    points: list[dict[str, float]]
    times: list[int] = field(init=False)

    def __post_init__(self) -> None:
        self.points = sorted(self.points, key=lambda p: p["ts"])
        self.times = [int(p["ts"]) for p in self.points]

    def at_entry(self, feature_id: str, entry_ms: int, spec: Mapping[str, Any]) -> tuple[int, float] | None:
        """The outcome job's entry rule, over the only samples that can matter."""
        tolerance = tolerance_ms(spec)
        low = bisect.bisect_left(self.times, entry_ms - tolerance)
        high = bisect.bisect_right(self.times, entry_ms)
        reading = reading_at_entry(feature_id, self.points[low:high], entry_ms, tolerance)
        return (int(reading.observed_at_ms), float(reading.value)) if reading.present else None


def z_reading(series: Series, current_ts: int, current_value: float, method: str, lookback: int, minimum: int) -> float | None:
    """The scorer's z-score: the last ``lookback`` samples before the current one, at least ``minimum``."""
    end = bisect.bisect_left(series.times, current_ts)
    selected = [p["value"] for p in series.points[max(0, end - lookback):end]]
    if len(selected) < minimum:
        return None
    try:
        return float(z_score_statistics(selected, current_value, method)["z_score"])
    except FeatureValidationError:
        return None


def change_4h(series: Series, current_ts: int, current_value: float) -> float | None:
    """Percent change from the earliest sample in [t-4h, t], which must reach back at least 3h30m."""
    index = bisect.bisect_left(series.times, current_ts - CHANGE_WINDOW_MS)
    if index >= len(series.times) or series.times[index] >= current_ts:
        return None
    base_ts, base = series.times[index], series.points[index]["value"]
    if base_ts > current_ts - CHANGE_MIN_SPAN_MS or base <= 0:
        return None
    return (current_value - base) / base * 100.0


@dataclass(frozen=True)
class Entry:
    opportunity_id: str
    symbol: str
    entry_ms: int


def signed_readings(
    entry: Entry,
    readings: Sequence[Reading],
    recorded: Mapping[str, tuple[int, float]],
    series: Mapping[str, Series],
    specs: Mapping[str, Mapping[str, Any]],
) -> dict[str, float]:
    """``reading_id -> signed value`` for one entry. A reading that cannot be formed is absent, never zero."""
    values: dict[str, tuple[int, float] | None] = {}

    def entry_value(feature_id: str) -> tuple[int, float] | None:
        if feature_id not in values:
            if feature_id in RECORDED_AT_ENTRY:
                values[feature_id] = recorded.get(feature_id)
            else:
                stored = series.get(feature_id)
                values[feature_id] = stored.at_entry(feature_id, entry.entry_ms, specs[feature_id]) if stored else None
        return values[feature_id]

    out: dict[str, float] = {}
    price = recorded.get(PRICE_FEATURE)
    for reading in readings:
        current = entry_value(reading.feature_id)
        if current is None:
            continue
        ts, value = current
        stored = series.get(reading.feature_id)
        signed: float | None = None
        if reading.kind == RAW:
            signed = value
        elif reading.kind == Z and stored is not None:
            signed = z_reading(stored, ts, value, reading.z_method, reading.z_lookback, reading.z_minimum)
        elif reading.kind == CHANGE_4H and stored is not None:
            signed = change_4h(stored, ts, value)
        elif reading.kind == WITH_PRICE and price is not None:
            signed = value * price[1]
        elif reading.kind == CHANGE_4H_WITH_PRICE and price is not None and stored is not None:
            change = change_4h(stored, ts, value)
            signed = change * price[1] if change is not None else None
        if signed is not None:
            out[reading.reading_id] = signed
    return out
