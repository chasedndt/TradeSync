"""The plain-language reading of an evidence-combination result.

Written for the operator scanning the Learning view: whether combined sources
were better or worse calibrated than the base rate, whether their scores differ
from both baselines by more than the test window can resolve, and whether any
combined probability was high enough to pay for the round trip. Every sentence
is built from numbers already in the report and judges nothing beyond them.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from .evidence_combination_economics import Breakeven, Clearance
from .evidence_combination_scoring import ForecastScore, PairedDifference

NAMES = {
    "base_rate": "the base rate",
    "rulebook_score": "the rulebook score",
    "combined": "combined sources",
    "combined_without_dependence_adjustment": "combined sources counted as independent",
}


def horizon_words(minutes: int) -> str:
    if minutes % 60 == 0:
        hours = minutes // 60
        return "1 hour" if hours == 1 else f"{hours} hours"
    return f"{minutes} minutes"


def _points(value: float) -> str:
    return f"{value * 100:.1f} points"


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _calibration_sentence(horizon_minutes: int, combined: ForecastScore, base: ForecastScore) -> str:
    if combined.calibration_error < base.calibration_error:
        judged = "better calibrated than"
    elif combined.calibration_error > base.calibration_error:
        judged = "worse calibrated than"
    else:
        judged = "as well calibrated as"
    return (
        f"At {horizon_words(horizon_minutes)}, combined sources would have been {judged} the base rate on the "
        f"newest {combined.decisions:,} decisions: their forecasts sat {_points(combined.calibration_error)} from "
        f"what happened on average, against {_points(base.calibration_error)} for the base rate."
    )


def difference_phrase(difference: PairedDifference) -> str:
    span = (
        f"{difference.low:+.4f} to {difference.high:+.4f}"
        if difference.low is not None and difference.high is not None
        else ""
    )
    if difference.verdict == "better":
        return f"lower, and the 95% interval of the difference ({span}) is below zero"
    if difference.verdict == "worse":
        return f"higher, and the 95% interval of the difference ({span}) is above zero"
    if difference.verdict == "not_distinguishable":
        return f"the 95% interval of the difference ({span}) includes zero, so this test window cannot tell them apart"
    return "too few effective windows to put an interval on the difference"


def _score_sentence(scores: Mapping[str, ForecastScore], comparisons: Sequence[PairedDifference]) -> str:
    parts = []
    for baseline in ("base_rate", "rulebook_score"):
        difference = next(
            (c for c in comparisons if c.candidate == "combined" and c.baseline == baseline and c.metric == "log_loss"),
            None,
        )
        if difference is None or baseline not in scores:
            continue
        parts.append(f"{scores[baseline].log_loss:.4f} for {NAMES[baseline]} ({difference_phrase(difference)})")
    if not parts:
        return ""
    return f"Log loss was {scores['combined'].log_loss:.4f} for combined sources, against " + "; and ".join(parts) + "."


def _economics_sentence(threshold: Breakeven, cleared: Clearance) -> str:
    if threshold.long_above is None:
        return "The fitting window had too few rises or falls to state the probability a call needs to cover costs."
    levels = f"above {_percent(threshold.long_above)} for a long"
    if threshold.short_below is not None and threshold.short_below > 0:
        levels += f" or below {_percent(threshold.short_below)} for a short"
    cost = f"the {threshold.cost_pct:.2f}% round trip"
    calls = cleared.long_calls + cleared.short_calls
    if calls == 0:
        return f"No test decision's combined probability was {levels}, the levels needed to cover {cost}."
    detail = ""
    if cleared.mean_net_return_pct is not None:
        detail = f"; the implied calls averaged {cleared.mean_net_return_pct:+.3f}% after costs"
        if cleared.low is not None and cleared.high is not None:
            detail += f" (95% interval {cleared.low:+.3f}% to {cleared.high:+.3f}%)"
    return (
        f"{calls:,} of {cleared.decisions:,} test decisions had a combined probability {levels}, "
        f"the levels needed to cover {cost}{detail}."
    )


def plain_reading(
    horizon_minutes: int,
    scores: Mapping[str, ForecastScore],
    comparisons: Sequence[PairedDifference],
    threshold: Breakeven,
    cleared: Clearance,
) -> str:
    sentences = [
        _calibration_sentence(horizon_minutes, scores["combined"], scores["base_rate"]),
        _score_sentence(scores, comparisons),
        _economics_sentence(threshold, cleared),
        "Research reading only: nothing here changes scoring, weights or gates.",
    ]
    return " ".join(sentence for sentence in sentences if sentence)


def insufficient_reading(horizon_minutes: int, fit_decisions: int, test_decisions: int) -> str:
    return (
        f"At {horizon_words(horizon_minutes)} there are not yet enough measured decisions to fit on older ones and "
        f"test on newer ones ({fit_decisions:,} to fit, {test_decisions:,} to test). Nothing is inferred."
    )
