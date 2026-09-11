"""Detectable, positive and economic are three different claims."""

from __future__ import annotations

import pytest

from tradesync_core.edge_evidence import (
    CellEvidence,
    CostAssumptions,
    apply_holm,
    assess_cell,
    chronological_split,
)
from tradesync_core.independence import Observation, binomial_se

MIN = 60
COSTS = CostAssumptions(0.09, 0.02, 0.02, source="test fixture, not a venue schedule")


def obs(symbol: str, minute: int, direction: str, forward: float) -> Observation:
    sign = 1 if direction == "LONG" else -1
    return Observation(symbol, minute * MIN, direction, forward, forward * sign)


def called(i: int, move: float, right_every: int = 10) -> Observation:
    """Alternate LONG and SHORT, five hours apart; wrong once every ``right_every``.

    The market rises for a right LONG or a wrong SHORT and falls otherwise, so
    the base rate stays near a coin flip and any skill is the caller's own.
    """
    is_long = i % 2 == 1
    right = i % right_every != 0
    market = move if is_long == right else -move
    return obs("BTC-PERP", i * 300, "LONG" if is_long else "SHORT", market)


def test_the_2026_09_09_false_positive_is_no_longer_significant() -> None:
    """The sample shape that reported -2.37 SE, "significant", on 9 September.

    Forty verdicts from three correlated symbols inside about five hours, at a
    240-minute horizon. Pooled, that is two independent windows. The skill is
    badly negative, the old error would have called it significant, and it is
    nowhere near detectable once the error reflects what the sample is worth.
    """
    sample = []
    for i in range(40):
        symbol = ("BTC-PERP", "ETH-PERP", "SOL-PERP")[i % 3]
        minute = i * 8
        if i % 5 == 0:
            sample.append(obs(symbol, minute, "SHORT", 0.2))  # every SHORT wrong
        elif i % 2 == 1 and i % 3 != 0:
            sample.append(obs(symbol, minute, "LONG", 0.2))  # some LONGs right
        else:
            sample.append(obs(symbol, minute, "LONG", -0.2))  # the rest wrong

    cell = assess_cell("240m rising", sample, 240, draws=300)
    apply_holm([cell])

    assert cell.skill == pytest.approx(-0.22)
    assert cell.independent_pooled == 2
    naive_z = cell.skill / binomial_se(cell.measured)
    assert naive_z < -2, "the old independence assumption called this significant"
    assert not cell.detectable
    assert not cell.positive_skill


def test_strongly_negative_skill_is_detectable_but_never_positive() -> None:
    """The old flag said "significant" for this. It is detectable, and it is bad."""
    always_wrong = [called(i, 0.1, right_every=1) for i in range(200)]
    cell = assess_cell("15m falling", always_wrong, 15, draws=200)
    apply_holm([cell])
    assert cell.skill == pytest.approx(-0.5)
    assert cell.detectable
    assert not cell.positive_skill


def test_a_real_positive_skill_survives_when_it_is_the_only_cell() -> None:
    good = [called(i, 0.1) for i in range(400)]
    cell = assess_cell("15m rising", good, 15, draws=200)
    apply_holm([cell])
    assert cell.skill == pytest.approx(0.4)
    assert cell.independent_pooled == 400
    assert cell.positive_skill


def _cell(label: str, p_positive: float, z: float) -> CellEvidence:
    return CellEvidence(
        label=label, horizon_minutes=15, measured=100,
        independent_per_symbol=100, independent_pooled=100,
        hit_rate=0.6, market_up_rate=0.5, long_share=0.5, expected_hit_rate=0.5,
        skill=0.1, se_binomial_pooled=0.05, se_block_bootstrap=0.05,
        standard_error=0.05, z=z, p_two_sided=2 * p_positive, p_positive=p_positive,
        detectable=abs(z) >= 2, mean_signed_return_pct=0.1, mean_net_return_pct=None,
        in_sample_skill=None, holdout_skill=None, holdout_measured=0,
    )


def test_holm_raises_the_bar_when_six_cells_were_looked_at() -> None:
    """p = 0.02 clears 2.5% alone, but not 2.5% / 6 among six cells."""
    lone = _cell("alone", 0.02, 2.05)
    apply_holm([lone])
    assert lone.positive_skill

    crowd = [_cell("marginal", 0.02, 2.05)] + [_cell(f"null{i}", 0.4, 0.25) for i in range(5)]
    apply_holm(crowd)
    assert not any(c.positive_skill for c in crowd)

    strong = [_cell("strong", 0.0001, 3.7)] + [_cell(f"null{i}", 0.4, 0.25) for i in range(5)]
    apply_holm(strong)
    assert strong[0].positive_skill
    assert not any(c.positive_skill for c in strong[1:])


def test_positive_skill_is_never_claimed_below_the_detectable_line() -> None:
    """z = 1.98 clears one-sided 2.5% (p = 0.024) but not two standard errors.

    Without the second condition a cell could be "positive" while not being
    "detectable", and the two verdicts would contradict each other.
    """
    borderline = _cell("borderline", 0.0239, 1.98)
    apply_holm([borderline])
    assert not borderline.detectable
    assert not borderline.positive_skill


def test_a_verdict_from_fewer_cells_does_not_survive_into_more() -> None:
    marginal = _cell("marginal", 0.02, 2.05)
    apply_holm([marginal])
    assert marginal.positive_skill
    apply_holm([marginal] + [_cell(f"null{i}", 0.4, 0.25) for i in range(5)])
    assert not marginal.positive_skill


def test_without_costs_economic_edge_is_unknown_not_false() -> None:
    cell = assess_cell("15m", [called(i, 0.1) for i in range(400)], 15, draws=100)
    apply_holm([cell])
    assert cell.positive_skill
    assert cell.economic_edge is None
    assert any("economic edge cannot be assessed" in n for n in cell.notes)


def test_a_gross_winner_that_loses_after_costs_has_no_economic_edge() -> None:
    """Right nine times in ten on moves too small to pay the costs."""
    small = [called(i, 0.05) for i in range(400)]
    cell = assess_cell("15m", small, 15, costs=COSTS, draws=200)
    apply_holm([cell])
    assert cell.positive_skill
    assert cell.mean_signed_return_pct == pytest.approx(0.04)
    assert cell.mean_net_return_pct == pytest.approx(0.04 - 0.13)
    assert cell.economic_edge is False


def test_costs_must_say_where_they_came_from() -> None:
    with pytest.raises(ValueError):
        CostAssumptions(0.09, 0.02, 0.02, source="  ")
    with pytest.raises(ValueError):
        CostAssumptions(-0.01, 0.02, 0.02, source="x")


def test_the_holdout_is_the_latest_data_never_a_shuffle() -> None:
    sample = [obs("BTC-PERP", m, "LONG", 0.1) for m in (50, 10, 40, 20, 30)]
    in_sample, holdout = chronological_split(sample, 0.4)
    assert [o.opened_at_s // MIN for o in in_sample] == [10, 20, 30]
    assert [o.opened_at_s // MIN for o in holdout] == [40, 50]


def test_a_sign_flip_between_periods_is_called_out() -> None:
    early = [called(i, 0.1, right_every=1_000) for i in range(1, 71)]  # all right
    late = [called(i, 0.1, right_every=1) for i in range(1_000, 1_030)]  # all wrong
    cell = assess_cell("15m", early + late, 15, draws=100)
    assert cell.in_sample_skill > 0 > cell.holdout_skill
    assert any("disagree in sign" in n for n in cell.notes)
