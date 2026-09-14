"""The Regime Lab's overview, evaluation and draft experiment routes.

Moved unchanged out of main.py; main.py registers the routes.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from app.regime_lab import RegimeLabValidationError, persist_experiment

logger = logging.getLogger("state-api")

# Set by register(): the app's shared state, the engine and the live evidence reader.
state = None
regime_lab_engine = None
_regime_lab_evidence = None


class RegimeLabExperimentRequest(BaseModel):
    name: str = Field(default="Local paper challenger", min_length=3, max_length=120)
    version: str = Field(min_length=1, max_length=40)
    hypothesis: str = Field(min_length=20, max_length=800)
    evaluation_window: str = Field(
        default="current_evidence_snapshot", min_length=3, max_length=120
    )
    expected_effect: str = Field(default="uncertain", max_length=80)
    weights: Dict[str, float]
    risk_flags: List[str] = Field(default_factory=list)


async def get_regime_lab_overview(
    venue: str = Query("hyperliquid"),
    symbol: str = Query("BTC-PERP"),
):
    """Return source evidence, feature normalization and the baseline evaluation."""
    feature_results, source_status = await _regime_lab_evidence(venue, symbol)
    return regime_lab_engine.build_overview(feature_results, source_status)


async def evaluate_regime_lab_experiment(
    request: RegimeLabExperimentRequest,
    venue: str = Query("hyperliquid"),
    symbol: str = Query("BTC-PERP"),
):
    """Validate and compare a draft without writing or activating it."""
    feature_results, source_status = await _regime_lab_evidence(venue, symbol)
    try:
        evaluation = regime_lab_engine.evaluate_request(
            request.model_dump(), feature_results
        )
    except RegimeLabValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    evaluation["source_status"] = source_status
    return evaluation


async def save_regime_lab_experiment(
    request: RegimeLabExperimentRequest,
    venue: str = Query("hyperliquid"),
    symbol: str = Query("BTC-PERP"),
):
    """Persist a draft experiment; nothing here can activate it."""
    feature_results, source_status = await _regime_lab_evidence(venue, symbol)
    try:
        evaluation = regime_lab_engine.evaluate_request(
            request.model_dump(), feature_results
        )
    except RegimeLabValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not state.pool:
        raise HTTPException(
            status_code=503,
            detail="PostgreSQL is unavailable; evaluation succeeded but was not saved",
        )
    try:
        async with state.pool.acquire() as conn:
            async with conn.transaction():
                experiment_id = await persist_experiment(
                    conn, regime_lab_engine, request.model_dump(), evaluation
                )
    except Exception as exc:
        logger.error(
            f"Regime Lab persistence failed: {exc}",
            extra={"trace_id": "regime-lab"},
        )
        raise HTTPException(
            status_code=503,
            detail="Regime Lab persistence is unavailable; verify migrations",
        ) from exc
    return {
        "saved": True,
        "experiment_id": experiment_id,
        "status": "draft",
        "source_status": source_status,
        "activation_available": False,
        "evaluation": evaluation,
    }


async def list_regime_lab_experiments(limit: int = Query(20, ge=1, le=100)):
    """List immutable draft experiment records; no activation action is exposed."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="PostgreSQL is unavailable")
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select e.id, e.name, e.status, e.horizon, e.hypothesis,
                       e.evaluation_plan, e.results, e.created_at,
                       champion.version as baseline_version,
                       challenger.version as challenger_version
                from regime_experiments e
                join regime_rulebooks champion on champion.id=e.champion_rulebook_id
                join regime_rulebooks challenger on challenger.id=e.challenger_rulebook_id
                order by e.created_at desc
                limit $1
                """,
                limit,
            )
        return {"experiments": [dict(row) for row in rows], "count": len(rows)}
    except Exception as exc:
        logger.error(
            f"Regime Lab history failed: {exc}",
            extra={"trace_id": "regime-lab"},
        )
        raise HTTPException(
            status_code=503,
            detail="Regime Lab history is unavailable; verify migrations",
        ) from exc


def register(app, app_state, *, engine, evidence) -> None:
    global state, regime_lab_engine, _regime_lab_evidence
    state, regime_lab_engine, _regime_lab_evidence = app_state, engine, evidence
    app.get("/state/regime-lab/overview", tags=["regime-lab"])(get_regime_lab_overview)
    app.post("/state/regime-lab/evaluate", tags=["regime-lab"])(evaluate_regime_lab_experiment)
    app.post("/state/regime-lab/experiments", tags=["regime-lab"])(save_regime_lab_experiment)
    app.get("/state/regime-lab/experiments", tags=["regime-lab"])(list_regime_lab_experiments)
