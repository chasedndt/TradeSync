"""Score probability forecasts against what happened: Brier score, log loss, reliability.

For a forecast p that the market rises and an outcome y (1 rose, 0 fell):

- Brier score: (p - y)^2, averaged. 0 is perfect; always saying 1/2 scores 0.25.
- Log loss: -[y ln p + (1 - y) ln(1 - p)], averaged. Always saying 1/2 scores
  ln 2 = 0.6931. It punishes a confident mistake far harder than Brier does.
- Reliability: forecasts are sorted and cut into bins of about equal count
  (identical forecasts are never split); in each bin the mean forecast is set
  beside the share that rose, with a Wilson interval at the bin's effective
  windows. A calibrated forecaster's bins sit on the diagonal.
- Murphy's decomposition over those bins:
  Brier ~ reliability - resolution + uncertainty. Reliability is the
  count-weighted squared gap between forecast and outcome (lower is better
  calibrated); resolution is how far the bins' outcomes sit from the overall
  rate (higher is sharper); uncertainty is y_bar (1 - y_bar), which no
  forecaster controls. Exact when every forecast in a bin is the same.
- Calibration error: the count-weighted mean |forecast - share that rose| over
  the bins, in probability units.

A difference between two forecasters is taken decision by decision (paired), and
its mean carries an interval at the test window's effective windows
(``learning_stats.mean_interval``): overlapping windows are not independent
evidence that one forecaster is better.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from .learning_stats import Z_95, effective_sample_size, mean_interval, wilson_interval

PROBABILITY_CLIP = 1e-6
DEFAULT_BINS = 5


def _check(probabilities: Sequence[float], outcomes: Sequence[int]) -> None:
    if len(probabilities) != len(outcomes):
        raise ValueError("one outcome per forecast")
    if any(not 0.0 <= p <= 1.0 for p in probabilities):
        raise ValueError("forecasts must be probabilities")
    if any(y not in (0, 1) for y in outcomes):
        raise ValueError("outcomes are 1 (rose) or 0 (fell)")


def brier_terms(probabilities: Sequence[float], outcomes: Sequence[int]) -> list[float]:
    _check(probabilities, outcomes)
    return [(p - y) ** 2 for p, y in zip(probabilities, outcomes)]


def log_loss_terms(probabilities: Sequence[float], outcomes: Sequence[int]) -> list[float]:
    """Per-decision log loss; forecasts are clipped to [1e-6, 1 - 1e-6] so one certainty cannot be infinite."""
    _check(probabilities, outcomes)
    out = []
    for p, y in zip(probabilities, outcomes):
        clipped = min(max(p, PROBABILITY_CLIP), 1.0 - PROBABILITY_CLIP)
        out.append(-math.log(clipped) if y else -math.log(1.0 - clipped))
    return out


def equal_count_bins(probabilities: Sequence[float], bins: int = DEFAULT_BINS) -> list[list[int]]:
    """Indices sorted by forecast, cut into at most ``bins`` groups of about equal count."""
    if bins < 1:
        raise ValueError("bins must be at least 1")
    n = len(probabilities)
    order = sorted(range(n), key=lambda i: (probabilities[i], i))
    groups: list[list[int]] = []
    start = 0
    for k in range(1, bins + 1):
        end = n if k == bins else max(start, round(k * n / bins))
        while 0 < end < n and probabilities[order[end]] == probabilities[order[end - 1]]:
            end += 1
        if end > start:
            groups.append(order[start:end])
            start = end
    return groups


@dataclass(frozen=True)
class ReliabilityBin:
    decisions: int
    effective_windows: float
    mean_probability: float
    rise_share: float
    low: float | None
    high: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": self.decisions,
            "effective_windows": round(self.effective_windows, 3),
            "mean_probability": round(self.mean_probability, 6),
            "rise_share": round(self.rise_share, 6),
            "low": None if self.low is None else round(self.low, 6),
            "high": None if self.high is None else round(self.high, 6),
        }


@dataclass(frozen=True)
class ForecastScore:
    decisions: int
    brier: float
    log_loss: float
    mean_probability: float
    rise_share: float
    reliability: float
    resolution: float
    uncertainty: float
    calibration_error: float
    bins: tuple[ReliabilityBin, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": self.decisions,
            "brier": round(self.brier, 6),
            "log_loss": round(self.log_loss, 6),
            "mean_probability": round(self.mean_probability, 6),
            "rise_share": round(self.rise_share, 6),
            "reliability": round(self.reliability, 6),
            "resolution": round(self.resolution, 6),
            "uncertainty": round(self.uncertainty, 6),
            "calibration_error": round(self.calibration_error, 6),
            "bins": [item.to_dict() for item in self.bins],
        }


def score_forecast(
    probabilities: Sequence[float],
    outcomes: Sequence[int],
    opened_at_s: Sequence[int],
    horizon_minutes: int,
    *,
    bins: int = DEFAULT_BINS,
    z: float = Z_95,
) -> ForecastScore:
    if not probabilities:
        raise ValueError("nothing to score")
    if len(opened_at_s) != len(probabilities):
        raise ValueError("one opening time per forecast")
    brier = sum(brier_terms(probabilities, outcomes)) / len(probabilities)
    log_loss = sum(log_loss_terms(probabilities, outcomes)) / len(probabilities)
    n = len(probabilities)
    rise = sum(outcomes) / n
    table: list[ReliabilityBin] = []
    reliability = resolution = calibration = 0.0
    for group in equal_count_bins(probabilities, bins):
        count = len(group)
        forecast = sum(probabilities[i] for i in group) / count
        observed = sum(outcomes[i] for i in group) / count
        effective = effective_sample_size([opened_at_s[i] for i in group], horizon_minutes)
        interval = wilson_interval(observed, effective, z) if effective > 0 else None
        share = count / n
        reliability += share * (forecast - observed) ** 2
        resolution += share * (observed - rise) ** 2
        calibration += share * abs(forecast - observed)
        table.append(ReliabilityBin(
            count, effective, forecast, observed,
            interval[0] if interval else None, interval[1] if interval else None,
        ))
    return ForecastScore(
        n, brier, log_loss, sum(probabilities) / n, rise,
        reliability, resolution, rise * (1.0 - rise), calibration, tuple(table),
    )


@dataclass(frozen=True)
class PairedDifference:
    candidate: str
    baseline: str
    metric: str
    mean: float
    low: float | None
    high: float | None
    effective_windows: float

    @property
    def verdict(self) -> str:
        """Lower loss is better: the whole interval below zero is 'better', above zero 'worse'."""
        if self.low is None or self.high is None:
            return "not_measurable"
        if self.high < 0:
            return "better"
        if self.low > 0:
            return "worse"
        return "not_distinguishable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "baseline": self.baseline,
            "metric": self.metric,
            "mean_difference": round(self.mean, 6),
            "low": None if self.low is None else round(self.low, 6),
            "high": None if self.high is None else round(self.high, 6),
            "effective_windows": round(self.effective_windows, 3),
            "verdict": self.verdict,
        }


def paired_difference(
    candidate: str,
    baseline: str,
    metric: str,
    candidate_terms: Sequence[float],
    baseline_terms: Sequence[float],
    effective: float,
    z: float = Z_95,
) -> PairedDifference:
    """Mean of candidate minus baseline per decision, with an interval at ``effective`` windows."""
    if len(candidate_terms) != len(baseline_terms):
        raise ValueError("paired terms must line up")
    measured = mean_interval([c - b for c, b in zip(candidate_terms, baseline_terms)], effective, z)
    if measured is None:
        raise ValueError("nothing to compare")
    mean, low, high = measured
    return PairedDifference(candidate, baseline, metric, mean, low, high, effective)
