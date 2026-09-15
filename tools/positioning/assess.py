"""Join the declared readings to measured outcomes and assess them together, as declared."""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Mapping, Sequence

from tradesync_core.edge_evidence import ALPHA_ONE_SIDED, CostAssumptions
from tradesync_core.feature_evidence import FeatureOutcomeRow, assess_feature_cards

from .candidates import Reading, expected_polarity
from .readings import Entry, Series, signed_readings

DECLARED_CELLS = 120
REFERENCE_SKILLS = (0.10, 0.05)
DAY_S = 86_400


def holm_first_z(cells: int = DECLARED_CELLS, alpha: float = ALPHA_ONE_SIDED) -> float:
    """The z the first-ranked of ``cells`` one-sided tests must reach under Holm."""
    return NormalDist().inv_cdf(1 - alpha / cells)


def windows_needed(skill: float, cells: int = DECLARED_CELLS) -> int:
    """Independent windows for a true ``skill`` to reach that z under the worst-case binomial error."""
    return math.ceil((holm_first_z(cells) / (2 * skill)) ** 2)


def build_rows(
    outcomes: Sequence[Mapping[str, Any]],
    recorded: Mapping[str, Mapping[str, tuple[int, float]]],
    series: Mapping[str, Mapping[str, Series]],
    readings: Sequence[Reading],
    specs: Mapping[str, Mapping[str, Any]],
) -> tuple[list[FeatureOutcomeRow], dict[str, Any]]:
    """One row per (reading, measured outcome) where the reading exists, and per-reading coverage."""
    rows: list[FeatureOutcomeRow] = []
    coverage = {r.reading_id: {"entries": 0, "abstained": 0, "first_entry_s": None, "last_entry_s": None} for r in readings}
    per_entry: dict[str, dict[str, float]] = {}
    for outcome in outcomes:
        opportunity = outcome["opportunity_id"]
        if opportunity not in per_entry:
            entry = Entry(opportunity, outcome["symbol"], outcome["entry_ms"])
            per_entry[opportunity] = values = signed_readings(
                entry, readings, recorded.get(opportunity, {}), series.get(outcome["symbol"], {}), specs
            )
            opened = outcome["opened_at_s"]
            for reading_id, value in values.items():
                c = coverage[reading_id]
                c["entries"] += 1
                c["abstained"] += int(value == 0)
                c["first_entry_s"] = opened if c["first_entry_s"] is None else min(c["first_entry_s"], opened)
                c["last_entry_s"] = opened if c["last_entry_s"] is None else max(c["last_entry_s"], opened)
        for reading_id, value in per_entry[opportunity].items():
            rows.append(FeatureOutcomeRow(reading_id, outcome["symbol"], outcome["opened_at_s"],
                                          outcome["horizon_minutes"], outcome["forward_return_pct"], value))
    return rows, {"opportunities": len(per_entry), "readings": coverage}


def spans_in_days(rows: Sequence[FeatureOutcomeRow]) -> dict[tuple[str, int], float]:
    """Days from the first to the last call (abstains excluded) per (reading, horizon)."""
    first: dict[tuple[str, int], int] = {}
    last: dict[tuple[str, int], int] = {}
    for row in rows:
        if row.value == 0:
            continue
        key = (row.feature_id, row.horizon_minutes)
        first[key] = min(first.get(key, row.opened_at_s), row.opened_at_s)
        last[key] = max(last.get(key, row.opened_at_s), row.opened_at_s)
    return {key: (last[key] - first[key]) / DAY_S for key in first}


def reasons(cell: Mapping[str, Any], needed: int) -> list[str]:
    """Every declared reason that applies to one cell."""
    if not cell["measured"]:
        return ["no observations"]
    found = []
    if cell["independent_pooled"] < needed:
        found.append("too few independent windows")
    if not cell["positive_skill"]:
        found.append("no positive skill")
    elif not (cell["holdout_skill"] is not None and cell["holdout_skill"] > 0):
        found.append("failed hold-out")
    if cell["mean_net_return_pct"] is not None and cell["mean_net_return_pct"] <= 0:
        found.append("negative after costs")
    return found


def verdict(cell: Mapping[str, Any], reading: Reading) -> str:
    if cell["earned"] and cell["economic_edge"]:
        return "admit" if reading.admissible else "earned, not admissible"
    return "not earned"


def assess(
    rows: Sequence[FeatureOutcomeRow],
    readings: Sequence[Reading],
    coverage: Mapping[str, Any],
    costs: CostAssumptions,
    *,
    draws: int = 400,
    seed: int = 0,
) -> dict[str, Any]:
    by_id = {r.reading_id: r for r in readings}
    cards, tested = assess_feature_cards(rows, list(by_id), costs=costs, draws=draws, seed=seed)
    needed = {str(skill): windows_needed(skill) for skill in REFERENCE_SKILLS}
    spans = spans_in_days(rows)
    out = []
    for card in cards:
        reading = by_id[card.feature_id]
        cells = []
        for cell in card.cells:
            days = spans.get((reading.reading_id, cell["horizon_minutes"]), 0.0)
            rate = cell["independent_pooled"] / days if days > 0 else None
            cells.append({**cell, "span_days": days, "independent_per_day": rate,
                          "reasons": reasons(cell, needed[str(REFERENCE_SKILLS[0])]), "verdict": verdict(cell, reading),
                          "days_needed": {key: (n / rate if rate else None) for key, n in needed.items()}})
        out.append({
            "reading_id": reading.reading_id, "feature_id": reading.feature_id, "kind": reading.kind,
            "admissible": reading.admissible, "expected": expected_polarity(reading),
            "z": {"method": reading.z_method, "lookback": reading.z_lookback, "minimum": reading.z_minimum} if reading.z_method else None,
            "abstained_rows": card.abstained, "earned": card.earned, "earned_by": card.earned_by,
            "coverage": coverage["readings"][reading.reading_id], "cells": cells,
        })
    labelled = [(f"{r['reading_id']} {c['horizon_minutes']}m {c['polarity']}", c["verdict"]) for r in out for c in r["cells"]]
    return {
        "schema": "positioning_candidates_v1",
        "declared_cells": DECLARED_CELLS,
        "cells_tested": tested,
        "holm_first_z": holm_first_z(),
        "windows_needed": needed,
        "costs": {"total_pct": costs.total_pct, "source": costs.source},
        "opportunities": coverage["opportunities"],
        "readings": out,
        "decision": {
            "admitted": [label for label, v in labelled if v == "admit"],
            "earned_not_admissible": [label for label, v in labelled if v == "earned, not admissible"],
        },
    }
