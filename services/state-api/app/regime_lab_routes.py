"""The Regime Lab's overview and draft experiment routes.

- ``GET /state/regime-lab/overview``: live feature evidence, normalization, block
  evidence and the baseline evaluation for one market.
- ``POST /state/regime-lab/experiments``: judge a challenger by replay and store
  it as an immutable draft together with that judgement.
- ``GET /state/regime-lab/experiments``: recent drafts with their hypothesis,
  weights and replay judgement.

Evaluating a challenger is ``POST /state/regime-lab/replay`` (app/regime_replay.py).
Saving runs the same replay on the server, so the stored judgement is the one
measured at save time rather than one the browser sent. There is no activation
endpoint.
"""

from __future__ import annotations

import logging
from typing import Dict, Literal, Optional

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from app.regime_lab_experiments import LIST_SQL, experiment_summary, persist_experiment
from app.regime_replay import challenger_from_request, run_replay
from tradesync_core import normalize_symbol

logger = logging.getLogger("state-api")

# Set by register(): the app's shared state, the engine and the live evidence reader.
state = None
regime_lab_engine = None
_regime_lab_evidence = None


class RegimeLabExperimentRequest(BaseModel):
    """A challenger to judge by replay and keep as a draft."""

    name: str = Field(default="Paper challenger", min_length=3, max_length=120)
    version: str = Field(min_length=1, max_length=40)
    hypothesis: str = Field(min_length=20, max_length=800)
    weights: Dict[str, float]
    hours: Literal[24, 168, 720] = 24
    horizon_minutes: Literal[15, 60, 240] = 60
    symbol: Optional[str] = Field(default=None, max_length=24)


async def get_regime_lab_overview(
    venue: str = Query("hyperliquid"),
    symbol: str = Query("BTC-PERP"),
):
    """Return source evidence, feature normalization and the baseline evaluation."""
    feature_results, source_status = await _regime_lab_evidence(venue, symbol)
    return regime_lab_engine.build_overview(feature_results, source_status)


async def save_regime_lab_experiment(request: RegimeLabExperimentRequest):
    """Judge the challenger by replay and store it as an immutable draft; nothing here can activate it."""
    hypothesis = request.hypothesis.strip()
    if len(hypothesis) < 20:
        raise HTTPException(status_code=422, detail="hypothesis must contain at least 20 characters")
    challenger = challenger_from_request(regime_lab_engine, request.weights, request.version, hypothesis)
    if not state.pool:
        raise HTTPException(status_code=503, detail="PostgreSQL is unavailable; the experiment was not saved")
    symbol = normalize_symbol(request.symbol) if request.symbol else None
    replay = await run_replay(
        state.pool, regime_lab_engine,
        hours=request.hours, horizon_minutes=request.horizon_minutes, symbol=symbol, challenger=challenger,
    )
    try:
        async with state.pool.acquire() as conn:
            async with conn.transaction():
                experiment_id = await persist_experiment(
                    conn, regime_lab_engine.baseline, challenger,
                    name=request.name.strip(), hypothesis=hypothesis, replay=replay,
                )
    except Exception as exc:
        if type(exc).__name__ == "UniqueViolationError":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Challenger version '{request.version}' is already saved with a different "
                    "configuration; choose a new version"
                ),
            ) from None
        logger.error(f"Regime Lab persistence failed: {type(exc).__name__}: {exc}", extra={"trace_id": "regime-lab"})
        raise HTTPException(
            status_code=503,
            detail=f"The experiment could not be stored ({type(exc).__name__}); verify the regime_experiments migration",
        ) from None
    return {
        "saved": True,
        "experiment_id": experiment_id,
        "status": "draft",
        "replay": replay,
        "activation_available": False,
    }


async def list_regime_lab_experiments(limit: int = Query(20, ge=1, le=100)):
    """Recent immutable drafts with their hypothesis, weights and replay judgement."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="PostgreSQL is unavailable; saved experiments cannot be listed")
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(LIST_SQL, limit)
    except Exception as exc:
        logger.error(f"Regime Lab history failed: {type(exc).__name__}: {exc}", extra={"trace_id": "regime-lab"})
        raise HTTPException(
            status_code=503,
            detail=f"Saved experiments could not be read ({type(exc).__name__}); verify the regime_experiments migration",
        ) from None
    return {"experiments": [experiment_summary(row) for row in rows], "count": len(rows)}


def register(app, app_state, *, engine, evidence) -> None:
    global state, regime_lab_engine, _regime_lab_evidence
    state, regime_lab_engine, _regime_lab_evidence = app_state, engine, evidence
    app.get("/state/regime-lab/overview", tags=["regime-lab"])(get_regime_lab_overview)
    app.post("/state/regime-lab/experiments", tags=["regime-lab"])(save_regime_lab_experiment)
    app.get("/state/regime-lab/experiments", tags=["regime-lab"])(list_regime_lab_experiments)
