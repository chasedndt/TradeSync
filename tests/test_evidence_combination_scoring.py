"""Brier score, log loss, reliability bins and paired differences at effective windows."""

from __future__ import annotations

import math

import pytest

from evidence_combination_fixtures import HOUR, T0
from tradesync_core.evidence_combination_scoring import (
    PairedDifference,
    brier_terms,
    equal_count_bins,
    log_loss_terms,
    paired_difference,
    score_forecast,
)


def mean(values):
    return sum(values) / len(values)


def hourly(count: int) -> list[int]:
    return [T0 + i * HOUR for i in range(count)]


def test_worked_example_brier_and_log_loss() -> None:
    """Doc example 9: forecasts 60%, 55%, 40% against rose, fell, fell."""
    p, y = [0.60, 0.55, 0.40], [1, 0, 0]
    assert mean(brier_terms(p, y)) == pytest.approx(0.2075)
    assert mean(log_loss_terms(p, y)) == pytest.approx(0.6067, abs=1e-4)
    assert mean(brier_terms([0.5] * 3, y)) == pytest.approx(0.25)
    assert mean(log_loss_terms([0.5] * 3, y)) == pytest.approx(math.log(2))


def test_worked_example_reliability_and_resolution() -> None:
    """Doc example 10: five forecasts of 40% with one rise, five of 60% with four."""
    p = [0.40] * 5 + [0.60] * 5
    y = [1, 0, 0, 0, 0] + [1, 1, 1, 1, 0]
    score = score_forecast(p, y, hourly(10), 60, bins=2)
    assert [b.decisions for b in score.bins] == [5, 5]
    assert [b.rise_share for b in score.bins] == pytest.approx([0.2, 0.8])
    assert score.brier == pytest.approx(0.20)
    assert score.reliability == pytest.approx(0.04)
    assert score.resolution == pytest.approx(0.09)
    assert score.uncertainty == pytest.approx(0.25)
    assert score.brier == pytest.approx(score.reliability - score.resolution + score.uncertainty)
    assert score.calibration_error == pytest.approx(0.20)


def test_a_gap_is_detectable_only_when_a_bin_interval_excludes_its_forecast() -> None:
    worked = score_forecast([0.40] * 5 + [0.60] * 5, [1, 0, 0, 0, 0] + [1, 1, 1, 1, 0], hourly(10), 60, bins=2)
    assert worked.bins_within_interval == 2 and not worked.miscalibration_detectable  # 20 points, five windows a bin
    wrong = score_forecast([0.5] * 20, [1] * 20, hourly(20), 60)
    assert wrong.bins_within_interval == 0 and wrong.miscalibration_detectable
    assert wrong.to_dict()["miscalibration_detectable"] is True and wrong.to_dict()["bins_within_interval"] == 0


def test_identical_forecasts_are_never_split_across_bins() -> None:
    assert equal_count_bins([0.5] * 10, 5) == [list(range(10))]
    assert equal_count_bins([0.1, 0.2, 0.2, 0.2, 0.3, 0.4], 3) == [[0, 1, 2, 3], [4, 5]]
    assert equal_count_bins([], 5) == []
    with pytest.raises(ValueError):
        equal_count_bins([0.5], 0)


def test_a_constant_forecast_is_one_reliability_point() -> None:
    score = score_forecast([0.52] * 8, [1, 0, 1, 1, 0, 0, 1, 0], hourly(8), 60)
    assert len(score.bins) == 1 and score.resolution == 0.0
    assert score.reliability == pytest.approx((0.52 - 0.5) ** 2)
    assert score.calibration_error == pytest.approx(0.02)


def test_a_bin_interval_uses_its_effective_windows() -> None:
    p, y = [0.5] * 12, [1, 0] * 6
    spread = score_forecast(p, y, hourly(12), 60).bins[0]
    bunched = score_forecast(p, y, [T0 + i * 60 for i in range(12)], 60).bins[0]
    assert spread.effective_windows == pytest.approx(12) and bunched.effective_windows == pytest.approx(1)
    assert bunched.high - bunched.low > spread.high - spread.low


def test_a_certain_mistake_costs_a_large_but_finite_log_loss() -> None:
    assert log_loss_terms([1.0], [0]) == [pytest.approx(-math.log(1e-6))]


def test_forecasts_and_outcomes_are_checked() -> None:
    with pytest.raises(ValueError):
        brier_terms([1.2], [1])
    with pytest.raises(ValueError):
        brier_terms([0.5], [2])
    with pytest.raises(ValueError):
        log_loss_terms([0.5, 0.5], [1])
    with pytest.raises(ValueError):
        score_forecast([], [], [], 60)


def test_paired_difference_interval_is_set_by_effective_windows() -> None:
    candidate = [0.60 if i % 2 else 0.64 for i in range(40)]
    baseline = [0.66] * 40
    wide = paired_difference("combined", "base_rate", "log_loss", candidate, baseline, effective=4)
    narrow = paired_difference("combined", "base_rate", "log_loss", candidate, baseline, effective=40)
    assert wide.mean == pytest.approx(narrow.mean) == pytest.approx(-0.04)
    assert (wide.high - wide.low) == pytest.approx((narrow.high - narrow.low) * math.sqrt(10))
    assert narrow.verdict == "better"
    assert paired_difference("a", "b", "brier", [0.1], [0.2], effective=1).verdict == "not_measurable"


def test_verdicts_read_lower_loss_as_better() -> None:
    assert PairedDifference("c", "b", "log_loss", -0.02, -0.03, -0.01, 50).verdict == "better"
    assert PairedDifference("c", "b", "log_loss", 0.02, 0.01, 0.03, 50).verdict == "worse"
    assert PairedDifference("c", "b", "log_loss", 0.0, -0.01, 0.01, 50).verdict == "not_distinguishable"
