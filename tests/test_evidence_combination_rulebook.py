"""The rulebook score calibrated as a probability, with the same doubt as the sources."""

from __future__ import annotations

import pytest

from evidence_combination_fixtures import decision
from tradesync_core.evidence_combination_rulebook import ScoreCalibration, calibrate_score


def informative(count: int):
    """Scores of +0.5 and -0.5; the market goes the score's way in three windows of four."""
    out = []
    for i in range(count):
        score = 0.5 if i % 2 == 0 else -0.5
        right = i % 8 not in (6, 7)
        out.append(decision(i, (score > 0) == right, score=score))
    return out


def test_worked_example_platt_probability() -> None:
    """Doc example 11: a = -0.04, b = 0.30, s = 0.28 -> 51.1%."""
    calibration = ScoreCalibration(-0.04, 0.30, 1, 1.0, 0.0)
    assert calibration.probability(0.28, 0.5) == pytest.approx(0.511, abs=1e-3)
    assert calibration.probability(None, 0.47) == 0.47


def test_an_informative_score_earns_a_positive_slope() -> None:
    calibration = calibrate_score(informative(400), 60)
    assert calibration is not None and calibration.decisions == 400
    assert calibration.slope > 1.5
    assert calibration.probability(0.5, 0.5) > 0.7 > 0.3 > calibration.probability(-0.5, 0.5)


def test_a_score_that_carries_nothing_forecasts_the_base_rate() -> None:
    decisions = [decision(i, i % 4 < 2, score=0.5 if i % 2 == 0 else -0.5) for i in range(400)]
    calibration = calibrate_score(decisions, 60)
    assert calibration.slope == pytest.approx(0.0, abs=1e-6)
    assert calibration.probability(0.5, 0.5) == pytest.approx(0.5, abs=1e-6)


def test_the_slope_prior_holds_back_a_thin_sample() -> None:
    assert 0 < calibrate_score(informative(16), 60).slope < calibrate_score(informative(400), 60).slope


def test_overlapping_scores_count_as_their_effective_windows() -> None:
    hourly = calibrate_score(informative(400), 60)
    clustered = calibrate_score([decision(i, d.rose, score=d.rulebook_score, spacing_s=360)
                                 for i, d in enumerate(informative(400))], 60)
    assert clustered.effective_windows == pytest.approx(40)
    assert clustered.slope < hourly.slope


def test_no_scored_decision_gives_no_calibration() -> None:
    assert calibrate_score([decision(0, True), decision(1, False)], 60) is None


def test_scores_without_spread_can_only_move_the_intercept() -> None:
    calibration = calibrate_score([decision(i, i % 4 == 0, score=0.0) for i in range(100)], 60)
    assert calibration.slope == 0.0
    assert calibration.probability(0.0, 0.5) == pytest.approx(25.5 / 101)
