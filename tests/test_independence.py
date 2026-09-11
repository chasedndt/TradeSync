"""Independent windows are counted, not estimated from elapsed time."""

from __future__ import annotations

import pytest

from tradesync_core.independence import (
    Observation,
    binomial_se,
    block_bootstrap_skill_se,
    independent_counts,
    non_overlapping,
    skill_of,
)

MIN = 60


def obs(symbol: str, minute: int, direction: str = "LONG", forward: float = 0.1) -> Observation:
    sign = 1 if direction == "LONG" else -1
    return Observation(symbol, minute * MIN, direction, forward, forward * sign)


def test_a_verdict_every_minute_holds_few_independent_four_hour_windows() -> None:
    """The shape of the 2026-09-09 sample: one verdict a minute for 5.6 hours."""
    sample = [obs("BTC-PERP", m) for m in range(0, 337)]
    kept = non_overlapping(sample, 240)
    assert [o.opened_at_s // MIN for o in kept] == [0, 240]


def test_correlated_symbols_are_counted_generously_and_conservatively() -> None:
    sample = [obs(s, m) for s in ("BTC-PERP", "ETH-PERP", "SOL-PERP") for m in range(0, 337)]
    counts = independent_counts(sample, 240)
    assert counts == {"per_symbol": 6, "pooled": 2}


def test_a_collection_gap_does_not_create_windows_that_were_never_observed() -> None:
    """Ten minutes of data, a long outage, ten more minutes.

    Elapsed span over horizon would claim about seventeen hourly windows. Only
    two were ever observed.
    """
    sample = [obs("BTC-PERP", m) for m in range(0, 10)] + [
        obs("BTC-PERP", m) for m in range(1000, 1010)
    ]
    assert independent_counts(sample, 60)["per_symbol"] == 2


def test_windows_that_only_touch_do_not_overlap() -> None:
    sample = [obs("BTC-PERP", 0), obs("BTC-PERP", 60), obs("BTC-PERP", 119)]
    assert len(non_overlapping(sample, 60)) == 2


def test_a_biased_guesser_with_no_skill_scores_zero() -> None:
    """Always LONG in a market that rose three times in four: 75% hits, no skill."""
    sample = [obs("BTC-PERP", i * 300, "LONG", 0.1 if i % 4 else -0.1) for i in range(40)]
    measured = skill_of(sample)
    assert measured["hit_rate"] == pytest.approx(0.75)
    assert measured["expected_hit_rate"] == pytest.approx(0.75)
    assert measured["skill"] == pytest.approx(0.0)


def test_overlap_is_carried_into_the_bootstrap_error() -> None:
    """Two blocks, each internally identical: effectively two observations.

    Treated as forty independent points the error would be about 0.08. Keeping
    each block whole shows the real uncertainty, which is several times larger.
    """
    rights = [obs("BTC-PERP", m, "LONG", 0.1) for m in range(0, 20)]
    wrongs = [obs("BTC-PERP", m, "LONG", -0.1) for m in range(300, 320)]
    # Half LONG, half SHORT inside each block so the base rate is not degenerate.
    rights += [obs("BTC-PERP", m, "SHORT", -0.1) for m in range(20, 40)]
    wrongs += [obs("BTC-PERP", m, "SHORT", 0.1) for m in range(320, 340)]
    se = block_bootstrap_skill_se(rights + wrongs, 240, draws=400, seed=7)
    assert se is not None and se > 0.3
    assert se > 3 * binomial_se(80)


def test_the_bootstrap_is_reproducible() -> None:
    sample = [obs("BTC-PERP", m * 90, "LONG", 0.1 if m % 3 else -0.1) for m in range(30)]
    first = block_bootstrap_skill_se(sample, 60, draws=200, seed=1)
    assert first == block_bootstrap_skill_se(sample, 60, draws=200, seed=1)


def test_one_block_has_no_measurable_error() -> None:
    """Resampling a block against itself shows no variation; zero would be a lie."""
    sample = [obs("BTC-PERP", m) for m in range(10)]
    assert block_bootstrap_skill_se(sample, 240) is None


def test_no_evidence_has_no_error() -> None:
    assert binomial_se(0) is None
    assert skill_of([]) is None
