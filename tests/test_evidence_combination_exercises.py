"""The remaining worked examples and the exercise answers printed in the design document, checked against the code."""

from __future__ import annotations

import math

import pytest

from evidence_combination_fixtures import decision
from tradesync_core.evidence_combination_data import effective_windows
from tradesync_core.evidence_combination_dependence import redundancy_weights
from tradesync_core.evidence_combination_economics import breakeven_probabilities
from tradesync_core.evidence_combination_likelihood import CallCounts, likelihood_ratios, unshrunk_ratios
from tradesync_core.evidence_combination_odds import combine_log_odds, logit, sigmoid
from tradesync_core.learning_stats import wilson_interval


def test_kish_effective_windows_worked_example() -> None:
    """Doc example 3: calls clustered 4, 4, 1 and 1 to an hour are 100 / 34 = 2.94 effective windows."""
    per_hour = (4, 4, 1, 1)
    decisions = [decision(hour * 10 + k, True, spacing_s=360) for hour, calls in enumerate(per_hour) for k in range(calls)]
    assert effective_windows(decisions, 60) == pytest.approx(100 / 34)


def test_worked_example_one_updates_a_prior() -> None:
    """Doc example 1: LR 1.5 moves 50% to 60%, and a 45% base rate to 55.1%."""
    assert combine_log_odds(logit(0.50), {"a": math.log(1.5)}).probability == pytest.approx(0.60)
    assert combine_log_odds(logit(0.45), {"a": math.log(1.5)}).probability == pytest.approx(0.5510, abs=1e-4)


def test_evidence_from_correlated_sources_saturates() -> None:
    """Doc example 13: sources of LR 1.1 with redundancy 0.25 can never carry 50% past 59.4%."""
    one = math.log(1.1)
    for k in (1, 10, 400):
        weights = redundancy_weights({f"s{i}": one for i in range(k)}, lambda i, j: 0.25)
        total = sum(weight * one for weight in weights.values())
        assert total == pytest.approx(k * one / (1 + (k - 1) * 0.25))
        assert total < one / 0.25
    assert sigmoid(one / 0.25) == pytest.approx(0.594, abs=1e-3)
    assert math.ceil(logit(0.70) / one) == 9  # nine independent agreeing sources to reach 70%


def test_exercise_one_likelihood_ratios() -> None:
    counts = CallCounts(rose=60, up_calls_when_rose=45, fell=60, up_calls_when_fell=30)
    assert unshrunk_ratios(counts) == pytest.approx((1.5, 0.5))
    ratios = likelihood_ratios(counts, prior_windows=20)
    assert ratios.up_call.estimate == pytest.approx(1.4140, abs=1e-4)
    assert ratios.down_call.estimate == pytest.approx(0.5558, abs=1e-4)


def test_exercises_two_and_three_combining() -> None:
    independent = combine_log_odds(logit(0.52), {"a": math.log(1.2), "b": math.log(1.3)})
    assert independent.probability == pytest.approx(0.6283, abs=1e-4)
    copies = combine_log_odds(logit(0.52), {"a": math.log(1.2), "copy": math.log(1.2)}, lambda i, j: 1.0)
    assert copies.probability == pytest.approx(0.5652, abs=1e-4)


def test_exercise_five_breakeven() -> None:
    assert breakeven_probabilities(0.25, 0.35, 0.12) == pytest.approx((0.7833, 0.3833), abs=1e-4)


def test_exercise_six_a_five_point_gap_on_one_hundred_windows_is_not_detectable() -> None:
    low, high = wilson_interval(0.55, 100)
    assert (low, high) == pytest.approx((0.4524, 0.6439), abs=1e-4)
    assert low <= 0.60 <= high
