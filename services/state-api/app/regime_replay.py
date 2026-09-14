"""Fixed-window replay of stored paper decisions under a challenger rulebook.

Moved unchanged out of main.py; main.py registers the route.
"""

from __future__ import annotations

import json
from typing import Dict, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from tradesync_core import normalize_symbol
from tradesync_core.paper_signal import AdmissionPolicy
from tradesync_core.regime_weights import RulebookValidationError, validate_rulebook
from tradesync_core.replay import (
    ReplayError,
    case_from_stored_evidence,
    compare_rulebooks,
)

# Set by register(): the app's shared state and the Regime Lab engine.
state = None
regime_lab_engine = None


class ReplayRequest(BaseModel):
    """A frozen-window replay request. Weights must form a valid rulebook."""

    hours: int = Field(24, ge=1, le=720)
    symbol: Optional[str] = None
    horizon_minutes: int = Field(60, ge=1)
    challenger_weights: Optional[Dict[str, float]] = None


async def replay_fixed_window(request: ReplayRequest):
    """Re-run the rulebook over a frozen window of recorded evidence.

    Champion and challenger see identical stored evidence, so any difference is
    attributable to the configuration rather than to the market having moved.
    Paper only: replay cannot activate a rulebook or place an order.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    symbol = normalize_symbol(request.symbol) if request.symbol else None
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.id, s.symbol, s.features,
                       o.signed_return_pct, o.forward_return_pct
                FROM signals s
                JOIN opportunities opp ON opp.signal_id = s.id
                JOIN opportunity_outcomes o
                  ON o.opportunity_id = opp.id AND o.horizon_minutes = $1
                WHERE s.agent = 'regime_paper_scorer'
                  AND s.created_at > now() - ($2 || ' hours')::interval
                  AND o.status = 'measured'
                  AND ($3::text IS NULL OR s.symbol = $3)
                ORDER BY s.created_at
                """,
                request.horizon_minutes,
                str(request.hours),
                symbol,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    cases = []
    skipped = 0
    for row in rows:
        stored = row["features"]
        if isinstance(stored, str):
            stored = json.loads(stored)
        try:
            cases.append(
                case_from_stored_evidence(
                    str(row["id"]),
                    row["symbol"],
                    stored,
                    outcome_signed_return_pct=row["signed_return_pct"],
                    market_move_pct=row["forward_return_pct"],
                )
            )
        except ReplayError:
            # Evidence recorded before the current schema cannot be replayed
            # faithfully, so it is counted and excluded rather than guessed at.
            skipped += 1

    if not cases:
        return {
            "schema_version": "regime_replay_v1",
            "window_cases": 0,
            "skipped_unreplayable": skipped,
            "note": (
                "No measured decision in this window carries replayable "
                "evidence. Outcomes need the horizon to have closed."
            ),
        }

    champion = regime_lab_engine.baseline
    challenger = champion
    if request.challenger_weights:
        try:
            data = json.loads(json.dumps(champion.data))
            for block, weight in request.challenger_weights.items():
                if block not in data["blocks"]:
                    raise HTTPException(
                        status_code=400, detail=f"unknown block '{block}'"
                    )
                data["blocks"][block]["weight"] = weight
            data["version"] = f"{champion.version}-challenger"
            challenger = validate_rulebook(data)
        except RulebookValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    result = compare_rulebooks(
        cases,
        champion,
        challenger,
        AdmissionPolicy(),
        {
            "catalog_id": regime_lab_engine.catalog.data["catalog_id"],
            "version": regime_lab_engine.catalog.version,
            "digest": regime_lab_engine.catalog.digest,
        },
    )
    result["horizon_minutes"] = request.horizon_minutes
    result["window_hours"] = request.hours
    result["skipped_unreplayable"] = skipped
    result["execution_authority"] = False
    return result


def register(app, app_state, *, engine) -> None:
    global state, regime_lab_engine
    state, regime_lab_engine = app_state, engine
    app.post("/state/regime-lab/replay", tags=["regime-lab"])(replay_fixed_window)
