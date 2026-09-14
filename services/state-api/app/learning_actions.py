"""Operator actions for opportunity learning: generate, adopt, reject, revert.

Adoption and revert change which weights the paper scorer uses, so both demand
``confirm: true`` and a name. Nothing here places an order or changes any
execution flag: the scorer is paper-only and stays that way.
"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from tradesync_core.regime_weights import RegimeRulebook

from app import learning_job as job
from app import learning_store as store
from app import rulebook_activation as activation
from app.learning_routes import connection, uuid_or_422


class OperatorDecision(BaseModel):
    decided_by: str = Field(min_length=2, max_length=80)
    note: str = Field(default="", max_length=500)
    confirm: bool = False


class GenerateRequest(BaseModel):
    requested_by: str = Field(min_length=2, max_length=80)
    horizon_minutes: int = Field(default=job.TARGET_HORIZON_MINUTES)


def _require_confirmation(body: OperatorDecision, action: str) -> None:
    if not body.confirm:
        raise HTTPException(status_code=400, detail=f"{action} changes the paper scorer's weights; confirm it explicitly")


def register(router, state, baseline: RegimeRulebook) -> None:
    @router.post("/state/learning/proposals/generate")
    async def generate_proposal(body: GenerateRequest):
        if body.horizon_minutes not in (15, 60, 240):
            raise HTTPException(status_code=422, detail="horizon_minutes must be 15, 60 or 240")
        async with connection(state):
            pass  # fail fast with 503 before the lock when the database is not ready
        async with job.lock:
            outcome = await job.run_proposal_pass(state.pool, baseline, horizon=body.horizon_minutes,
                                                  created_by=body.requested_by)
        job.last_runs["proposal"] = {**outcome, "requested_by": body.requested_by}
        return outcome

    @router.post("/state/learning/proposals/{proposal_id}/adopt")
    async def adopt_proposal(proposal_id: str, body: OperatorDecision):
        key = uuid_or_422(proposal_id)
        _require_confirmation(body, "Adoption")
        async with connection(state) as conn:
            async with conn.transaction():
                row = await conn.fetchrow("SELECT * FROM learning_proposals WHERE id = $1::uuid FOR UPDATE", key)
                if not row:
                    raise HTTPException(status_code=404, detail="proposal not found")
                if row["status"] != "proposed":
                    raise HTTPException(status_code=409, detail=f"proposal is already {row['status']}")
                try:
                    result = await activation.adopt(conn, store.proposal_row(row), baseline, body.decided_by, body.note)
                except activation.ActivationConflict as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"adopted": True, **result,
                "note": "Recorded as the active paper rulebook; the scorer reads it on its next cycle."}

    @router.post("/state/learning/proposals/{proposal_id}/reject")
    async def reject_proposal(proposal_id: str, body: OperatorDecision):
        key = uuid_or_422(proposal_id)
        async with connection(state) as conn:
            updated = await conn.fetchval(
                """
                UPDATE learning_proposals SET status = 'rejected', decided_at = now(), decided_by = $2, decision_note = $3
                WHERE id = $1::uuid AND status = 'proposed' RETURNING id
                """,
                key, body.decided_by, body.note,
            )
            if not updated:
                status = await conn.fetchval("SELECT status FROM learning_proposals WHERE id = $1::uuid", key)
                if status is None:
                    raise HTTPException(status_code=404, detail="proposal not found")
                raise HTTPException(status_code=409, detail=f"proposal is already {status}")
        return {"rejected": True, "proposal_id": key}

    @router.post("/state/learning/active/revert")
    async def revert_active(body: OperatorDecision):
        _require_confirmation(body, "Revert")
        async with connection(state) as conn:
            async with conn.transaction():
                try:
                    result = await activation.revert(conn, baseline, body.decided_by, body.note)
                except activation.ActivationConflict as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"reverted": True, **result,
                "note": "The scorer uses the restored rulebook from its next cycle."}
