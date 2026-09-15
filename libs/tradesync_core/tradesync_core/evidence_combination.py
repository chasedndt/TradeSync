"""Combine evidence sources by their measured likelihood ratios: a research reading, never scoring.

The skill gate and the evidence cards say whether one source has skill. This
says what the sources would have been worth together. Each source's call at
entry moves the odds of a rise by its own likelihood ratio, measured on older
decisions with shrinkage toward no update (``evidence_combination_likelihood``);
sources that repeat each other share their vote
(``evidence_combination_dependence``); and the combined probability is scored
on the newest decisions against the base rate and against the rulebook's own
calibrated score (``evidence_combination_scoring``).

Shadow only. Nothing here reaches the scorer, the rulebook, the catalog, a
weight or a gate, and nothing is promoted. A better score is a reason for the
operator to register a forward comparison under this method's digest, not a
change. The walk-through with hand-worked numbers is
docs/research/2026-09-15_evidence-combination.md.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

from .evidence_combination_data import (
    DEFAULT_HOLDOUT_FRACTION,
    Decision,
    chronological_split,
    effective_windows,
    window_summary,
)
from .evidence_combination_economics import breakeven, clearance
from .evidence_combination_likelihood import DEFAULT_PRIOR_WINDOWS
from .evidence_combination_model import DEFAULT_MIN_REGIME_EFFECTIVE, CombinationModel, fit_model
from .evidence_combination_odds import Combined
from .evidence_combination_reading import insufficient_reading, plain_reading
from .evidence_combination_rulebook import ScoreCalibration, calibrate_score
from .evidence_combination_scoring import (
    DEFAULT_BINS,
    PROBABILITY_CLIP,
    brier_terms,
    log_loss_terms,
    paired_difference,
    score_forecast,
)

SCHEMA_VERSION = "evidence_combination_v1"
METHOD_VERSION = "evidence-combination-v1"
AUTHORITY = "research_only"

BASE_RATE = "base_rate"
RULEBOOK = "rulebook_score"
COMBINED = "combined"
NAIVE = "combined_without_dependence_adjustment"
METRICS = ("brier", "log_loss")
COMPARISONS = ((COMBINED, BASE_RATE), (COMBINED, RULEBOOK), (RULEBOOK, BASE_RATE), (NAIVE, COMBINED))

METHOD: dict[str, Any] = {
    "version": METHOD_VERSION,
    "reading": "sign of each source's entry reading; zero or missing abstains",
    "outcome": "forward return over the horizon: above zero rose, below zero fell, exactly zero excluded",
    "prior_windows": DEFAULT_PRIOR_WINDOWS,
    "base_rate": "fitting rise share at effective counts plus half a rise and half a fall",
    "likelihood_ratio": (
        "Beta-binomial; each conditional probability shrunk toward the source's up-call rate "
        "by prior_windows / 2 effective windows"
    ),
    "interval": "95%, delta method on the log likelihood ratio",
    "regime": (
        "per source where its effective regime windows reach min_regime_effective, shrunk toward "
        "the pooled ratio; the prior stays pooled"
    ),
    "min_regime_effective": DEFAULT_MIN_REGIME_EFFECTIVE,
    "dependence": (
        "residual within-outcome call correlation, polarity-signed, shrunk toward 1 by prior_windows; "
        "weight 1 / (1 + sum over others of max(0, rho) x min(1, |l_j| / |l_i|))"
    ),
    "rulebook_baseline": "Platt scaling of directional_score on the fitting decisions; slope prior worth prior_windows",
    "split": "chronological; newest holdout_fraction tested; fitting windows reaching into the test period purged",
    "holdout_fraction": DEFAULT_HOLDOUT_FRACTION,
    "effective_windows": "Kish over horizon-wide time clusters, symbols pooled",
    "reliability_bins": DEFAULT_BINS,
    "probability_clip": PROBABILITY_CLIP,
}

NOTE = (
    "Each source's call at entry moves the odds of a rise by its likelihood ratio, measured on the older "
    "decisions with shrinkage toward no update; sources that repeat each other share one vote; the combined "
    "probability is scored on the newest decisions against the base rate and the rulebook's calibrated score. "
    "Research reading only: no scoring influence, no rulebook, catalog or weight change, no execution authority "
    "and no automatic promotion. Promotion needs a pre-registered forward comparison under this method digest "
    "and an operator decision."
)


def method_digest(method: Mapping[str, Any] = METHOD) -> str:
    """SHA-256 of the method's canonical JSON; a forward comparison checks it has not changed."""
    canonical = json.dumps(method, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _rulebook_forecasts(calibration: ScoreCalibration | None, test: Sequence[Decision], prior: float) -> list[float]:
    if calibration is None:
        return [prior] * len(test)
    return [calibration.probability(d.rulebook_score, prior) for d in test]


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _sources(
    model: CombinationModel, ids: Sequence[str], test: Sequence[Decision], adjusted: Sequence[Combined]
) -> list[dict[str, Any]]:
    weights: dict[str, list[float]] = {}
    for combined in adjusted:
        for source, weight in combined.weights.items():
            if combined.contributions[source] != 0:
                weights.setdefault(source, []).append(weight)
    out = []
    for source_id in ids:
        entry = model.sources[source_id].to_dict()
        entry["test_calls"] = sum(1 for d in test if source_id in d.calls)
        entry["test_mean_weight"] = _mean(weights.get(source_id, []))
        out.append(entry)
    return out


def _dependence(
    model: CombinationModel, adjusted: Sequence[Combined], independent: Sequence[Combined]
) -> dict[str, Any]:
    pairs = sorted(model.pairs.values(), key=lambda p: (-p.redundancy, p.first, p.second))
    weights = [w for c in adjusted for source, w in c.weights.items() if c.contributions[source] != 0]
    return {
        "rule": METHOD["dependence"],
        "prior_windows": METHOD["prior_windows"],
        "pairs": [pair.to_dict() for pair in pairs],
        "test_mean_weight": _mean(weights),
        "test_mean_abs_evidence": {
            "adjusted": _mean([abs(c.evidence) for c in adjusted]),
            "counted_as_independent": _mean([abs(c.evidence) for c in independent]),
        },
    }


def assess_combination(
    decisions: Sequence[Decision],
    horizon_minutes: int,
    *,
    cost_pct: float,
    source_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Fit on the older decisions, score on the newest, and say what it means in words."""
    split = chronological_split(decisions, horizon_minutes, DEFAULT_HOLDOUT_FRACTION)
    ids = sorted(set(source_ids) if source_ids is not None else {s for d in decisions for s in d.calls})
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "method": {**METHOD, "digest": method_digest()},
        "horizon_minutes": horizon_minutes,
        "cost_pct": cost_pct,
        "decisions": len(decisions),
        "split": {
            "holdout_fraction": DEFAULT_HOLDOUT_FRACTION,
            "purged": split.purged,
            "flat_excluded": split.flat_excluded,
            "fit": window_summary(split.fit, horizon_minutes),
            "test": window_summary(split.test, horizon_minutes),
        },
        "authority": AUTHORITY,
        "promotion_allowed": False,
        "note": NOTE,
    }
    if not split.fit or not split.test:
        return {
            **report,
            "assessment": "insufficient_decisions",
            "base_rate": None,
            "sources": [],
            "dependence": None,
            "forecasts": None,
            "comparisons": [],
            "economics": None,
            "reading": insufficient_reading(horizon_minutes, len(split.fit), len(split.test)),
        }

    model = fit_model(split.fit, horizon_minutes, ids)
    calibration = calibrate_score(split.fit, horizon_minutes)
    test = list(split.test)
    adjusted = [model.predict(d) for d in test]
    independent = [model.predict(d, adjust_dependence=False) for d in test]
    prior = model.prior.rise_share
    forecasts = {
        BASE_RATE: [prior] * len(test),
        RULEBOOK: _rulebook_forecasts(calibration, test, prior),
        COMBINED: [c.probability for c in adjusted],
        NAIVE: [c.probability for c in independent],
    }
    outcomes = [d.outcome for d in test]
    opened = [d.opened_at_s for d in test]
    scores = {name: score_forecast(p, outcomes, opened, horizon_minutes) for name, p in forecasts.items()}
    terms = {
        name: {"brier": brier_terms(p, outcomes), "log_loss": log_loss_terms(p, outcomes)}
        for name, p in forecasts.items()
    }
    effective = effective_windows(test, horizon_minutes)
    comparisons = [
        paired_difference(candidate, baseline, metric, terms[candidate][metric], terms[baseline][metric], effective)
        for candidate, baseline in COMPARISONS
        for metric in METRICS
    ]
    threshold = breakeven(split.fit, cost_pct)
    cleared = clearance(test, forecasts[COMBINED], threshold, horizon_minutes)

    forecast_report = {name: score.to_dict() for name, score in scores.items()}
    forecast_report[RULEBOOK]["calibration"] = calibration.to_dict() if calibration else None
    forecast_report[RULEBOOK]["test_decisions_without_score"] = sum(1 for d in test if d.rulebook_score is None)
    return {
        **report,
        "assessment": "measured",
        "base_rate": model.prior.to_dict(),
        "sources": _sources(model, ids, test, adjusted),
        "dependence": _dependence(model, adjusted, independent),
        "forecasts": forecast_report,
        "comparisons": [c.to_dict() for c in comparisons],
        "economics": {**threshold.to_dict(), "test": cleared.to_dict()},
        "reading": plain_reading(horizon_minutes, scores, comparisons, threshold, cleared),
    }
