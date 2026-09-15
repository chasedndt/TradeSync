"""The probability a call must reach to cover the round trip, and what cleared it."""

from __future__ import annotations

import pytest

from evidence_combination_fixtures import decision
from tradesync_core.evidence_combination_economics import (
    Breakeven,
    breakeven,
    breakeven_probabilities,
    clearance,
    side_cleared,
)


def test_side_cleared_names_the_side_or_none() -> None:
    threshold = Breakeven(0.12, 0.3, 0.3, 0.70, 0.30)
    assert [side_cleared(p, threshold) for p in (0.71, 0.70, 0.5, 0.30, 0.29)] == ["long", None, None, None, "short"]
    assert side_cleared(0.99, Breakeven(0.12, None, None, None, None)) is None


def test_worked_example_equal_moves() -> None:
    """Doc example 12: rises and falls of 0.30%, 0.12% round trip."""
    assert breakeven_probabilities(0.30, 0.30, 0.12) == pytest.approx((0.70, 0.30))


def test_unequal_moves_move_the_thresholds() -> None:
    long_above, short_below = breakeven_probabilities(0.3143, 0.3690, 0.12)
    assert long_above == pytest.approx(0.7156, abs=1e-4)
    assert short_below == pytest.approx(0.3644, abs=1e-4)


def test_costs_larger_than_the_typical_move_rule_out_both_sides() -> None:
    long_above, short_below = breakeven_probabilities(0.10, 0.10, 0.12)
    assert long_above > 1 and short_below < 0


def test_thresholds_are_measured_on_the_decisions_given() -> None:
    decisions = [decision(0, True, move=0.2), decision(1, True, move=0.4), decision(2, False, move=0.3)]
    threshold = breakeven(decisions, 0.12)
    assert threshold.mean_rise_pct == pytest.approx(0.3) and threshold.mean_fall_pct == pytest.approx(0.3)
    assert threshold.long_above == pytest.approx(0.7)
    assert breakeven([decision(0, True)], 0.12).long_above is None


def test_bad_inputs_are_refused() -> None:
    with pytest.raises(ValueError):
        breakeven_probabilities(0.0, 0.3, 0.12)
    with pytest.raises(ValueError):
        breakeven_probabilities(0.3, 0.3, -0.01)


def test_clearance_counts_probabilities_beyond_the_thresholds_and_nets_costs() -> None:
    threshold = Breakeven(0.12, 0.3, 0.3, 0.70, 0.30)
    decisions = [decision(0, True, move=0.5), decision(1, False, move=0.4), decision(2, True, move=0.1)]
    cleared = clearance(decisions, [0.75, 0.25, 0.6], threshold, 60)
    assert (cleared.long_calls, cleared.short_calls, cleared.decisions) == (1, 1, 3)
    assert cleared.mean_net_return_pct == pytest.approx(((0.5 - 0.12) + (0.4 - 0.12)) / 2)
    assert cleared.effective_windows == pytest.approx(2)


def test_nothing_cleared_reports_no_return() -> None:
    threshold = Breakeven(0.12, 0.3, 0.3, 0.70, 0.30)
    cleared = clearance([decision(0, True), decision(1, False)], [0.5, 0.5], threshold, 60)
    assert cleared.long_calls == cleared.short_calls == 0
    assert cleared.mean_net_return_pct is None and cleared.effective_windows == 0.0
    with pytest.raises(ValueError):
        clearance([decision(0, True)], [], threshold, 60)
