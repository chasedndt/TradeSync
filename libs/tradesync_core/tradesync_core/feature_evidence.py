"""Does a feature, read at entry, say anything about what happened next?

This is the measurement behind an evidence card. Each candidate feature is
turned into a guesser: its sign at entry is the direction it would have
called (positive reads LONG, negative reads SHORT, zero abstains), and that
call is scored against the opportunity's forward return exactly as the paper
signal's own calls are scored in ``edge_evidence``. Both polarities are tested,
because a feature can be usefully contrarian, and both go through the same
Holm adjustment as every other cell so that testing twice as many cells is
paid for.

A weight is *earned* when one polarity shows positive skill at some horizon
and that skill survives the chronological hold-out. Earned is not granted:
the catalog's ``scoring_eligible`` flag changes only by operator decision,
and this module only reports what the evidence supports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .edge_evidence import CellEvidence, CostAssumptions, assess_cells
from .independence import Observation

POLARITIES = (("as_read", 1), ("inverted", -1))
EARNED_MEANING = (
    "earned = positive skill (Holm-adjusted with every cell here) that also "
    "held out of sample; granting a weight stays an operator decision"
)


@dataclass(frozen=True)
class FeatureOutcomeRow:
    """One outcome joined to one feature's entry reading."""

    feature_id: str
    symbol: str
    opened_at_s: int
    horizon_minutes: int
    forward_return_pct: float
    value: float


def as_guesser(row: FeatureOutcomeRow, polarity: int) -> Observation | None:
    """The feature's sign as a directional call. Zero abstains."""
    signed_value = row.value * polarity
    if signed_value == 0:
        return None
    direction = "LONG" if signed_value > 0 else "SHORT"
    signed = row.forward_return_pct if direction == "LONG" else -row.forward_return_pct
    return Observation(
        symbol=row.symbol,
        opened_at_s=row.opened_at_s,
        direction=direction,
        forward_return_pct=row.forward_return_pct,
        signed_return_pct=signed,
    )


def group_cells(
    rows: Iterable[FeatureOutcomeRow],
) -> dict[tuple[str, int, str], list[Observation]]:
    """(feature, horizon, polarity) -> the feature's calls as observations."""
    cells: dict[tuple[str, int, str], list[Observation]] = {}
    for row in rows:
        for name, sign in POLARITIES:
            obs = as_guesser(row, sign)
            if obs is not None:
                cells.setdefault((row.feature_id, row.horizon_minutes, name), []).append(obs)
    return cells


@dataclass
class FeatureCard:
    feature_id: str
    cells: list[dict[str, Any]] = field(default_factory=list)
    earned: bool = False
    earned_by: list[str] = field(default_factory=list)
    abstained: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "cells": self.cells,
            "earned": self.earned,
            "earned_by": self.earned_by,
            "abstained": self.abstained,
            "meaning": EARNED_MEANING,
        }


def earned_by(cell: CellEvidence) -> bool:
    """Positive skill that also held on the chronological hold-out."""
    return bool(cell.positive_skill) and cell.holdout_skill is not None and cell.holdout_skill > 0


def assess_feature_cards(
    rows: Sequence[FeatureOutcomeRow],
    feature_ids: Sequence[str],
    *,
    costs: CostAssumptions | None,
    draws: int = 400,
    seed: int = 0,
) -> tuple[list[FeatureCard], int]:
    """One card per feature; every cell of every card assessed together.

    Returns the cards (catalog order first, then any feature seen in the rows
    but not listed) and the number of cells the adjustment saw.
    """
    cells = group_cells(rows)
    keys = sorted(cells.keys())
    assessed = assess_cells(
        [(f"{f} {h}m {p}", h, cells[(f, h, p)]) for (f, h, p) in keys],
        costs=costs,
        draws=draws,
        seed=seed,
    )

    cards: dict[str, FeatureCard] = {f: FeatureCard(feature_id=f) for f in feature_ids}
    for row in rows:
        card = cards.setdefault(row.feature_id, FeatureCard(feature_id=row.feature_id))
        if row.value == 0:
            card.abstained += 1

    for (feature_id, horizon, polarity), cell in zip(keys, assessed):
        card = cards[feature_id]
        d = cell.to_dict()
        d["horizon_minutes"], d["polarity"] = horizon, polarity
        d["earned"] = earned_by(cell)
        card.cells.append(d)
        if d["earned"]:
            card.earned = True
            card.earned_by.append(f"{horizon}m {polarity}")

    ordered = [cards[f] for f in feature_ids]
    ordered += [c for f, c in cards.items() if f not in feature_ids]
    return ordered, len(assessed)


def catalog_standing(spec: Mapping[str, Any]) -> str:
    """How the catalog currently treats the feature: scoring or context-only."""
    return "scoring" if spec.get("scoring_eligible") else "context_only"
