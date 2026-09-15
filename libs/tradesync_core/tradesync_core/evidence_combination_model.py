"""Fit sources on older decisions, then combine them on newer ones.

    ln odds(rise | calls) = ln odds(base rate) + sum over sources that called of  w_i x ln LR_i(call_i | regime)

- The base rate is the fitting period's own share of rising windows, at
  effective counts, plus half an imaginary rise and half a fall. Not 50%.
- A source that called contributes the log LR of the call it made. A source
  that abstained, or has no fitting record, contributes nothing.
- A source's LR is conditioned on the decision's entry regime only where that
  source has at least ``min_regime_effective`` effective fitting windows in the
  regime, and even then it is shrunk toward what the source's calls meant in
  the *other* regimes, so no window is used twice (with no other regime on
  record it is shrunk toward no update, like any source). Elsewhere the pooled
  LR is used. The regime label is not itself evidence: the prior stays pooled.
- w_i is the redundancy weight from ``evidence_combination_dependence``. With
  ``adjust_dependence=False`` every weight is 1: naive Bayes, which counts
  correlated sources twice. It is kept only as a comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .evidence_combination_data import Decision, effective_windows
from .evidence_combination_dependence import PairDependence, pair_dependence, polarity_of
from .evidence_combination_likelihood import (
    DEFAULT_PRIOR_WINDOWS,
    CallCounts,
    LikelihoodRatios,
    likelihood_ratios,
    unshrunk_ratios,
)
from .evidence_combination_odds import Combined, combine_log_odds, logit

DEFAULT_MIN_REGIME_EFFECTIVE = 20.0


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


@dataclass(frozen=True)
class BaseRate:
    rise_share: float
    decisions: int
    effective_windows: float

    @property
    def log_odds(self) -> float:
        return logit(self.rise_share)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rise_share": round(self.rise_share, 6),
            "log_odds": round(self.log_odds, 6),
            "decisions": self.decisions,
            "effective_windows": round(self.effective_windows, 3),
        }


def base_rate(decisions: Sequence[Decision], horizon_minutes: int) -> BaseRate:
    """The period's own share of rising windows at effective counts, with half a rise and half a fall added."""
    moved = [d for d in decisions if d.moved]
    if not moved:
        return BaseRate(0.5, 0, 0.0)
    effective = effective_windows(moved, horizon_minutes)
    rose = effective * sum(d.rose for d in moved) / len(moved)
    return BaseRate((rose + 0.5) / (effective + 1.0), len(moved), effective)


def call_counts(decisions: Iterable[Decision], source_id: str, horizon_minutes: int) -> tuple[CallCounts, int]:
    """A source's effective call counts over the decisions where it called, and its raw number of calls."""
    called = [d for d in decisions if d.moved and source_id in d.calls]
    if not called:
        return CallCounts(0.0, 0.0, 0.0, 0.0), 0
    rose = [d for d in called if d.rose]
    fell = [d for d in called if not d.rose]
    raw = CallCounts(
        float(len(rose)),
        float(sum(d.calls[source_id] > 0 for d in rose)),
        float(len(fell)),
        float(sum(d.calls[source_id] > 0 for d in fell)),
    )
    return raw.scaled(effective_windows(called, horizon_minutes) / len(called)), len(called)


@dataclass(frozen=True)
class RegimeRatios:
    regime: str
    calls: int
    effective_windows: float
    conditioned: bool
    ratios: LikelihoodRatios

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "calls": self.calls,
            "effective_windows": round(self.effective_windows, 3),
            "conditioned": self.conditioned,
            "up_call": self.ratios.up_call.to_dict(),
            "down_call": self.ratios.down_call.to_dict(),
        }


@dataclass(frozen=True)
class SourceModel:
    source_id: str
    calls: int
    counts: CallCounts
    pooled: LikelihoodRatios
    regimes: Mapping[str, RegimeRatios]

    @property
    def has_record(self) -> bool:
        return self.calls > 0

    def ratios_for(self, regime: str) -> LikelihoodRatios:
        entry = self.regimes.get(regime)
        return entry.ratios if entry is not None and entry.conditioned else self.pooled

    def to_dict(self) -> dict[str, Any]:
        up, down = unshrunk_ratios(self.counts)
        swing = self.pooled.swing
        return {
            "source_id": self.source_id,
            "fit_calls": self.calls,
            "fit_effective_windows": round(self.counts.windows, 3),
            "up_call_share": round(self.counts.up_call_share, 6) if self.has_record else None,
            "likelihood_ratio": self.pooled.to_dict(),
            "unshrunk": {"up_call": _round(up), "down_call": _round(down)},
            "polarity": "follows" if swing > 0 else "contrarian" if swing < 0 else "none",
            "interval_excludes_one": self.pooled.up_call.excludes_one or self.pooled.down_call.excludes_one,
            "regimes": [self.regimes[key].to_dict() for key in sorted(self.regimes)],
        }


def fit_source(
    decisions: Sequence[Decision],
    source_id: str,
    horizon_minutes: int,
    *,
    prior_windows: float = DEFAULT_PRIOR_WINDOWS,
    min_regime_effective: float = DEFAULT_MIN_REGIME_EFFECTIVE,
) -> SourceModel:
    counts, calls = call_counts(decisions, source_id, horizon_minutes)
    pooled = likelihood_ratios(counts, prior_windows=prior_windows)
    regimes: dict[str, RegimeRatios] = {}
    for regime in sorted({d.regime for d in decisions if d.moved and source_id in d.calls}):
        regime_counts, regime_calls = call_counts(
            (d for d in decisions if d.regime == regime), source_id, horizon_minutes
        )
        conditioned = regime_counts.windows >= min_regime_effective
        ratios = pooled
        if conditioned:
            ratios = likelihood_ratios(
                regime_counts,
                prior_windows=prior_windows,
                prior=_other_regimes(decisions, source_id, regime, horizon_minutes, prior_windows),
            )
        regimes[regime] = RegimeRatios(regime, regime_calls, regime_counts.windows, conditioned, ratios)
    return SourceModel(source_id, calls, counts, pooled, regimes)


def _other_regimes(
    decisions: Sequence[Decision], source_id: str, regime: str, horizon_minutes: int, prior_windows: float
) -> tuple[float, float] | None:
    """(P(up call | rose), P(up call | fell)) outside ``regime``; None when the source never called elsewhere."""
    counts, calls = call_counts((d for d in decisions if d.regime != regime), source_id, horizon_minutes)
    if not calls:
        return None
    others = likelihood_ratios(counts, prior_windows=prior_windows)
    return others.p_up_call_when_rose, others.p_up_call_when_fell


@dataclass(frozen=True)
class CombinationModel:
    prior: BaseRate
    sources: Mapping[str, SourceModel]
    pairs: Mapping[tuple[str, str], PairDependence]

    def redundancy(self, first: str, second: str) -> float:
        """A pair never measured together is treated as redundant: no evidence of independence, no double vote."""
        if first == second:
            return 1.0
        pair = self.pairs.get((first, second) if first < second else (second, first))
        return pair.redundancy if pair is not None else 1.0

    def contributions(self, decision: Decision) -> dict[str, float]:
        """ln LR of each call made by a source with a fitting record; anything else contributes nothing."""
        out: dict[str, float] = {}
        for source_id in sorted(decision.calls):
            source = self.sources.get(source_id)
            if source is None or not source.has_record:
                continue
            out[source_id] = source.ratios_for(decision.regime).log_ratio(decision.calls[source_id])
        return out

    def predict(self, decision: Decision, *, adjust_dependence: bool = True) -> Combined:
        redundancy = self.redundancy if adjust_dependence else None
        return combine_log_odds(self.prior.log_odds, self.contributions(decision), redundancy)


def fit_model(
    decisions: Sequence[Decision],
    horizon_minutes: int,
    source_ids: Iterable[str] | None = None,
    *,
    prior_windows: float = DEFAULT_PRIOR_WINDOWS,
    min_regime_effective: float = DEFAULT_MIN_REGIME_EFFECTIVE,
) -> CombinationModel:
    """Base rate, every source's LRs and every pair's dependence, from the fitting decisions only."""
    ids = sorted(set(source_ids) if source_ids is not None else {s for d in decisions for s in d.calls})
    sources = {
        source_id: fit_source(
            decisions,
            source_id,
            horizon_minutes,
            prior_windows=prior_windows,
            min_regime_effective=min_regime_effective,
        )
        for source_id in ids
    }
    # A source with no fitting record never contributes, so its pairs would only be noise in the report.
    recorded = [source_id for source_id in ids if sources[source_id].has_record]
    pairs: dict[tuple[str, str], PairDependence] = {}
    for index, first in enumerate(recorded):
        for second in recorded[index + 1:]:
            polarity = polarity_of(sources[first].pooled.swing) * polarity_of(sources[second].pooled.swing)
            pairs[(first, second)] = pair_dependence(
                decisions, first, second, horizon_minutes, polarity, prior_windows
            )
    return CombinationModel(base_rate(decisions, horizon_minutes), sources, pairs)
