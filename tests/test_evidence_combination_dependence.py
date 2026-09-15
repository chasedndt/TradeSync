"""Correlated sources share their vote; independent ones keep it."""

from __future__ import annotations

import math
import random

import pytest

from evidence_combination_fixtures import decision
from tradesync_core.evidence_combination_dependence import (
    pair_dependence,
    redundancy_weights,
    residual_correlation,
    shrink_toward_redundant,
)
from tradesync_core.evidence_combination_odds import combine_log_odds, logit


def test_identical_calls_are_fully_redundant_and_opposite_calls_fully_opposed() -> None:
    rows = [(1, 1, True), (-1, -1, True), (1, 1, False), (-1, -1, False)]
    assert residual_correlation(rows) == pytest.approx(1.0)
    assert residual_correlation([(a, -b, rose) for a, b, rose in rows]) == pytest.approx(-1.0)


def test_agreement_that_comes_from_both_being_right_is_not_redundancy() -> None:
    """Both sources are right in 3 of 4 windows, with independent mistakes.

    They agree in 62.5% of windows, far more than chance, yet within the rising and
    within the falling windows their calls are unrelated: residual correlation zero.
    """
    rows = []
    for rose in (True, False):
        right = 1 if rose else -1
        for a_right in (True, True, True, False):
            for b_right in (True, True, True, False):
                rows.append((right if a_right else -right, right if b_right else -right, rose))
    assert sum(a == b for a, b, _ in rows) / len(rows) == pytest.approx(0.625)
    assert residual_correlation(rows) == pytest.approx(0.0, abs=1e-12)


def test_a_call_that_never_varies_within_outcomes_has_no_correlation() -> None:
    assert residual_correlation([(1, 1, True), (1, -1, True), (-1, 1, False), (-1, -1, False)]) is None
    assert residual_correlation([]) is None


def test_correlation_shrinks_toward_redundant_worked_example() -> None:
    """Doc example 6: 0.10 measured on 60 shared effective windows, twenty prior windows."""
    assert shrink_toward_redundant(0.10, 60, 20) == pytest.approx(0.325)
    assert shrink_toward_redundant(0.10, 0, 20) == pytest.approx(1.0)
    assert shrink_toward_redundant(0.10, 1000, 20) == pytest.approx(120 / 1020)
    with pytest.raises(ValueError):
        shrink_toward_redundant(0.1, -1, 20)


def test_two_exact_copies_get_half_a_vote_each() -> None:
    assert redundancy_weights({"a": 0.2231, "b": 0.2231}, lambda i, j: 1.0) == pytest.approx({"a": 0.5, "b": 0.5})


def test_independent_sources_keep_their_full_vote() -> None:
    weights = redundancy_weights({"a": 0.3, "b": -0.1, "c": 0.05}, lambda i, j: 0.0)
    assert weights == pytest.approx({"a": 1.0, "b": 1.0, "c": 1.0})


def test_equally_strong_sources_with_a_common_correlation_follow_kish() -> None:
    k, rho = 5, 0.3
    weights = redundancy_weights({f"s{i}": 0.1 for i in range(k)}, lambda i, j: rho)
    assert all(w == pytest.approx(1 / (1 + (k - 1) * rho)) for w in weights.values())


def test_a_source_with_nothing_to_say_dilutes_no_one() -> None:
    assert redundancy_weights({"a": 0.25, "silent": 0.0}, lambda i, j: 1.0)["a"] == pytest.approx(1.0)


def test_negative_correlation_never_boosts_a_vote() -> None:
    assert redundancy_weights({"a": 0.2, "b": 0.2}, lambda i, j: -0.8) == pytest.approx({"a": 1.0, "b": 1.0})


def test_partial_correlation_worked_example() -> None:
    """Doc example 5: LR 1.25 and 1.10, shrunk correlation 0.40, base rate 48%."""
    la, lb = math.log(1.25), math.log(1.10)
    weights = redundancy_weights({"a": la, "b": lb}, lambda i, j: 0.40)
    assert weights["a"] == pytest.approx(0.8541, abs=1e-4)
    assert weights["b"] == pytest.approx(0.7143, abs=1e-4)
    combined = combine_log_odds(logit(0.48), {"a": la, "b": lb}, lambda i, j: 0.40)
    assert combined.evidence == pytest.approx(0.2587, abs=1e-4)
    assert combined.probability == pytest.approx(0.5445, abs=1e-4)


def test_perfectly_correlated_sources_never_add_up_to_more_than_the_strongest() -> None:
    rng = random.Random(7)
    for _ in range(500):
        values = {f"s{i}": rng.uniform(0.001, 1.0) for i in range(rng.randint(2, 8))}
        weights = redundancy_weights(values, lambda i, j: 1.0)
        assert sum(weights[s] * v for s, v in values.items()) <= max(values.values()) + 1e-9


def test_pair_dependence_uses_shared_windows_and_signs_by_polarity() -> None:
    decisions = []
    for i in range(40):
        rose = i % 2 == 0
        call = 1 if i % 4 < 2 else -1  # varies within rises and within falls
        decisions.append(decision(i, rose, {"a": call, "b": -call}))
    decisions.append(decision(41, True, {"a": 1}))
    followers = pair_dependence(decisions, "a", "b", 60, polarity=1)
    assert followers.shared_decisions == 40 and followers.shared_effective == pytest.approx(40)
    assert followers.residual_correlation == pytest.approx(-1.0)
    assert followers.shrunk_correlation == pytest.approx((40 * -1 + 20) / 60)
    assert followers.redundancy == 0.0
    # One follows the market and the other is contrarian: opposite calls repeat the same evidence.
    assert pair_dependence(decisions, "a", "b", 60, polarity=-1).redundancy == pytest.approx(1.0)
    never_together = pair_dependence(decisions, "a", "c", 60, polarity=1)
    assert never_together.shared_decisions == 0 and never_together.redundancy == pytest.approx(1.0)
