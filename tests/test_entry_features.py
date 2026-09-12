"""An entry reading is the newest sample before entry, within the feature's own tolerance."""

from __future__ import annotations

import pytest

from tradesync_core.entry_features import (
    candidate_features,
    reading_at_entry,
    tolerance_ms,
)

ENTRY = 1_000_000_000


def pt(ts: int, value: float) -> dict:
    return {"ts": ts, "value": value}


def test_newest_sample_before_entry_wins_regardless_of_order() -> None:
    points = [pt(ENTRY - 30_000, 1.0), pt(ENTRY - 5_000, 2.0), pt(ENTRY - 60_000, 3.0)]
    reading = reading_at_entry("f", points, ENTRY, max_age_ms=60_000)
    assert reading.value == 2.0 and reading.age_ms == 5_000 and reading.present


def test_a_sample_after_entry_is_hindsight_and_never_used() -> None:
    points = [pt(ENTRY + 1, 99.0), pt(ENTRY - 10_000, 1.0)]
    assert reading_at_entry("f", points, ENTRY, 60_000).value == 1.0
    only_after = reading_at_entry("f", [pt(ENTRY + 1, 99.0)], ENTRY, 60_000)
    assert not only_after.present and "before entry" in only_after.reason


def test_a_sample_at_entry_counts() -> None:
    assert reading_at_entry("f", [pt(ENTRY, 4.0)], ENTRY, 1).value == 4.0


def test_a_stale_sample_is_reported_absent_with_its_age_not_carried_forward() -> None:
    reading = reading_at_entry("f", [pt(ENTRY - 120_001, 1.0)], ENTRY, max_age_ms=120_000)
    assert reading.value is None
    assert reading.age_ms == 120_001 and reading.observed_at_ms == ENTRY - 120_001
    assert "tolerance 120000" in reading.reason


def test_malformed_points_are_skipped_not_fatal() -> None:
    points = [{"ts": "x", "value": 1}, {"ts": ENTRY, "value": None}, {"ts": True, "value": 1}, pt(ENTRY - 1, 7.0)]
    assert reading_at_entry("f", points, ENTRY, 10).value == 7.0


def test_tolerance_is_one_sampling_bucket_plus_the_freshness_window() -> None:
    assert tolerance_ms({"fresh_after_ms": 1_800_000, "sampling_interval_ms": 900_000}) == 2_700_000
    assert tolerance_ms({"fresh_after_ms": 15_000, "sampling_interval_ms": 60_000}) == 75_000
    assert tolerance_ms({"sampling_interval_ms": 60_000}) == 60_000
    with pytest.raises(ValueError):
        tolerance_ms({"fresh_after_ms": 0})


def test_candidates_are_implemented_directional_features_including_scoring_ones() -> None:
    catalog = {
        "scored": {"availability": "implemented", "signal_kind": "directional", "scoring_eligible": True},
        "context": {"availability": "implemented", "signal_kind": "directional", "scoring_eligible": False},
        "level": {"availability": "implemented", "signal_kind": "reference"},
        "planned": {"availability": "planned", "signal_kind": "directional"},
    }
    assert candidate_features(catalog) == ["scored", "context"]
