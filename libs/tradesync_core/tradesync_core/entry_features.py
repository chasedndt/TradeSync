"""Read what a feature said at the moment an opportunity fired.

The live feature store (``market-data`` ``/feature-history``) keeps a rolling
seven days of samples per feature and symbol. Given that series and an entry
time, this picks the newest sample that had already been observed when the
signal fired and was still within the feature's own freshness tolerance.

Nothing here interpolates. A sample observed after entry is hindsight and is
never used; a sample older than the tolerance is stale and is reported as
absent rather than carried forward, because "the store had nothing current"
is a fact the evidence cards need to count.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "entry_feature_v1"
# Features that can be tested as a directional input. Scoring ones are
# included on purpose: an admitted weight should face the same measurement as
# a candidate, or the card cannot say whether the admission was justified.
CANDIDATE_SIGNAL_KIND = "directional"


@dataclass(frozen=True)
class EntryReading:
    feature_id: str
    value: float | None
    observed_at_ms: int | None
    age_ms: int | None
    reason: str

    @property
    def present(self) -> bool:
        return self.value is not None


def candidate_features(catalog_features: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Implemented directional features, in catalog order."""
    return [
        feature_id
        for feature_id, spec in catalog_features.items()
        if spec.get("availability") == "implemented"
        and spec.get("signal_kind") == CANDIDATE_SIGNAL_KIND
    ]


def _positive_number(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return int(value)


def tolerance_ms(spec: Mapping[str, Any]) -> int:
    """How old a sample may be at entry and still count as the entry reading.

    The store keeps one sample per sampling bucket, so the newest sample can
    legitimately be a whole ``sampling_interval_ms`` old at entry. On top of
    that the catalog's ``fresh_after_ms`` is the feature's own statement of
    how long a reading stays current once taken. The tolerance is the sum:
    the latest bucket's sample, taken while still fresh. A one-minute feature
    with a 15 s freshness tolerates 75 s; news tone, sampled every fifteen
    minutes and fresh for thirty, tolerates forty-five.
    """
    fresh = _positive_number(spec.get("fresh_after_ms"))
    sampling = _positive_number(spec.get("sampling_interval_ms"))
    if fresh is None and sampling is None:
        raise ValueError("feature spec has neither fresh_after_ms nor sampling_interval_ms")
    return (fresh or 0) + (sampling or 0)


def reading_at_entry(
    feature_id: str,
    points: Sequence[Mapping[str, Any]],
    opened_at_ms: int,
    max_age_ms: int,
) -> EntryReading:
    """The newest sample at or before ``opened_at_ms`` within ``max_age_ms``.

    ``points`` are ``{"ts": ms, "value": float}`` in any order. Samples after
    entry are ignored outright.
    """
    best_ts: int | None = None
    best_value: float | None = None
    for point in points:
        ts, value = point.get("ts"), point.get("value")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        ts = int(ts)
        if ts > opened_at_ms:
            continue
        if best_ts is None or ts > best_ts:
            best_ts, best_value = ts, float(value)

    if best_ts is None:
        return EntryReading(feature_id, None, None, None, "no sample observed before entry")
    age = opened_at_ms - best_ts
    if age > max_age_ms:
        return EntryReading(
            feature_id,
            None,
            best_ts,
            age,
            f"newest sample before entry was {age} ms old; tolerance {max_age_ms} ms",
        )
    return EntryReading(feature_id, best_value, best_ts, age, "")
