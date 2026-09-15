"""The whole reading: chronological purged split, research-only authority, and results that mean what they say."""

from __future__ import annotations

import pytest

from evidence_combination_fixtures import decision, skilled_call, uninformative_call
from tradesync_core.evidence_combination import METHOD, assess_combination, method_digest
from tradesync_core.evidence_combination_data import call_from_reading, chronological_split


def skilled_market(count: int = 1000):
    """A source with real skill, an exact copy of it, a coin, and a rulebook score that carries nothing."""
    out = []
    for i in range(count):
        rose, call = skilled_call(i)
        calls = {"skill": call, "copy": call, "coin": uninformative_call(i)}
        out.append(decision(i, rose, calls, score=0.5 if i % 4 < 2 else -0.5))
    return out


def test_readings_become_calls_and_zero_abstains() -> None:
    assert call_from_reading(0.3) == 1 and call_from_reading(-2) == -1
    assert call_from_reading(0.0) is None and call_from_reading(None) is None
    assert call_from_reading(float("nan")) is None


def test_split_is_chronological_purged_and_excludes_flat_windows() -> None:
    decisions = [decision(i, i % 2 == 0, spacing_s=1800) for i in range(10)]
    decisions.append(decision(99, True, move=0.0))
    split = chronological_split(list(reversed(decisions)), 60)
    assert split.flat_excluded == 1
    assert [d.key for d in split.test] == ["d00007", "d00008", "d00009"]
    # d00006 opened 30 minutes before the first test decision: its hour reaches into the test period.
    assert [d.key for d in split.fit] == [f"d{i:05d}" for i in range(6)] and split.purged == 1
    with pytest.raises(ValueError):
        chronological_split(decisions, 60, holdout_fraction=1.0)


def test_the_report_is_research_only_and_names_its_method() -> None:
    report = assess_combination(skilled_market(200), 60, cost_pct=0.12)
    assert report["authority"] == "research_only" and report["promotion_allowed"] is False
    assert report["schema_version"] == "evidence_combination_v1" and report["assessment"] == "measured"
    assert report["method"]["digest"] == method_digest() and len(method_digest()) == 64
    assert set(report["forecasts"]) == {"base_rate", "rulebook_score", "combined", "combined_without_dependence_adjustment"}
    assert "operator decision" in report["note"]


def test_the_digest_changes_when_any_constant_changes() -> None:
    assert method_digest({**METHOD, "prior_windows": 21.0}) != method_digest()
    assert method_digest(dict(reversed(list(METHOD.items())))) == method_digest()


def test_too_few_decisions_are_reported_not_scored() -> None:
    report = assess_combination([decision(0, True, {"a": 1})], 60, cost_pct=0.12)
    assert report["assessment"] == "insufficient_decisions" and report["forecasts"] is None
    assert "Nothing is inferred" in report["reading"]


def test_a_skilled_source_beats_the_base_rate_and_its_copy_is_not_counted_twice() -> None:
    report = assess_combination(skilled_market(), 60, cost_pct=0.12)
    split = report["split"]
    assert split["fit"]["decisions"] == 700 and split["test"]["decisions"] == 300 and split["purged"] == 0
    assert split["test"]["effective_windows"] == pytest.approx(300)
    assert split["test"]["independent_windows"]["pooled"] == 300

    forecasts = report["forecasts"]
    assert forecasts["combined"]["log_loss"] < forecasts["base_rate"]["log_loss"]
    comparisons = {(c["candidate"], c["baseline"], c["metric"]): c for c in report["comparisons"]}
    assert comparisons[("combined", "base_rate", "log_loss")]["verdict"] == "better"
    assert comparisons[("combined", "rulebook_score", "brier")]["verdict"] == "better"
    # Counted as independent, the copy doubles the evidence and the forecast becomes overconfident.
    assert forecasts["combined_without_dependence_adjustment"]["log_loss"] > forecasts["combined"]["log_loss"]
    assert forecasts["rulebook_score"]["calibration"]["slope"] == pytest.approx(0.0, abs=1e-6)

    sources = {s["source_id"]: s for s in report["sources"]}
    assert sources["skill"]["test_mean_weight"] == pytest.approx(0.5)
    assert sources["coin"]["test_mean_weight"] is None  # its log LR is exactly zero: nothing to weigh
    assert report["dependence"]["pairs"][0]["first"] == "copy" and report["dependence"]["pairs"][0]["redundancy"] == 1.0
    assert "Log loss was" in report["reading"] and "the base rate" in report["reading"]


def test_the_economics_name_the_breakeven_and_what_cleared_it() -> None:
    report = assess_combination(skilled_market(), 60, cost_pct=0.12)
    economics = report["economics"]
    assert economics["long_above"] == pytest.approx(0.70) and economics["short_below"] == pytest.approx(0.30)
    # Up calls reach about 66%, short of 70%; down calls fall to about 26%, below 30%.
    assert economics["test"]["long_calls"] == 0 and economics["test"]["short_calls"] > 0
    assert "for a short" in report["reading"] and "0.12% round trip" in report["reading"]


def test_sources_that_know_nothing_leave_every_forecast_at_the_base_rate() -> None:
    decisions = [decision(i, i % 2 == 0, {"coin": uninformative_call(i)}) for i in range(400)]
    report = assess_combination(decisions, 60, cost_pct=0.12)
    forecasts = report["forecasts"]
    assert forecasts["combined"]["log_loss"] == pytest.approx(forecasts["base_rate"]["log_loss"])
    assert report["sources"][0]["likelihood_ratio"]["up_call"]["estimate"] == pytest.approx(1.0)
    assert not report["sources"][0]["interval_excludes_one"]
    assert "No test decision" in report["reading"]
