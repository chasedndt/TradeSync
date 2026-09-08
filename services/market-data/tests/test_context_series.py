"""The alignment rules the canvas context panes depend on."""

from __future__ import annotations

import pytest

from app.context_series import bucket_open, bucket_series, describe_coverage

MINUTE = 60
HOUR = 3600


def test_a_sample_lands_in_the_candle_it_falls_inside() -> None:
    # 15m buckets: 10:07:30 belongs to the candle that opened at 10:00.
    assert bucket_open(ts_ms=1_700_000_000_000, bucket_s=900) == 1_699_999_200
    assert bucket_open(1_699_999_200_000, 900) == 1_699_999_200
    assert bucket_open(1_700_000_099_999, 900) == 1_699_999_200


def test_repeated_samples_in_one_bucket_collapse_to_the_newest() -> None:
    """The context poller writes the same value several times per poll.

    One poll produces several events, each event produces a snapshot, and each
    snapshot appends a point. Four identical open-interest samples inside 200ms
    is normal; four points on the chart is not.
    """
    points = [
        {"ts": 1_000_000, "value": 10.0},
        {"ts": 1_000_100, "value": 10.0},
        {"ts": 1_000_150, "value": 10.0},
        {"ts": 1_000_200, "value": 11.0},
    ]
    series = bucket_series(points, bucket_s=900)
    assert len(series) == 1
    assert series[0]["value"] == 11.0
    assert series[0]["samples"] == 4


def test_an_empty_bucket_is_absent_rather_than_zero() -> None:
    """A collection gap must not be drawn as a market that did not move."""
    points = [
        {"ts": 0, "value": 5.0},
        # nothing at all for the next two hours
        {"ts": 3 * HOUR * 1000, "value": 7.0},
    ]
    series = bucket_series(points, bucket_s=HOUR)
    assert [entry["time"] for entry in series] == [0, 3 * HOUR]
    assert 5.0 in {entry["value"] for entry in series}


def test_funding_over_a_wide_bucket_reports_the_total_paid() -> None:
    """A 1d bucket covering 24 hourly rates is the day's cost, not one hour."""
    rates = [{"ts": index * HOUR * 1000, "rate": 0.0001} for index in range(24)]
    daily = bucket_series(rates, bucket_s=24 * HOUR, statistic="sum", value_key="rate")
    assert len(daily) == 1
    assert daily[0]["value"] == pytest.approx(0.0024)


def test_open_interest_over_a_wide_bucket_reports_the_standing_level() -> None:
    """Summing a level would be meaningless; it is not a flow."""
    points = [{"ts": index * MINUTE * 1000, "value": 100.0} for index in range(15)]
    series = bucket_series(points, bucket_s=900, statistic="last")
    assert series[0]["value"] == 100.0


def test_a_malformed_sample_is_dropped_not_defaulted_to_zero() -> None:
    """A zero funding rate is a claim about the market we cannot evidence."""
    points = [
        {"ts": 0, "value": 1.0},
        {"ts": 1000},  # no value
        {"ts": 2000, "value": None},
        {"ts": 3000, "value": "not a number"},
        {"value": 9.0},  # no timestamp
    ]
    series = bucket_series(points, bucket_s=HOUR)
    assert len(series) == 1
    assert series[0]["value"] == 1.0
    assert series[0]["samples"] == 1


def test_statistics_are_named_explicitly() -> None:
    points = [{"ts": 0, "value": 2.0}, {"ts": 1000, "value": 4.0}]
    assert bucket_series(points, HOUR, "mean")[0]["value"] == 3.0
    assert bucket_series(points, HOUR, "max")[0]["value"] == 4.0
    assert bucket_series(points, HOUR, "sum")[0]["value"] == 6.0
    with pytest.raises(ValueError):
        bucket_series(points, HOUR, "median")  # type: ignore[arg-type]


def test_a_non_positive_bucket_is_refused() -> None:
    with pytest.raises(ValueError):
        bucket_series([], 0)


def test_coverage_states_how_much_of_the_window_is_real() -> None:
    """Open interest reaches back 24h at most; the chart may reach further.

    The pane says so rather than letting a line stop without explanation.
    """
    candle_times = [index * HOUR for index in range(48)]
    # Only the most recent 24 hours were recorded.
    series = [{"time": index * HOUR, "value": 1.0} for index in range(24, 48)]

    coverage = describe_coverage(series, candle_times)
    assert coverage["candles"] == 48
    assert coverage["covered"] == 24
    assert coverage["coverage_pct"] == 50.0
    assert coverage["first_time"] == 24 * HOUR
    assert coverage["last_time"] == 47 * HOUR


def test_coverage_of_nothing_is_zero_not_an_error() -> None:
    assert describe_coverage([], [0, HOUR])["coverage_pct"] == 0.0
    empty = describe_coverage([], [])
    assert empty["candles"] == 0
    assert empty["first_time"] is None
