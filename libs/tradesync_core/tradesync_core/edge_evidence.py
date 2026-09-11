"""Keep "the measurement can see something" apart from "there is an edge worth having".

The first skill endpoint reported one flag, ``significant``, that was true when
the absolute skill cleared two standard errors. A sufficiently *negative* skill
therefore read as significant too. Codex's review of 2026-09-09 found this, and
that nothing was net of costs, nothing was held out, and six cells were tested
at once with no allowance for that. Each is corrected here, as three separate
verdicts that must never be collapsed into one:

- ``detectable``      |z| >= 2 either way. Descriptive: the sample can tell this
                      apart from zero. A detectably *bad* signal is detectable.
- ``positive_skill``  skill > 0 at one-sided 2.5%, Holm-adjusted across every
                      cell assessed together, and |z| >= 2. Six horizon/regime
                      cells tested at 2.5% each will throw up a false positive
                      often enough that an unadjusted one is not a finding.
- ``economic_edge``   positive skill AND a positive mean return after stated
                      costs. ``None`` when no costs were supplied: an edge that
                      has not been costed cannot be declared either way.

None of these is trading readiness. Gates stay closed on this module's output
alone; it only describes evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from .independence import (
    Observation,
    binomial_se,
    block_bootstrap_skill_se,
    independent_counts,
    skill_of,
)

ALPHA_ONE_SIDED = 0.025
DETECTABLE_Z = 2.0
DEFAULT_HOLDOUT_FRACTION = 0.30


@dataclass(frozen=True)
class CostAssumptions:
    """Round-trip trading costs, as percentages of notional.

    ``source`` is required so a cost figure can never appear without saying
    where it came from. Funding is not included here: it depends on the side
    and the hold, and is applied per observation once it is recorded.
    """

    round_trip_fee_pct: float
    spread_pct: float
    slippage_pct: float
    source: str

    def __post_init__(self) -> None:
        for name in ("round_trip_fee_pct", "spread_pct", "slippage_pct"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if not self.source.strip():
            raise ValueError("costs must name their source")

    @property
    def total_pct(self) -> float:
        return self.round_trip_fee_pct + self.spread_pct + self.slippage_pct


def chronological_split(
    observations: Sequence[Observation], holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION
) -> tuple[list[Observation], list[Observation]]:
    """Earliest observations in-sample, latest held out. Never shuffled.

    A shuffled split leaks the future into the past; a real edge has to survive
    being measured on data that came after the period it was noticed in.
    """
    if not 0 < holdout_fraction < 1:
        raise ValueError("holdout_fraction must be in (0, 1)")
    ordered = sorted(observations, key=lambda o: (o.opened_at_s, o.symbol))
    cut = len(ordered) - math.ceil(len(ordered) * holdout_fraction)
    return ordered[:cut], ordered[cut:]


@dataclass
class CellEvidence:
    label: str
    horizon_minutes: int
    measured: int
    independent_per_symbol: int
    independent_pooled: int
    hit_rate: float | None
    market_up_rate: float | None
    long_share: float | None
    expected_hit_rate: float | None
    skill: float | None
    se_binomial_pooled: float | None
    se_block_bootstrap: float | None
    standard_error: float | None
    z: float | None
    p_two_sided: float | None
    p_positive: float | None
    detectable: bool
    mean_signed_return_pct: float | None
    mean_net_return_pct: float | None
    in_sample_skill: float | None
    holdout_skill: float | None
    holdout_measured: int
    positive_skill: bool = False
    economic_edge: bool | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out = {k: v for k, v in self.__dict__.items()}
        out["readiness"] = "descriptive evidence only; not trading readiness"
        return out


def _normal_upper_tail(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def assess_cell(
    label: str,
    observations: Sequence[Observation],
    horizon_minutes: int,
    *,
    costs: CostAssumptions | None = None,
    holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION,
    draws: int = 1000,
    seed: int = 0,
) -> CellEvidence:
    """Everything the sample says about one horizon/regime cell, before adjustment.

    ``positive_skill`` and ``economic_edge`` are left unset here; they depend on
    how many cells were tested and are filled in by ``assess_cells``.
    """
    counts = independent_counts(observations, horizon_minutes)
    measured = skill_of(observations)
    se_pooled = binomial_se(counts["pooled"])
    se_boot = block_bootstrap_skill_se(observations, horizon_minutes, draws=draws, seed=seed)
    # The larger error is the one decisions use: the conservative choice.
    available = [se for se in (se_pooled, se_boot) if se is not None]
    se = max(available) if available else None

    skill = measured["skill"] if measured else None
    z = skill / se if skill is not None and se else None
    notes: list[str] = []

    mean_signed = (
        sum(o.signed_return_pct for o in observations) / len(observations)
        if observations
        else None
    )
    mean_net = None
    if costs is not None and mean_signed is not None:
        mean_net = mean_signed - costs.total_pct
        notes.append(f"costs from {costs.source}; funding not yet included")
    elif costs is None:
        notes.append("no costs supplied; economic edge cannot be assessed")

    if len(observations) >= 2:
        in_sample, holdout = chronological_split(observations, holdout_fraction)
    else:
        in_sample, holdout = list(observations), []
    in_skill = skill_of(in_sample)
    out_skill = skill_of(holdout)
    if in_skill and out_skill and (in_skill["skill"] > 0) != (out_skill["skill"] > 0):
        notes.append("in-sample and held-out skill disagree in sign")

    if counts["pooled"] < counts["per_symbol"]:
        notes.append(
            f"{counts['per_symbol']} independent windows per symbol, "
            f"{counts['pooled']} with symbols pooled; the pooled count sets the error"
        )

    return CellEvidence(
        label=label,
        horizon_minutes=horizon_minutes,
        measured=len(observations),
        independent_per_symbol=counts["per_symbol"],
        independent_pooled=counts["pooled"],
        hit_rate=measured["hit_rate"] if measured else None,
        market_up_rate=measured["market_up_rate"] if measured else None,
        long_share=measured["long_share"] if measured else None,
        expected_hit_rate=measured["expected_hit_rate"] if measured else None,
        skill=skill,
        se_binomial_pooled=se_pooled,
        se_block_bootstrap=se_boot,
        standard_error=se,
        z=z,
        p_two_sided=2 * _normal_upper_tail(abs(z)) if z is not None else None,
        p_positive=_normal_upper_tail(z) if z is not None else None,
        detectable=z is not None and abs(z) >= DETECTABLE_Z,
        mean_signed_return_pct=mean_signed,
        mean_net_return_pct=mean_net,
        in_sample_skill=in_skill["skill"] if in_skill else None,
        holdout_skill=out_skill["skill"] if out_skill else None,
        holdout_measured=len(holdout),
        notes=notes,
    )


def apply_holm(cells: Sequence[CellEvidence], alpha: float = ALPHA_ONE_SIDED) -> None:
    """Holm step-down over every cell's one-sided p-value for positive skill.

    Sorted ascending, the k-th smallest p must clear ``alpha / (m - k)``; the
    first that fails stops the procedure, and every larger p fails with it.
    """
    # Reset first: a verdict from an earlier, smaller set of cells must not
    # survive into a larger one, where the bar is higher.
    for cell in cells:
        cell.positive_skill = False
    tested = sorted((c for c in cells if c.p_positive is not None), key=lambda c: c.p_positive)
    m = len(tested)
    for rank, cell in enumerate(tested):
        if cell.p_positive > alpha / (m - rank):
            break
        cell.positive_skill = cell.z is not None and cell.z >= DETECTABLE_Z
    for cell in cells:
        if cell.mean_net_return_pct is None:
            cell.economic_edge = None
        else:
            cell.economic_edge = cell.positive_skill and cell.mean_net_return_pct > 0


def assess_cells(
    cells: Sequence[tuple[str, int, Sequence[Observation]]],
    *,
    costs: CostAssumptions | None = None,
    holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION,
    draws: int = 1000,
    seed: int = 0,
) -> list[CellEvidence]:
    """Assess ``(label, horizon_minutes, observations)`` cells together.

    Together is the point: the multiple-comparison adjustment is only honest if
    it sees every cell that was looked at, not just the promising ones.
    """
    assessed = [
        assess_cell(
            label,
            obs,
            horizon,
            costs=costs,
            holdout_fraction=holdout_fraction,
            draws=draws,
            seed=seed,
        )
        for label, horizon, obs in cells
    ]
    apply_holm(assessed)
    return assessed
