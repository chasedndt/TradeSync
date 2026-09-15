"""One source's likelihood ratios: shrinkage toward no update, intervals and polarity."""

from __future__ import annotations

import math

import pytest

from tradesync_core.evidence_combination_likelihood import (
    CallCounts,
    likelihood_ratios,
    log_variance,
    shrunk_probability,
    unshrunk_ratios,
)


def test_no_evidence_means_no_update() -> None:
    ratios = likelihood_ratios(CallCounts(0, 0, 0, 0))
    assert ratios.up_call.estimate == 1.0 and ratios.down_call.estimate == 1.0
    assert ratios.log_ratio(1) == 0.0 and ratios.log_ratio(-1) == 0.0 and ratios.swing == 0.0
    assert ratios.up_call.low < 1 < ratios.up_call.high


def test_worked_example_two_hundred_windows() -> None:
    """Doc example 1: 60 up calls in 100 rises, 40 in 100 falls. Plain LR 1.5; shrunk 1.4444."""
    counts = CallCounts(rose=100, up_calls_when_rose=60, fell=100, up_calls_when_fell=40)
    assert unshrunk_ratios(counts) == pytest.approx((1.5, 0.6667), abs=1e-4)
    ratios = likelihood_ratios(counts, prior_windows=20)
    assert ratios.p_up_call_when_rose == pytest.approx(65 / 110)
    assert ratios.up_call.estimate == pytest.approx(1.4444, abs=1e-4)
    assert ratios.up_call.excludes_one


def test_worked_example_twenty_windows() -> None:
    """Doc example 2: 6 up calls in 10 rises, 4 in 10 falls, twenty prior windows."""
    counts = CallCounts(rose=10, up_calls_when_rose=6, fell=10, up_calls_when_fell=4)
    assert counts.up_call_share == pytest.approx(0.5)
    ratios = likelihood_ratios(counts, prior_windows=20)
    assert ratios.p_up_call_when_rose == pytest.approx(0.55)
    assert ratios.p_up_call_when_fell == pytest.approx(0.45)
    assert ratios.up_call.estimate == pytest.approx(1.2222, abs=1e-4)
    assert ratios.down_call.estimate == pytest.approx(0.8182, abs=1e-4)
    assert ratios.up_call.low == pytest.approx(0.6635, abs=1e-4)
    assert ratios.up_call.high == pytest.approx(2.2515, abs=1e-4)
    assert not ratios.up_call.excludes_one


def test_more_windows_narrow_the_interval_and_approach_the_plain_ratio() -> None:
    widths, estimates = [], []
    for scale in (1, 4, 16, 64):
        ratios = likelihood_ratios(CallCounts(10 * scale, 6 * scale, 10 * scale, 4 * scale))
        widths.append(math.log(ratios.up_call.high) - math.log(ratios.up_call.low))
        estimates.append(ratios.up_call.estimate)
    assert widths == sorted(widths, reverse=True)
    assert estimates == sorted(estimates)
    assert estimates[-1] < 1.5 and estimates[-1] == pytest.approx(1.5, abs=0.02)


def test_a_contrarian_source_reads_below_one_without_a_polarity_test() -> None:
    ratios = likelihood_ratios(CallCounts(rose=40, up_calls_when_rose=10, fell=40, up_calls_when_fell=30))
    assert ratios.up_call.estimate < 1 < ratios.down_call.estimate
    assert ratios.swing < 0


def test_effective_counts_keep_the_plain_ratio_but_not_the_certainty() -> None:
    raw = CallCounts(600, 360, 600, 240)
    effective = raw.scaled(0.05)  # 1,200 overlapping calls worth 60 effective windows
    assert unshrunk_ratios(effective) == pytest.approx(unshrunk_ratios(raw))
    thin, thick = likelihood_ratios(effective), likelihood_ratios(raw)
    assert thin.up_call.high - thin.up_call.low > thick.up_call.high - thick.up_call.low
    assert thin.up_call.estimate < thick.up_call.estimate


def test_a_regime_prior_with_no_regime_windows_returns_the_prior_ratio() -> None:
    pooled = likelihood_ratios(CallCounts(30, 20, 30, 12))
    regime = likelihood_ratios(
        CallCounts(0, 0, 0, 0), prior=(pooled.p_up_call_when_rose, pooled.p_up_call_when_fell)
    )
    assert regime.up_call.estimate == pytest.approx(pooled.up_call.estimate)
    assert regime.down_call.estimate == pytest.approx(pooled.down_call.estimate)


def test_regime_shrinkage_worked_example() -> None:
    """Doc example 8: 0.55 elsewhere, 14 up calls in 20 effective rises here, 10 prior windows per class."""
    assert shrunk_probability(14, 20, 0.55, 10) == pytest.approx(0.65)


def test_log_variance_is_the_delta_method() -> None:
    assert log_variance(0.55, 20) == pytest.approx(0.45 / (0.55 * 21))


@pytest.mark.parametrize("counts", [(-1, 0, 1, 0), (1, 2, 1, 0), (math.nan, 0, 1, 0), (1, 0, math.inf, 0)])
def test_malformed_counts_are_refused(counts) -> None:
    with pytest.raises(ValueError):
        CallCounts(*counts)


def test_prior_windows_must_be_positive() -> None:
    with pytest.raises(ValueError):
        likelihood_ratios(CallCounts(1, 1, 1, 0), prior_windows=0)


def test_a_call_is_up_or_down() -> None:
    with pytest.raises(ValueError):
        likelihood_ratios(CallCounts(1, 1, 1, 0)).log_ratio(0)


def test_unshrunk_ratios_are_undefined_without_both_outcomes() -> None:
    assert unshrunk_ratios(CallCounts(5, 3, 0, 0)) == (None, None)
