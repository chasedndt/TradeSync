"""The rulebook's directional score, given its fairest chance to be a probability.

The score is a weighted average of normalised readings between -1 and +1. It is
not a probability: reading +0.3 as "65% up" has no basis. To compare it with a
probability fairly it is calibrated on the same fitting decisions the
combination learns from (Platt scaling):

    P(rise | score s) = 1 / (1 + exp(-(a + b s)))

a and b maximise the log likelihood of the fitting outcomes, with the same doubt
used everywhere else in evidence combination:

- rows are weighted so the data counts as its effective windows, not its raw
  decisions;
- half an imaginary rise and half a fall at s = 0 keep a finite;
- the slope b has a Gaussian prior at 0 worth ``prior_windows`` windows: its
  precision is prior_windows x 0.25 x mean(s^2), the information that many
  windows would hold about b near p = 1/2.

A score that carries nothing keeps b near 0 and forecasts close to the base rate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from .evidence_combination_data import Decision, effective_windows
from .evidence_combination_likelihood import DEFAULT_PRIOR_WINDOWS
from .evidence_combination_odds import sigmoid

FISHER_AT_HALF = 0.25
MAX_ITERATIONS = 100
TOLERANCE = 1e-10


@dataclass(frozen=True)
class ScoreCalibration:
    intercept: float
    slope: float
    decisions: int
    effective_windows: float
    slope_prior_precision: float

    def probability(self, score: float | None, fallback: float) -> float:
        """The calibrated chance of a rise; ``fallback`` (the base rate) for a decision with no score."""
        if score is None or not math.isfinite(score):
            return fallback
        return sigmoid(self.intercept + self.slope * score)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intercept": round(self.intercept, 6),
            "slope": round(self.slope, 6),
            "decisions": self.decisions,
            "effective_windows": round(self.effective_windows, 3),
            "slope_prior_precision": round(self.slope_prior_precision, 6),
        }


def calibrate_score(
    decisions: Sequence[Decision],
    horizon_minutes: int,
    *,
    prior_windows: float = DEFAULT_PRIOR_WINDOWS,
) -> ScoreCalibration | None:
    """Penalised logistic fit of rise on the rulebook score; None when no fitting decision has a score."""
    scored = [
        d for d in decisions
        if d.moved and d.rulebook_score is not None and math.isfinite(d.rulebook_score)
    ]
    if not scored:
        return None
    effective = effective_windows(scored, horizon_minutes)
    weight = effective / len(scored)
    rows = [(float(d.rulebook_score), float(d.outcome), weight) for d in scored]
    precision = prior_windows * FISHER_AT_HALF * sum(score * score for score, _, _ in rows) / len(rows)
    rows += [(0.0, 1.0, 0.5), (0.0, 0.0, 0.5)]

    intercept = slope = 0.0
    for _ in range(MAX_ITERATIONS):
        grad_a, grad_b = 0.0, -precision * slope
        h_aa, h_ab, h_bb = 0.0, 0.0, precision
        for score, outcome, row_weight in rows:
            p = sigmoid(intercept + slope * score)
            residual = row_weight * (outcome - p)
            grad_a += residual
            grad_b += residual * score
            curvature = row_weight * p * (1.0 - p)
            h_aa += curvature
            h_ab += curvature * score
            h_bb += curvature * score * score
        determinant = h_aa * h_bb - h_ab * h_ab
        if h_bb <= TOLERANCE or determinant <= TOLERANCE:
            # No spread in the scores: only the intercept can learn anything.
            step_a, step_b = grad_a / h_aa, 0.0
        else:
            step_a = (h_bb * grad_a - h_ab * grad_b) / determinant
            step_b = (h_aa * grad_b - h_ab * grad_a) / determinant
        intercept += step_a
        slope += step_b
        if abs(step_a) < TOLERANCE and abs(step_b) < TOLERANCE:
            break
    return ScoreCalibration(intercept, slope, len(scored), effective, precision)
