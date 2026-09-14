"""Read routes for opportunity learning: scoreboard, failures, verdicts, proposals, active rulebook.

``register`` also attaches the operator actions (app/learning_actions.py) and
the background job (app/learning_job.py), so main.py registers learning once.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from tradesync_core.learning_aggregate import VerdictPolicy, aggregate_all
from tradesync_core.learning_scoreboard import scoreboard
from tradesync_core.outcome_classification import FAILURES
from tradesync_core.regime_weights import RegimeRulebook

from app import background
from app import learning_job as job
from app import learning_store as store
from app import rulebook_activation as activation

router = APIRouter(tags=["learning"])
NOT_MIGRATED = "Learning tables are not migrated yet (ops/migrations/028_opportunity_learning.sql)."


@asynccontextmanager
async def connection(state):
    """A pooled connection; 503 when the database or the 028 tables are missing."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    try:
        async with state.pool.acquire() as conn:
            yield conn
    except Exception as exc:
        if type(exc).__name__ == "UndefinedTableError":
            raise HTTPException(status_code=503, detail=NOT_MIGRATED) from exc
        raise


def uuid_or_422(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="not a valid id") from exc


def register(app, state, baseline: RegimeRulebook) -> None:
    @router.get("/state/learning/scoreboard")
    async def get_scoreboard(days: int = Query(14, ge=1, le=90)):
        async with connection(state) as conn:
            rows = await store.attributions_since(conn, days)
        return {"days": days, "cost_pct": job.COST_PCT, "attributions": len(rows),
                "horizons": await asyncio.to_thread(scoreboard, rows),
                "note": "A win finished beyond the round-trip cost in its own direction."}

    @router.get("/state/learning/failures")
    async def get_failures(horizon: Optional[int] = Query(None, ge=1), limit: int = Query(20, ge=1, le=100)):
        async with connection(state) as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM opportunity_attributions
                WHERE classification = ANY($1::text[]) AND ($2::int IS NULL OR horizon_minutes = $2)
                ORDER BY opened_at DESC, horizon_minutes LIMIT $3
                """,
                sorted(FAILURES), horizon, limit,
            )
        return {"failures": [store.attribution_row(r) for r in rows]}

    @router.get("/state/learning/verdicts")
    async def get_verdicts(horizon: int = Query(60, ge=1), days: int = Query(14, ge=1, le=90)):
        async with connection(state) as conn:
            rows = await store.attributions_since(conn, days, horizon)
        policy = VerdictPolicy()
        tables = await asyncio.to_thread(aggregate_all, rows, policy)
        return {"horizon_minutes": horizon, "days": days, "attributions": len(rows),
                "policy": policy.to_dict(), **tables}

    @router.get("/state/learning/proposals")
    async def get_proposals(limit: int = Query(10, ge=1, le=50)):
        async with connection(state) as conn:
            rows = await conn.fetch("SELECT * FROM learning_proposals ORDER BY created_at DESC LIMIT $1", limit)
        return {"proposals": [store.proposal_row(r) for r in rows], "last_run": job.last_runs.get("proposal")}

    @router.get("/state/learning/active")
    async def get_active():
        async with connection(state) as conn:
            current = await activation.read_active(conn, baseline)
            history = await activation.history(conn, baseline)
            used = await activation.scorer_last_used(conn)
        return {
            "active": current.summary(),
            "file": {"version": baseline.version, "digest": baseline.digest, "weights": baseline.weights},
            "history": history,
            "scorer_last_used": used,
            "scorer_in_step": bool(used and used["digest"] == current.rulebook.digest),
        }

    @router.get("/state/learning/status")
    async def get_status():
        return {"last_runs": job.last_runs, "cost_pct": job.COST_PCT,
                "target_horizon_minutes": job.TARGET_HORIZON_MINUTES, "window_days": job.WINDOW_DAYS,
                "attribution_interval_seconds": job.ATTRIBUTION_INTERVAL_SECONDS,
                "proposal_interval_seconds": job.PROPOSAL_INTERVAL_SECONDS,
                "adoption": "operator action only; nothing is adopted automatically"}

    @router.get("/state/opportunities/{opportunity_id}/attribution")
    async def get_opportunity_attribution(opportunity_id: str):
        key = uuid_or_422(opportunity_id)
        async with connection(state) as conn:
            outcomes = await conn.fetch(
                """
                SELECT horizon_minutes, status, entry_price, exit_price, forward_return_pct, signed_return_pct,
                       max_favourable_pct, max_adverse_pct, reason, measured_at
                FROM opportunity_outcomes WHERE opportunity_id = $1::uuid ORDER BY horizon_minutes
                """,
                key,
            )
            regime = await conn.fetchrow(
                "SELECT regime, trailing_return_pct FROM opportunity_entry_regimes WHERE opportunity_id = $1::uuid", key
            )
            attributions = await conn.fetch(
                "SELECT * FROM opportunity_attributions WHERE opportunity_id = $1::uuid ORDER BY horizon_minutes", key
            )
        return {
            "opportunity_id": key,
            "entry_regime": dict(regime) if regime else None,
            "outcomes": [{**dict(r), "measured_at": r["measured_at"].isoformat() if r["measured_at"] else None}
                         for r in outcomes],
            "attributions": [store.attribution_row(r) for r in attributions],
        }

    from app.learning_actions import register as register_actions

    register_actions(router, state, baseline)
    background.add("opportunity_learning", lambda: job.learning_loop(state, baseline))
    app.include_router(router)
