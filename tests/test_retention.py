"""Refusals may be summarised away, never quietly discounted."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradesync_core.retention import (
    DEFAULT_REFUSAL_RETENTION_DAYS,
    all_reason_codes,
    merge_rollup,
    primary_reason,
    retention_cutoff,
    rollup_refusals,
)


def row(day: int, symbol: str, *reasons: str, score=None, coverage=None):
    """A refusal row shaped as core-scorer actually writes one.

    ``rejection_reasons`` is a list of ``{code, detail, feature_id}``; several
    can be present on one verdict.
    """
    features: dict = {}
    if reasons:
        features["rejection_reasons"] = [
            {"code": code, "detail": "", "feature_id": ""} for code in reasons
        ]
    if score is not None:
        features["weighted_score"] = score
    if coverage is not None:
        features["data_coverage"] = coverage
    return {
        "created_at": datetime(2026, 9, day, 12, 0, tzinfo=timezone.utc),
        "symbol": symbol,
        "features": features,
    }


def test_the_cutoff_is_the_retention_window_back_from_now() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    assert retention_cutoff(7, now) == now - timedelta(days=7)
    assert retention_cutoff(now=now) == now - timedelta(
        days=DEFAULT_REFUSAL_RETENTION_DAYS
    )


def test_a_zero_day_window_is_refused() -> None:
    """It would delete a refusal in the same pass that wrote it.

    The dashboard would then have nothing left to explain the current state.
    """
    with pytest.raises(ValueError):
        retention_cutoff(0)
    with pytest.raises(ValueError):
        retention_cutoff(-1)


def test_refusals_group_by_day_symbol_and_reason() -> None:
    rolled = rollup_refusals(
        [
            row(1, "BTC-PERP", "coverage_below_floor"),
            row(1, "BTC-PERP", "coverage_below_floor"),
            row(1, "BTC-PERP", "score_below_band"),
            row(1, "ETH-PERP", "coverage_below_floor"),
            row(2, "BTC-PERP", "coverage_below_floor"),
        ]
    )
    assert [(r["symbol"], r["reason"], r["refusals"]) for r in rolled] == [
        ("BTC-PERP", "coverage_below_floor", 2),
        ("BTC-PERP", "score_below_band", 1),
        ("ETH-PERP", "coverage_below_floor", 1),
        ("BTC-PERP", "coverage_below_floor", 1),
    ]


def test_a_refusal_with_no_stated_reason_is_still_counted() -> None:
    """Dropping it would understate the denominator.

    That is the failure this rollup exists to prevent: every admission rate
    computed afterwards would be flattered by the rows that went missing.
    """
    rolled = rollup_refusals([row(1, "BTC-PERP"), row(1, "BTC-PERP")])
    assert len(rolled) == 1
    assert rolled[0]["reason"] == "unstated"
    assert rolled[0]["refusals"] == 2


def test_a_row_with_no_timestamp_cannot_be_placed_and_is_skipped() -> None:
    """There is no honest day to file it under; inventing one would be worse."""
    rolled = rollup_refusals(
        [{"symbol": "BTC-PERP", "features": {}}, row(1, "BTC", "x")]
    )
    assert len(rolled) == 1
    assert rolled[0]["symbol"] == "BTC"


def test_distributions_are_summarised_not_just_counted() -> None:
    rolled = rollup_refusals(
        [
            row(1, "BTC-PERP", "coverage_below_floor", score=-0.2, coverage=0.30),
            row(1, "BTC-PERP", "coverage_below_floor", score=0.4, coverage=0.50),
        ]
    )
    entry = rolled[0]
    assert entry["mean_score"] == pytest.approx(0.1)
    assert entry["mean_coverage"] == pytest.approx(0.4)
    assert entry["min_coverage"] == 0.30
    assert entry["max_coverage"] == 0.50
    assert entry["scored_rows"] == 2
    assert entry["covered_rows"] == 2


def test_an_absent_measure_is_null_rather_than_zero() -> None:
    """A mean of zero is a claim about the scores; an absent field is not."""
    entry = rollup_refusals([row(1, "BTC-PERP", "no_regime_evidence")])[0]
    assert entry["refusals"] == 1
    assert entry["mean_score"] is None
    assert entry["mean_coverage"] is None
    assert entry["scored_rows"] == 0
    assert entry["covered_rows"] == 0


def test_a_boolean_is_not_treated_as_a_number() -> None:
    """bool is an int in Python, and True would average as 1.0."""
    entry = rollup_refusals(
        [row(1, "BTC-PERP", "x", score=True), row(1, "BTC-PERP", "x", score=0.5)]
    )[0]
    assert entry["scored_rows"] == 1
    assert entry["mean_score"] == pytest.approx(0.5)


def test_a_second_pass_in_the_same_day_adds_rather_than_replaces() -> None:
    first = rollup_refusals(
        [row(1, "BTC-PERP", "coverage_below_floor", coverage=0.30)] * 1
    )[0]
    second = rollup_refusals(
        [row(1, "BTC-PERP", "coverage_below_floor", coverage=0.50)] * 1
    )[0]

    merged = merge_rollup(first, second)
    assert merged["refusals"] == 2
    assert merged["mean_coverage"] == pytest.approx(0.4)
    assert merged["min_coverage"] == 0.30
    assert merged["max_coverage"] == 0.50


def test_a_coverage_only_batch_still_merges_its_coverage() -> None:
    """The regression that a single shared count caused.

    These refusals carry a coverage but no score. Weighting the coverage mean by
    the *score* count made it zero on both sides, and the merged mean came back
    as None even though both batches had a real number.
    """
    first = rollup_refusals([row(1, "BTC-PERP", "r", coverage=0.30)])[0]
    second = rollup_refusals([row(1, "BTC-PERP", "r", coverage=0.50)])[0]
    assert first["scored_rows"] == 0 and first["covered_rows"] == 1

    merged = merge_rollup(first, second)
    assert merged["mean_coverage"] == pytest.approx(0.4)
    assert merged["mean_score"] is None


def test_means_recombine_weighted_by_how_many_rows_each_side_scored() -> None:
    """A 1-row batch must not pull a 99-row day's average halfway to itself."""
    existing = {
        "day": None,
        "symbol": "BTC-PERP",
        "reason": "x",
        "refusals": 99,
        "scored_rows": 99,
        "covered_rows": 99,
        "mean_coverage": 0.50,
        "min_coverage": 0.50,
        "max_coverage": 0.50,
        "mean_score": None,
    }
    incoming = {
        "day": None,
        "symbol": "BTC-PERP",
        "reason": "x",
        "refusals": 1,
        "scored_rows": 1,
        "covered_rows": 1,
        "mean_coverage": 1.0,
        "min_coverage": 1.0,
        "max_coverage": 1.0,
        "mean_score": None,
    }
    merged = merge_rollup(existing, incoming)
    # Naive averaging would give 0.75; the weighted answer is 0.505.
    assert merged["mean_coverage"] == pytest.approx(0.505)
    assert merged["refusals"] == 100


def test_merging_onto_nothing_returns_the_incoming_entry() -> None:
    incoming = rollup_refusals([row(1, "BTC-PERP", "x", coverage=0.2)])[0]
    assert merge_rollup(None, incoming) == incoming


def test_merging_a_scored_batch_onto_an_unscored_one_keeps_the_number() -> None:
    unscored = {
        "day": None, "symbol": "S", "reason": "r", "refusals": 3,
        "scored_rows": 0, "covered_rows": 0, "mean_coverage": None, "mean_score": None,
        "min_coverage": None, "max_coverage": None,
    }
    scored = {
        "day": None, "symbol": "S", "reason": "r", "refusals": 1,
        "scored_rows": 1, "covered_rows": 1, "mean_coverage": 0.4, "mean_score": 0.1,
        "min_coverage": 0.4, "max_coverage": 0.4,
    }
    merged = merge_rollup(unscored, scored)
    assert merged["refusals"] == 4
    assert merged["mean_coverage"] == pytest.approx(0.4)
    assert merged["min_coverage"] == 0.4


def test_a_multi_reason_refusal_is_counted_once_under_its_first_gate() -> None:
    """Otherwise the totals sum to more than the number of refusals.

    A verdict can fail the coverage floor and the direction band at once. Filing
    it under both would inflate every denominator computed from this table.
    """
    features = {
        "rejection_reasons": [
            {"code": "coverage_below_floor"},
            {"code": "score_inside_deadband"},
        ]
    }
    assert primary_reason(features) == "coverage_below_floor"
    assert all_reason_codes(features) == [
        "coverage_below_floor",
        "score_inside_deadband",
    ]

    rolled = rollup_refusals(
        [row(1, "BTC-PERP", "coverage_below_floor", "score_inside_deadband")]
    )
    assert len(rolled) == 1
    assert rolled[0]["refusals"] == 1
    # The secondary code is kept, it is just not a second refusal.
    assert rolled[0]["reason_codes"] == {
        "coverage_below_floor": 1,
        "score_inside_deadband": 1,
    }


def test_reason_tallies_merge_across_passes() -> None:
    first = rollup_refusals([row(1, "BTC-PERP", "a", "b")])[0]
    second = rollup_refusals([row(1, "BTC-PERP", "a")])[0]
    merged = merge_rollup(first, second)
    assert merged["refusals"] == 2
    assert merged["reason_codes"] == {"a": 2, "b": 1}


def test_an_older_single_string_reason_still_resolves() -> None:
    """Rows written before the list shape must not all land in 'unstated'."""
    assert primary_reason({"refusal_reason": "legacy_code"}) == "legacy_code"
    assert all_reason_codes({"refusal_reason": "legacy_code"}) == ["legacy_code"]


def test_a_refusal_with_an_empty_reason_list_is_unstated_not_dropped() -> None:
    assert primary_reason({"rejection_reasons": []}) == "unstated"
    assert rollup_refusals([{"created_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
                             "symbol": "S",
                             "features": {"rejection_reasons": []}}])[0]["reason"] == "unstated"
