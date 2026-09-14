"""The skill gate, measured the corrected way.

Replaces the by-regime endpoint's method with the one built in
``tradesync_core`` on 2026-09-11 after Codex's review:

- regimes are the **entry-time** labels recorded per opportunity, not an
  hour's own forward returns;
- independence is **counted** from actually non-overlapping windows, with
  symbols pooled, and the error is the larger of that binomial error and a
  block bootstrap;
- three verdicts that are never collapsed: ``detectable`` (either sign),
  ``positive_skill`` (one-sided, Holm-adjusted across every cell assessed
  together, and at least two standard errors), ``economic_edge`` (positive
  skill and a positive mean return after stated costs).

All horizons and regimes are assessed in one call, because the
multiple-comparison adjustment is only honest if it sees every cell that was
looked at. Nothing here opens a gate: it describes evidence.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from tradesync_core.edge_evidence import CostAssumptions, assess_cells
from tradesync_core.independence import Observation
from tradesync_core.outcomes import DEFAULT_HORIZONS_MINUTES
from tradesync_core.paper_rehearsal import HYPERLIQUID_BASE_FEES

router = APIRouter(tags=["outcomes"])

# Round trip: taker in and taker out at the venue's base tier, plus a crossing
# of the spread each way and a slippage allowance. The fee is the venue's
# published figure; the spread and slippage are conservative operator
# defaults, above the 1-2 bps the rehearsal fills have been recording for the
# majors, until a per-symbol measured spread replaces them.
COSTS = CostAssumptions(
    round_trip_fee_pct=HYPERLIQUID_BASE_FEES.taker_fee * 2 * 100,
    spread_pct=0.02,
    slippage_pct=0.01,
    source=(
        f"fees: {HYPERLIQUID_BASE_FEES.source} (read {HYPERLIQUID_BASE_FEES.read_on}); "
        "spread 2 bps and slippage 1 bps are conservative operator defaults"
    ),
)


def rows_to_observations(rows) -> dict[tuple[int, str], list[Observation]]:
    """Group measured outcomes into (horizon, entry regime) cells."""
    cells: dict[tuple[int, str], list[Observation]] = {}
    for r in rows:
        regime = r["regime"] or "unknown"
        cells.setdefault((int(r["horizon_minutes"]), regime), []).append(
            Observation(
                symbol=r["symbol"],
                opened_at_s=int(r["opened_at"].timestamp()),
                direction=r["direction"],
                forward_return_pct=float(r["forward_return_pct"]),
                signed_return_pct=float(r["signed_return_pct"]),
            )
        )
    return cells


async def compute_skill_gate(pool, symbol: str | None) -> dict[str, Any]:
    """The full skill-gate reading; shared by the endpoint and the thesis.

    The block bootstrap is pure Python and takes seconds. It runs in a worker
    thread so the event loop, and every other request, keeps being served.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT x.horizon_minutes, x.symbol, x.direction, x.opened_at,
                   x.forward_return_pct, x.signed_return_pct, r.regime
            FROM opportunity_outcomes x
            LEFT JOIN opportunity_entry_regimes r ON r.opportunity_id = x.opportunity_id
            WHERE x.status = 'measured'
              AND x.forward_return_pct IS NOT NULL AND x.signed_return_pct IS NOT NULL
              AND ($1::text IS NULL OR x.symbol = $1)
            """,
            symbol,
        )
        unlabelled = await conn.fetchval(
            """
            SELECT count(*) FROM opportunities o
            LEFT JOIN opportunity_entry_regimes r ON r.opportunity_id = o.id
            WHERE o.dir IN ('LONG','SHORT') AND r.opportunity_id IS NULL
            """
        )
    return await asyncio.to_thread(build_skill_gate, symbol, rows, int(unlabelled or 0))


def build_skill_gate(symbol: str | None, rows, unlabelled: int) -> dict[str, Any]:
    """Assess every (horizon, entry regime) cell together; CPU-bound, no I/O."""
    cells = rows_to_observations(rows)
    assessed = assess_cells(
        [(f"{h}m {regime}", h, obs) for (h, regime), obs in sorted(cells.items())],
        costs=COSTS,
        draws=400,
        seed=0,
    )
    out: list[dict[str, Any]] = []
    for (h, regime), cell in zip(sorted(cells.keys()), assessed):
        d = cell.to_dict()
        d["horizon_minutes"], d["regime"] = h, regime
        out.append(d)

    any_positive = any(c.positive_skill for c in assessed)
    any_edge = any(c.economic_edge for c in assessed)
    return {
        "schema_version": "skill_gate_v2",
        "symbol": symbol,
        "horizons": list(DEFAULT_HORIZONS_MINUTES),
        "cells": out,
        "cells_assessed_together": len(assessed),
        "verdict": {
            "any_detectable": any(c.detectable for c in assessed),
            "any_positive_skill": any_positive,
            "any_economic_edge": any_edge,
            "gate": "OPEN" if any_edge else "CLOSED",
        },
        "costs": {
            "round_trip_fee_pct": COSTS.round_trip_fee_pct,
            "spread_pct": COSTS.spread_pct,
            "slippage_pct": COSTS.slippage_pct,
            "total_pct": COSTS.total_pct,
            "source": COSTS.source,
        },
        "entry_regimes_pending": int(unlabelled or 0),
        "note": (
            "Regimes are entry-time labels from candles closed before each signal. "
            "Standard errors count non-overlapping windows with symbols pooled and "
            "take the larger of that and a block bootstrap. positive_skill is "
            "Holm-adjusted across every cell here. economic_edge requires positive "
            "skill and a positive mean return after the stated costs. None of this "
            "is trading readiness; the gate opens only on economic_edge AND explicit "
            "operator approval."
        ),
    }


def register(app, state) -> None:
    @router.get("/state/outcomes/skill-gate")
    async def skill_gate(symbol: str | None = None):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        return await compute_skill_gate(state.pool, symbol)

    app.include_router(router)
