"""Fitting sources on older decisions and combining them: base rate, duplicates, missing sources, regimes."""

from __future__ import annotations

import math

import pytest

from evidence_combination_fixtures import decision, skilled_call, uninformative_call
from tradesync_core.evidence_combination_likelihood import unshrunk_ratios
from tradesync_core.evidence_combination_model import base_rate, call_counts, fit_model
from tradesync_core.evidence_combination_odds import combine_log_odds, logit, sigmoid


def test_the_prior_is_the_fitting_share_of_rises_not_one_half() -> None:
    """Doc example 3: 30 rises in 100 independent windows -> (30 + 0.5) / (100 + 1)."""
    hourly = [decision(i, i % 10 < 3) for i in range(100)]
    assert base_rate(hourly, 60).rise_share == pytest.approx(30.5 / 101)


def test_the_prior_counts_effective_windows_not_overlapping_calls() -> None:
    """Ten calls per hour for ten hours are ten effective windows: (3 + 0.5) / (10 + 1)."""
    clustered = [decision(i, i % 10 < 3, spacing_s=360) for i in range(100)]
    prior = base_rate(clustered, 60)
    assert prior.effective_windows == pytest.approx(10)
    assert prior.rise_share == pytest.approx(3.5 / 11)


def test_worked_example_independent_sources() -> None:
    """Doc example 4: base rate 48%, LR 1.25 and LR 1.10, independent."""
    combined = combine_log_odds(logit(0.48), {"a": math.log(1.25), "b": math.log(1.10)})
    assert logit(0.48) == pytest.approx(-0.0800, abs=1e-4)
    assert combined.log_odds == pytest.approx(0.2384, abs=1e-4)
    assert combined.probability == pytest.approx(0.5593, abs=1e-4)


def test_worked_example_an_exact_copy_counts_once() -> None:
    """Doc example 4, continued: B is an exact copy of A with LR 1.25."""
    same = {"a": math.log(1.25), "copy": math.log(1.25)}
    counted_once = combine_log_odds(logit(0.48), same, lambda i, j: 1.0)
    counted_twice = combine_log_odds(logit(0.48), same)
    assert counted_once.probability == pytest.approx(0.5357, abs=1e-4)
    assert counted_twice.probability == pytest.approx(0.5906, abs=1e-4)


def test_sigmoid_is_stable_at_the_extremes() -> None:
    assert sigmoid(1000) == 1.0 and sigmoid(-1000) == 0.0 and sigmoid(0) == 0.5


def test_two_perfectly_duplicated_sources_do_not_double_the_update() -> None:
    decisions = []
    for i in range(400):
        rose, call = skilled_call(i)
        decisions.append(decision(i, rose, {"a": call, "copy": call}))
    both = fit_model(decisions, 60)
    alone = fit_model([decision(i, d.rose, {"a": d.calls["a"]}) for i, d in enumerate(decisions)], 60)

    single = alone.predict(decision(500, True, {"a": 1}))
    duplicated = both.predict(decision(500, True, {"a": 1, "copy": 1}))
    assert single.evidence > 0.5  # a real update, so the comparison means something
    assert both.pairs[("a", "copy")].redundancy == pytest.approx(1.0)
    assert duplicated.weights == pytest.approx({"a": 0.5, "copy": 0.5})
    assert duplicated.evidence == pytest.approx(single.evidence)
    assert duplicated.probability == pytest.approx(single.probability)
    # Counted as independent, the copy doubles the update: exactly what the adjustment prevents.
    assert both.predict(decision(500, True, {"a": 1, "copy": 1}), adjust_dependence=False).evidence == pytest.approx(
        2 * single.evidence
    )


def test_a_source_that_abstains_or_has_no_record_contributes_nothing() -> None:
    decisions = []
    for i in range(300):
        rose, call = skilled_call(i)
        calls = {"a": call, "b": uninformative_call(i)} if i % 3 else {"a": call}
        decisions.append(decision(i, rose, calls))
    model = fit_model(decisions, 60)

    silent = model.predict(decision(900, True, {}))
    assert silent.contributions == {} and silent.probability == pytest.approx(model.prior.rise_share)
    only_a = model.predict(decision(900, True, {"a": 1}))
    assert only_a.weights == {"a": 1.0}
    assert only_a.evidence == pytest.approx(model.sources["a"].ratios_for("rising").log_ratio(1))
    stranger = model.predict(decision(900, True, {"a": 1, "never_fitted": -1}))
    assert set(stranger.contributions) == {"a"} and stranger.evidence == pytest.approx(only_a.evidence)


def test_a_source_with_no_information_leaves_the_forecast_at_the_base_rate() -> None:
    decisions = [decision(i, i % 2 == 0, {"coin": uninformative_call(i)}) for i in range(200)]
    model = fit_model(decisions, 60)
    ratios = model.sources["coin"].pooled
    assert ratios.up_call.estimate == pytest.approx(1.0) and ratios.down_call.estimate == pytest.approx(1.0)
    assert model.predict(decision(300, True, {"coin": 1})).probability == pytest.approx(model.prior.rise_share)


def test_regime_conditioning_only_where_the_sample_supports_it() -> None:
    decisions = []
    for i in range(120):  # follows the market in rising markets
        rose, call = skilled_call(i)
        decisions.append(decision(i, rose, {"s": call}, regime="rising"))
    for i in range(120, 240):  # contrarian in falling markets
        rose, call = skilled_call(i)
        decisions.append(decision(i, rose, {"s": -call}, regime="falling"))
    for i in range(240, 246):  # six windows in flat markets: too few to condition on
        rose, call = skilled_call(i)
        decisions.append(decision(i, rose, {"s": call}, regime="flat"))
    model = fit_model(decisions, 60, min_regime_effective=20)
    source = model.sources["s"]
    rising, falling, flat = (source.regimes[key] for key in ("rising", "falling", "flat"))

    assert rising.conditioned and falling.conditioned and not flat.conditioned
    assert rising.ratios.up_call.estimate > 1 > falling.ratios.up_call.estimate
    assert source.ratios_for("flat") is source.pooled and source.ratios_for("unknown") is source.pooled
    plain_rising = unshrunk_ratios(call_counts([d for d in decisions if d.regime == "rising"], "s", 60)[0])[0]
    assert plain_rising == pytest.approx(2.0)
    assert 1 < rising.ratios.up_call.estimate < plain_rising  # shrunk toward the other regimes
    up_in_rising = model.predict(decision(900, True, {"s": 1}, regime="rising")).probability
    up_in_falling = model.predict(decision(901, True, {"s": 1}, regime="falling")).probability
    assert up_in_rising > model.prior.rise_share > up_in_falling


def test_a_single_regime_is_shrunk_toward_no_update_like_the_pooled_ratio() -> None:
    decisions = [decision(i, *skilled_call(i)[:1], {"s": skilled_call(i)[1]}) for i in range(200)]
    source = fit_model(decisions, 60).sources["s"]
    assert source.regimes["rising"].conditioned
    assert source.ratios_for("rising").up_call.estimate == pytest.approx(source.pooled.up_call.estimate)


def test_a_source_report_names_polarity_counts_and_regimes() -> None:
    decisions = []
    for i in range(200):
        rose, call = skilled_call(i)
        decisions.append(decision(i, rose, {"follows": call, "contrarian": -call}))
    model = fit_model(decisions, 60)
    follows, contrarian = model.sources["follows"].to_dict(), model.sources["contrarian"].to_dict()
    assert follows["polarity"] == "follows" and contrarian["polarity"] == "contrarian"
    assert follows["fit_calls"] == 200 and follows["fit_effective_windows"] == pytest.approx(200)
    assert follows["unshrunk"]["up_call"] == pytest.approx(2.0) and follows["interval_excludes_one"]
    assert [r["regime"] for r in follows["regimes"]] == ["rising"]
    # A follower and a contrarian that mirror each other are the same evidence.
    assert model.pairs[("contrarian", "follows")].redundancy == pytest.approx(1.0)
