"""How far one source's call should move the odds, measured from its own record.

A source calls up or down. Over the windows where it called, the market rose in
some and fell in others. The likelihood ratio (LR) of a call is how much more
often the source made that call before a rise than before a fall:

    LR(up call)   = P(up call | rose)   / P(up call | fell)
    LR(down call) = P(down call | rose) / P(down call | fell)

Bayes' rule in odds form: posterior odds of a rise = prior odds x LR of the call
that was made. An LR of 1 changes nothing; above 1 the call favours a rise,
below 1 a fall. A source whose up calls tend to come before falls has
LR(up call) < 1: it is contrarian, and the ratio says so without a separate
polarity test.

Each conditional probability is estimated with Beta-binomial shrinkage. Before
any data, act as if ``prior_windows`` effective windows, half rises and half
falls, had shown the source calling up at its usual rate whatever the market
did. Both probabilities then equal that rate and every LR is exactly 1. Data
pulls each probability away from the rate in proportion to how many effective
windows back it: at ``prior_windows`` effective windows the data carries half
the weight. No evidence means no update; thin evidence means a small one.

Counts are *effective* counts. Calls a few minutes apart share most of their
window, so raw counts are first scaled by effective windows / calls. The
interval is a normal approximation on the log scale (the delta method) from the
two Beta posteriors, which are independent because they use disjoint windows.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .learning_stats import Z_95

DEFAULT_PRIOR_WINDOWS = 20.0


@dataclass(frozen=True)
class CallCounts:
    """One source's calls split by what the market then did. Counts may be fractional."""

    rose: float
    up_calls_when_rose: float
    fell: float
    up_calls_when_fell: float

    def __post_init__(self) -> None:
        for name in ("rose", "up_calls_when_rose", "fell", "up_calls_when_fell"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a non-negative number")
        if self.up_calls_when_rose > self.rose * (1 + 1e-12) or self.up_calls_when_fell > self.fell * (1 + 1e-12):
            raise ValueError("up calls cannot exceed the windows they were made in")

    @property
    def windows(self) -> float:
        return self.rose + self.fell

    @property
    def up_call_share(self) -> float:
        """The source's usual up-call rate, with one imaginary up and one down call: never 0 or 1."""
        return (self.up_calls_when_rose + self.up_calls_when_fell + 1.0) / (self.windows + 2.0)

    def scaled(self, factor: float) -> "CallCounts":
        if not math.isfinite(factor) or factor < 0:
            raise ValueError("factor must be a non-negative number")
        return CallCounts(
            self.rose * factor,
            min(self.up_calls_when_rose * factor, self.rose * factor),
            self.fell * factor,
            min(self.up_calls_when_fell * factor, self.fell * factor),
        )


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float

    @property
    def excludes_one(self) -> bool:
        return self.low > 1.0 or self.high < 1.0

    def to_dict(self) -> dict[str, float]:
        return {"estimate": round(self.estimate, 6), "low": round(self.low, 6), "high": round(self.high, 6)}


def shrunk_probability(successes: float, trials: float, prior_mean: float, prior_windows: float) -> float:
    """(successes + prior_windows x prior_mean) / (trials + prior_windows): the Beta posterior mean."""
    if prior_windows <= 0:
        raise ValueError("prior_windows must be positive")
    if not 0 < prior_mean < 1:
        raise ValueError("prior_mean must be strictly between 0 and 1")
    return (successes + prior_windows * prior_mean) / (trials + prior_windows)


def log_variance(probability: float, strength: float) -> float:
    """Var[ln theta] for theta ~ Beta with this mean and alpha + beta = ``strength`` (delta method)."""
    return (1.0 - probability) / (probability * (strength + 1.0))


def _ratio(numerator: float, denominator: float, variance: float, z: float) -> Interval:
    log_estimate = math.log(numerator / denominator)
    half = z * math.sqrt(variance)
    return Interval(math.exp(log_estimate), math.exp(log_estimate - half), math.exp(log_estimate + half))


@dataclass(frozen=True)
class LikelihoodRatios:
    """Shrunk LRs of both calls, with the probabilities they came from."""

    up_call: Interval
    down_call: Interval
    p_up_call_when_rose: float
    p_up_call_when_fell: float
    effective_windows: float

    def log_ratio(self, call: int) -> float:
        """ln LR of the call made: +1 for an up call, -1 for a down call."""
        if call not in (1, -1):
            raise ValueError("a call is +1 (up) or -1 (down)")
        return math.log(self.up_call.estimate if call > 0 else self.down_call.estimate)

    @property
    def swing(self) -> float:
        """ln LR(up call) - ln LR(down call): above 0 follows the market, below 0 is contrarian."""
        return self.log_ratio(1) - self.log_ratio(-1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "up_call": self.up_call.to_dict(),
            "down_call": self.down_call.to_dict(),
            "p_up_call_when_rose": round(self.p_up_call_when_rose, 6),
            "p_up_call_when_fell": round(self.p_up_call_when_fell, 6),
            "effective_windows": round(self.effective_windows, 3),
        }


def likelihood_ratios(
    counts: CallCounts,
    *,
    prior_windows: float = DEFAULT_PRIOR_WINDOWS,
    prior: tuple[float, float] | None = None,
    z: float = Z_95,
) -> LikelihoodRatios:
    """Shrunk LRs of an up call and a down call, each with an interval.

    ``prior`` is the pair (P(up call | rose), P(up call | fell)) to shrink toward.
    By default both are the source's usual up-call rate, so no data gives LR 1.
    A regime's estimate passes the pooled pair instead, so no regime data gives
    the pooled LR. Each probability gets half of ``prior_windows``.
    """
    half = prior_windows / 2.0
    share = counts.up_call_share
    prior_rose, prior_fell = prior if prior is not None else (share, share)
    rose = shrunk_probability(counts.up_calls_when_rose, counts.rose, prior_rose, half)
    fell = shrunk_probability(counts.up_calls_when_fell, counts.fell, prior_fell, half)
    strength_rose, strength_fell = counts.rose + half, counts.fell + half
    up = _ratio(rose, fell, log_variance(rose, strength_rose) + log_variance(fell, strength_fell), z)
    down = _ratio(
        1.0 - rose,
        1.0 - fell,
        log_variance(1.0 - rose, strength_rose) + log_variance(1.0 - fell, strength_fell),
        z,
    )
    return LikelihoodRatios(up, down, rose, fell, counts.windows)


def unshrunk_ratios(counts: CallCounts) -> tuple[float | None, float | None]:
    """The plain LRs from the counts alone, for comparison; None where a count leaves one undefined."""
    if counts.rose <= 0 or counts.fell <= 0:
        return None, None
    rose = counts.up_calls_when_rose / counts.rose
    fell = counts.up_calls_when_fell / counts.fell
    up = rose / fell if fell > 0 else None
    down = (1.0 - rose) / (1.0 - fell) if fell < 1 else None
    return up, down
