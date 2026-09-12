"""Source cards: what each external source (agent, indicator, channel) has earned.

The claims job turns quarantined material into claims and measures each one
against venue candles. This endpoint reads those measurements and assesses
every source with the same machinery as the skill gate and the evidence
cards: counted independence, block bootstrap, three verdicts, the stated
costs, and one Holm adjustment across every cell of every card. Both
polarities are tested, because a source can be usefully contrarian.

"Earned" is positive skill that also held out of sample. The endpoint reports
it; granting a source any weight in admission remains an operator decision.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.skill_gate import COSTS
from tradesync_core.edge_evidence import assess_cells
from tradesync_core.feature_evidence import earned_by
from tradesync_core.independence import Observation
from tradesync_core.outcomes import DEFAULT_HORIZONS_MINUTES

router = APIRouter(tags=["outcomes"])

ROWS_SQL = """
SELECT c.source, c.source_id, o.symbol, o.direction, o.horizon_minutes, o.claimed_at,
       o.forward_return_pct, o.signed_return_pct
FROM evidence_claim_outcomes o
JOIN evidence_claims c ON c.id = o.claim_id
WHERE o.status = 'measured' AND o.forward_return_pct IS NOT NULL AND o.signed_return_pct IS NOT NULL
  AND ($1::text IS NULL OR o.symbol = $1)
"""

COVERAGE_SQL = """
SELECT c.source, c.source_id, count(*) AS claims, max(c.claimed_at) AS latest,
       count(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM evidence_claim_outcomes o WHERE o.claim_id = c.id AND o.status = 'measured')) AS measured
FROM evidence_claims c
WHERE ($1::text IS NULL OR c.symbol = $1)
GROUP BY c.source, c.source_id
"""

EXTRACTION_SQL = """
SELECT count(*) FILTER (WHERE claims > 0) AS with_claims, count(*) FILTER (WHERE claims = 0) AS without,
       (SELECT count(*) FROM quarantine_intake q LEFT JOIN quarantine_extractions x ON x.quarantine_id = q.id
         WHERE q.accepted AND q.source IN ('tradingview','discord','chaseos') AND x.quarantine_id IS NULL) AS pending
FROM quarantine_extractions
"""


def rows_to_cells(rows) -> dict[tuple[str, str, int, str], list[Observation]]:
    """(source, source_id, horizon, polarity) -> observations. Inverted flips the call."""
    cells: dict[tuple[str, str, int, str], list[Observation]] = {}
    for r in rows:
        fwd, signed = float(r["forward_return_pct"]), float(r["signed_return_pct"])
        opened = int(r["claimed_at"].timestamp())
        for polarity, direction, s in (
            ("as_stated", r["direction"], signed),
            ("inverted", "SHORT" if r["direction"] == "LONG" else "LONG", -signed),
        ):
            cells.setdefault((r["source"], r["source_id"], int(r["horizon_minutes"]), polarity), []).append(
                Observation(symbol=r["symbol"], opened_at_s=opened, direction=direction, forward_return_pct=fwd, signed_return_pct=s)
            )
    return cells


def build_response(symbol: str | None, rows, coverage, extraction, draws: int = 400) -> dict[str, Any]:
    cells = rows_to_cells(rows)
    keys = sorted(cells.keys())
    assessed = assess_cells([(f"{sid} {h}m {p}", h, cells[k]) for k in keys for (_, sid, h, p) in [k]], costs=COSTS, draws=draws, seed=0)

    cards: dict[tuple[str, str], dict[str, Any]] = {}
    for r in coverage:
        cards[(r["source"], r["source_id"])] = {
            "source": r["source"], "source_id": r["source_id"], "claims": int(r["claims"]),
            "claims_measured": int(r["measured"]), "latest_claim_at": r["latest"].isoformat() if r["latest"] else None,
            "cells": [], "earned": False, "earned_by": [],
        }
    for (source, sid, h, polarity), cell in zip(keys, assessed):
        card = cards.setdefault((source, sid), {"source": source, "source_id": sid, "claims": 0, "claims_measured": 0,
                                                 "latest_claim_at": None, "cells": [], "earned": False, "earned_by": []})
        d = cell.to_dict()
        d["horizon_minutes"], d["polarity"], d["earned"] = h, polarity, earned_by(cell)
        card["cells"].append(d)
        if d["earned"]:
            card["earned"] = True
            card["earned_by"].append(f"{h}m {polarity}")
    ordered = sorted(cards.values(), key=lambda c: (not c["earned"], -c["claims"], c["source_id"]))
    for c in ordered:
        c["next_step"] = ("operator may catalogue this source as a context-only feature and admit it by decision"
                          if c["earned"] else "keeps recording; no weight")
    return {
        "schema_version": "source_cards_v1",
        "symbol": symbol,
        "horizons": list(DEFAULT_HORIZONS_MINUTES),
        "polarities": ["as_stated", "inverted"],
        "cards": ordered,
        "cells_assessed_together": len(assessed),
        "extraction": {"rows_with_claims": int(extraction["with_claims"] or 0), "rows_without_claims": int(extraction["without"] or 0),
                       "rows_pending": int(extraction["pending"] or 0)},
        "costs": {"round_trip_fee_pct": COSTS.round_trip_fee_pct, "spread_pct": COSTS.spread_pct,
                  "slippage_pct": COSTS.slippage_pct, "total_pct": COSTS.total_pct, "source": COSTS.source},
        "note": (
            "A claim is 'this source said this direction on this symbol at this time', extracted by rule from "
            "quarantined material and measured like a paper opportunity. Cells across every source are "
            "Holm-adjusted together with the skill gate's costs. 'earned' means positive skill that also held "
            "out of sample. Nothing here grants a weight; that is an operator decision."
        ),
    }


async def compute_source_cards(pool, symbol: str | None) -> dict[str, Any]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(ROWS_SQL, symbol)
        coverage = await conn.fetch(COVERAGE_SQL, symbol)
        extraction = await conn.fetchrow(EXTRACTION_SQL)
    return build_response(symbol, rows, coverage, extraction)


def register(app, state) -> None:
    @router.get("/state/outcomes/source-cards")
    async def source_cards(symbol: str | None = None):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        return await compute_source_cards(state.pool, symbol)

    app.include_router(router)
