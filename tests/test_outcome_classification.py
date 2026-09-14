"""A measured horizon is named against an explicit round-trip cost."""

from __future__ import annotations

import pytest

from tradesync_core.outcome_classification import (
    CLEAN_WIN,
    DEFAULT_ROUND_TRIP_COST_PCT,
    NO_FOLLOW_THROUGH,
    REVERSED,
    WIN_AFTER_DRAWDOWN,
    WRONG_DIRECTION,
    ClassificationError,
    classify_outcome,
)


def test_default_cost_is_the_skill_gate_round_trip() -> None:
    assert DEFAULT_ROUND_TRIP_COST_PCT == 0.12


def test_a_win_beyond_costs_with_a_shallow_drawdown_is_clean() -> None:
    outcome = classify_outcome(0.50, 0.60, 0.10)
    assert outcome.classification == CLEAN_WIN
    assert outcome.won and outcome.decided
    assert outcome.net_return_pct == pytest.approx(0.38)


def test_a_win_after_a_drawdown_deeper_than_the_net_win() -> None:
    outcome = classify_outcome(0.30, 0.45, 0.25)  # nets 0.18, endured 0.25
    assert outcome.classification == WIN_AFTER_DRAWDOWN
    assert outcome.won


def test_a_drawdown_equal_to_the_net_win_is_still_clean() -> None:
    assert classify_outcome(0.75, 1.0, 0.5, cost_pct=0.25).classification == CLEAN_WIN


def test_a_loss_that_never_cleared_costs_in_favour_is_wrong_direction() -> None:
    outcome = classify_outcome(-0.40, 0.05, 0.50)
    assert outcome.classification == WRONG_DIRECTION
    assert outcome.decided and not outcome.won
    assert outcome.net_return_pct == pytest.approx(-0.52)


def test_a_loss_after_clearing_costs_in_favour_is_reversed() -> None:
    assert classify_outcome(-0.30, 0.25, 0.45).classification == REVERSED


@pytest.mark.parametrize("signed", [0.12, 0.05, 0.0, -0.05, -0.12])
def test_a_move_inside_the_cost_band_is_no_follow_through_whatever_its_sign(signed) -> None:
    outcome = classify_outcome(signed, 0.30, 0.30)
    assert outcome.classification == NO_FOLLOW_THROUGH
    assert not outcome.decided and not outcome.won


def test_the_cost_is_configurable() -> None:
    assert classify_outcome(0.10, 0.2, 0.0, cost_pct=0.05).classification == CLEAN_WIN
    assert classify_outcome(0.10, 0.2, 0.0, cost_pct=0.20).classification == NO_FOLLOW_THROUGH
    assert classify_outcome(0.10, 0.2, 0.0, cost_pct=0.20).cost_pct == 0.20


def test_missing_excursions_are_read_as_none_recorded() -> None:
    outcome = classify_outcome(-0.5, None, None)
    assert outcome.classification == WRONG_DIRECTION
    assert outcome.max_favourable_pct == 0.0


@pytest.mark.parametrize(
    "args",
    [("0.1", 0, 0), (float("nan"), 0, 0), (True, 0, 0), (0.1, 0, 0, -0.01), (0.1, 0, 0, 0.12, 0)],
)
def test_malformed_input_is_refused(args) -> None:
    with pytest.raises(ClassificationError):
        classify_outcome(*args)
