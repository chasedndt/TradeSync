"""Odds arithmetic for combining evidence.

    log odds(p) = ln(p / (1 - p))          p = 1 / (1 + exp(-log odds))

Odds multiply by a likelihood ratio; log odds add its logarithm. So Bayes' rule
with several sources is a sum: the prior's log odds plus each source's log LR,
each multiplied by its redundancy weight. With every weight 1 this is naive
Bayes, which is right only when the sources are conditionally independent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from .evidence_combination_dependence import Redundancy, redundancy_weights


def logit(probability: float) -> float:
    if not 0 < probability < 1:
        raise ValueError("probability must be strictly between 0 and 1")
    return math.log(probability / (1.0 - probability))


def sigmoid(log_odds: float) -> float:
    """The probability for a log odds, without overflow at either extreme."""
    if log_odds >= 0:
        return 1.0 / (1.0 + math.exp(-log_odds))
    exp = math.exp(log_odds)
    return exp / (1.0 + exp)


@dataclass(frozen=True)
class Combined:
    """One decision's combined forecast and how it was built."""

    prior_log_odds: float
    log_odds: float
    probability: float
    contributions: Mapping[str, float]
    weights: Mapping[str, float]

    @property
    def evidence(self) -> float:
        """How far the sources moved the log odds away from the prior."""
        return self.log_odds - self.prior_log_odds


def combine_log_odds(
    prior_log_odds: float,
    contributions: Mapping[str, float],
    redundancy: Redundancy | None = None,
) -> Combined:
    """Prior log odds plus weighted log LRs. ``redundancy=None`` weights every source 1 (naive Bayes)."""
    if redundancy is None:
        weights = {source: 1.0 for source in contributions}
    else:
        weights = redundancy_weights(contributions, redundancy)
    log_odds = prior_log_odds + sum(weights[source] * value for source, value in contributions.items())
    return Combined(prior_log_odds, log_odds, sigmoid(log_odds), dict(contributions), weights)
