"""When two sources say the same thing, count it once.

Adding log likelihood ratios assumes each source's calls are independent of the
others once the market's direction is known (conditional independence). Two
sources that both track the market agree more often than chance simply because
both are right more often; that agreement is not redundancy. Redundancy is the
agreement left over *within* the rising windows and *within* the falling
windows: the residual correlation of their calls.

It is measured on the fitting windows where both sources called, with each
source's calls centred within each outcome class and the cross-products pooled
over the two classes. It is then shrunk toward 1, full redundancy, with the same
prior windows as the likelihood ratios:

    rho_shrunk = (shared effective windows x rho + prior windows x 1) / (shared effective windows + prior windows)

With no shared windows two sources are treated as the same evidence; only shared
windows that show them varying separately earn them separate votes. A source
that follows the market and a contrarian one repeat each other when their calls
are *negatively* correlated, so the correlation is signed by the product of the
two sources' polarities (the sign of each one's swing).

On one decision, source i's log LR is multiplied by the weight 1 / R_i, where

    R_i = 1 + sum over other present sources j of  max(0, rho_ij) x min(1, |l_j| / |l_i|)

one for itself, plus, for every other source present, the share of i's evidence
that source could be repeating: at most their correlation, and never more than
the evidence that source is itself giving. Two exact copies each get weight 1/2,
so together they count once. Independent sources keep weight 1. k equally
strong sources with a common correlation rho each get 1 / (1 + (k - 1) rho),
Kish's effective number. A source with nothing to say (l = 0) dilutes no one.
The rule is exact at those extremes and a conservative interpolation between
them; it is judged, like everything else here, out of sample.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from .evidence_combination_data import Decision, effective_windows
from .evidence_combination_likelihood import DEFAULT_PRIOR_WINDOWS

REDUNDANT = 1.0
_NO_SPREAD = 1e-12

Redundancy = Callable[[str, str], float]


def residual_correlation(rows: Iterable[tuple[int, int, bool]]) -> float | None:
    """Pooled within-outcome correlation of two sources' calls, from (call_a, call_b, rose) rows.

    None when either source's calls never vary within an outcome class: a call
    that is constant once the outcome is known has nothing left to repeat.
    """
    sums = {True: [0.0] * 6, False: [0.0] * 6}  # n, sum a, sum b, sum aa, sum bb, sum ab
    for a, b, rose in rows:
        total = sums[bool(rose)]
        total[0] += 1
        total[1] += a
        total[2] += b
        total[3] += a * a
        total[4] += b * b
        total[5] += a * b
    s_aa = s_bb = s_ab = 0.0
    for n, sum_a, sum_b, sum_aa, sum_bb, sum_ab in sums.values():
        if n == 0:
            continue
        s_aa += sum_aa - sum_a * sum_a / n
        s_bb += sum_bb - sum_b * sum_b / n
        s_ab += sum_ab - sum_a * sum_b / n
    if s_aa <= _NO_SPREAD or s_bb <= _NO_SPREAD:
        return None
    return max(-1.0, min(1.0, s_ab / math.sqrt(s_aa * s_bb)))


def shrink_toward_redundant(
    correlation: float, effective: float, prior_windows: float = DEFAULT_PRIOR_WINDOWS
) -> float:
    """Pull a measured correlation toward 1 by ``prior_windows`` imaginary shared windows."""
    if prior_windows <= 0:
        raise ValueError("prior_windows must be positive")
    if effective < 0 or not math.isfinite(effective):
        raise ValueError("effective must be a non-negative number")
    return (effective * correlation + prior_windows * REDUNDANT) / (effective + prior_windows)


def polarity_of(swing: float) -> int:
    """+1 follows the market, -1 contrarian, 0 no information."""
    return 1 if swing > 0 else -1 if swing < 0 else 0


@dataclass(frozen=True)
class PairDependence:
    first: str
    second: str
    shared_decisions: int
    shared_effective: float
    residual_correlation: float | None
    polarity: int
    shrunk_correlation: float

    @property
    def redundancy(self) -> float:
        """How much of one source the other can repeat: the shrunk, polarity-signed correlation, floored at 0."""
        return max(0.0, self.shrunk_correlation)

    def to_dict(self) -> dict[str, Any]:
        rho = self.residual_correlation
        return {
            "first": self.first,
            "second": self.second,
            "shared_decisions": self.shared_decisions,
            "shared_effective_windows": round(self.shared_effective, 3),
            "residual_correlation": None if rho is None else round(rho, 6),
            "polarity": self.polarity,
            "shrunk_correlation": round(self.shrunk_correlation, 6),
            "redundancy": round(self.redundancy, 6),
        }


def pair_dependence(
    decisions: Sequence[Decision],
    first: str,
    second: str,
    horizon_minutes: int,
    polarity: int,
    prior_windows: float = DEFAULT_PRIOR_WINDOWS,
) -> PairDependence:
    """Residual correlation of two sources over the windows where both called, signed and shrunk."""
    shared = [d for d in decisions if d.moved and first in d.calls and second in d.calls]
    rho = residual_correlation((d.calls[first], d.calls[second], d.rose) for d in shared)
    effective = effective_windows(shared, horizon_minutes) if shared else 0.0
    signed = polarity * (rho if rho is not None else 0.0)
    return PairDependence(
        first=first,
        second=second,
        shared_decisions=len(shared),
        shared_effective=effective,
        residual_correlation=rho,
        polarity=polarity,
        shrunk_correlation=shrink_toward_redundant(signed, effective, prior_windows),
    )


def redundancy_weights(contributions: Mapping[str, float], redundancy: Redundancy) -> dict[str, float]:
    """Weight 1 / R_i for every contributing source on one decision (see the module docstring)."""
    weights: dict[str, float] = {}
    for source, own in contributions.items():
        if own == 0:
            weights[source] = 1.0
            continue
        total = 1.0
        for other, theirs in contributions.items():
            if other != source:
                total += max(0.0, redundancy(source, other)) * min(1.0, abs(theirs) / abs(own))
        weights[source] = 1.0 / total
    return weights
