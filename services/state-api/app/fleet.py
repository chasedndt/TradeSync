"""The Hermes fleet in Market Command: read model, usage analytics, and directives.

The fleet's files live in WSL. The host bridge posts snapshots of the job
registry, the execution ledger and the token usage audit here, and picks up
directives to apply (schedule, enabled, working directory), reporting back
what it replaced. state-api never touches the fleet's files and never runs a
job. A directive is a request until the bridge says it was applied.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fleet"])

DIRECTIVE_KINDS = ("set_schedule", "set_enabled", "set_workdir")
# Schedules the panel offers. Anything else is a hand edit on the fleet host.
SCHEDULE_PRESETS = {
    "15m": {"kind": "interval", "minutes": 15, "display": "every 15m"},
    "30m": {"kind": "interval", "minutes": 30, "display": "every 30m"},
    "1h": {"kind": "interval", "minutes": 60, "display": "every 60m"},
    "3h": {"kind": "interval", "minutes": 180, "display": "every 180m"},
    "6h": {"kind": "interval", "minutes": 360, "display": "every 360m"},
    "daily-08": {"kind": "cron", "expr": "0 8 * * *", "display": "0 8 * * *"},
    "weekly-mon-08": {"kind": "cron", "expr": "0 8 * * 1", "display": "0 8 * * 1"},
}


class JobSnapshot(BaseModel):
    job_id: str
    name: str
    enabled: bool = True
    schedule: dict[str, Any] = Field(default_factory=dict)
    schedule_display: str = ""
    deliver: str = "local"
    workdir: str | None = None
    script: str | None = None
    no_agent: bool = False
    model: str | None = None
    description: str = ""
    last_run_at: datetime | None = None
    last_status: str | None = None
    next_run_at: datetime | None = None
    state: str | None = None


class RunSnapshot(BaseModel):
    id: str
    job_id: str
    status: str
    claimed_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None


class UsageSnapshot(BaseModel):
    fire_id: str
    job_id: str
    ts: datetime
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int | None = None
    deliver_target: str | None = None
    response_silent: bool | None = None
    error: str | None = None


class FleetSnapshot(BaseModel):
    jobs: list[JobSnapshot] = Field(default_factory=list)
    runs: list[RunSnapshot] = Field(default_factory=list)
    usage: list[UsageSnapshot] = Field(default_factory=list)


class DirectiveRequest(BaseModel):
    job_id: str
    kind: str
    preset: str | None = None  # for set_schedule
    enabled: bool | None = None  # for set_enabled
    workdir: str | None = None  # for set_workdir
    requested_by: str = "operator"


class DirectiveReport(BaseModel):
    id: str
    status: str
    previous: dict[str, Any] | None = None
    detail: str = ""


async def _upsert_jobs(conn, jobs: list[JobSnapshot]) -> None:
    for j in jobs:
        await conn.execute(
            """
            INSERT INTO fleet_jobs (job_id, name, enabled, schedule, schedule_display, deliver, workdir, script, no_agent, model,
                                    description, last_run_at, last_status, next_run_at, state, snapshot_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, now())
            ON CONFLICT (job_id) DO UPDATE SET name = EXCLUDED.name, enabled = EXCLUDED.enabled, schedule = EXCLUDED.schedule,
                schedule_display = EXCLUDED.schedule_display, deliver = EXCLUDED.deliver, workdir = EXCLUDED.workdir,
                script = EXCLUDED.script, no_agent = EXCLUDED.no_agent, model = EXCLUDED.model, description = EXCLUDED.description,
                last_run_at = EXCLUDED.last_run_at, last_status = EXCLUDED.last_status, next_run_at = EXCLUDED.next_run_at,
                state = EXCLUDED.state, snapshot_at = now()
            """,
            j.job_id, j.name, j.enabled, json.dumps(j.schedule), j.schedule_display, j.deliver, j.workdir, j.script,
            j.no_agent, j.model, j.description, j.last_run_at, j.last_status, j.next_run_at, j.state,
        )


async def _upsert_runs(conn, runs: list[RunSnapshot]) -> None:
    for r in runs:
        await conn.execute(
            """
            INSERT INTO fleet_runs (id, job_id, status, claimed_at, started_at, finished_at, duration_ms, error, snapshot_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
            ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, started_at = EXCLUDED.started_at,
                finished_at = EXCLUDED.finished_at, duration_ms = EXCLUDED.duration_ms, error = EXCLUDED.error, snapshot_at = now()
            """,
            r.id, r.job_id, r.status, r.claimed_at, r.started_at, r.finished_at, r.duration_ms, r.error,
        )


async def _upsert_usage(conn, usage: list[UsageSnapshot]) -> None:
    for u in usage:
        await conn.execute(
            """
            INSERT INTO fleet_usage (fire_id, job_id, ts, model, prompt_tokens, completion_tokens, total_tokens, duration_ms,
                                     deliver_target, response_silent, error)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) ON CONFLICT (fire_id) DO NOTHING
            """,
            u.fire_id, u.job_id, u.ts, u.model, u.prompt_tokens, u.completion_tokens, u.total_tokens, u.duration_ms,
            u.deliver_target, u.response_silent, u.error,
        )


def register(app, state) -> None:
    @router.post("/state/fleet/snapshot")
    async def post_snapshot(snapshot: FleetSnapshot):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        async with state.pool.acquire() as conn:
            await _upsert_jobs(conn, snapshot.jobs)
            await _upsert_runs(conn, snapshot.runs)
            await _upsert_usage(conn, snapshot.usage)
        return {"jobs": len(snapshot.jobs), "runs": len(snapshot.runs), "usage": len(snapshot.usage)}

    @router.get("/state/fleet/jobs")
    async def list_jobs():
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        async with state.pool.acquire() as conn:
            jobs = await conn.fetch("SELECT * FROM fleet_jobs ORDER BY enabled DESC, name")
            runs = await conn.fetch(
                """
                SELECT job_id, count(*) FILTER (WHERE claimed_at > now() - interval '24 hours') AS runs_24h,
                       count(*) FILTER (WHERE status = 'failed' AND claimed_at > now() - interval '24 hours') AS failed_24h
                FROM fleet_runs GROUP BY job_id
                """
            )
            usage = await conn.fetch(
                """
                SELECT job_id, coalesce(sum(total_tokens) FILTER (WHERE ts > now() - interval '24 hours'), 0) AS tokens_24h,
                       coalesce(sum(total_tokens) FILTER (WHERE ts > now() - interval '7 days'), 0) AS tokens_7d,
                       count(*) FILTER (WHERE ts > now() - interval '7 days') AS fires_7d
                FROM fleet_usage GROUP BY job_id
                """
            )
            pending = await conn.fetch("SELECT job_id, kind, payload, requested_at FROM fleet_directives WHERE status = 'pending'")
        run_by = {r["job_id"]: r for r in runs}
        use_by = {u["job_id"]: u for u in usage}
        pend_by: dict[str, list[dict[str, Any]]] = {}
        for p in pending:
            pend_by.setdefault(p["job_id"], []).append({"kind": p["kind"], "payload": _json(p["payload"]), "requested_at": p["requested_at"].isoformat()})
        out = []
        for j in jobs:
            r, u = run_by.get(j["job_id"]), use_by.get(j["job_id"])
            out.append({
                **{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in dict(j).items() if k != "schedule"},
                "schedule": _json(j["schedule"]),
                "runs_24h": int(r["runs_24h"]) if r else 0, "failed_24h": int(r["failed_24h"]) if r else 0,
                "tokens_24h": int(u["tokens_24h"]) if u else 0, "tokens_7d": int(u["tokens_7d"]) if u else 0,
                "fires_7d": int(u["fires_7d"]) if u else 0, "pending_directives": pend_by.get(j["job_id"], []),
            })
        newest = max((j["snapshot_at"] for j in jobs), default=None)
        return {"schema_version": "fleet_jobs_v1", "jobs": out, "snapshot_at": newest.isoformat() if newest else None,
                "presets": SCHEDULE_PRESETS,
                "note": "Read model of the Hermes fleet, posted by the host bridge. Directives are requests until the bridge applies them."}

    @router.get("/state/fleet/usage")
    async def usage_analytics(days: int = Query(7, ge=1, le=90)):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        async with state.pool.acquire() as conn:
            daily = await conn.fetch(
                """
                SELECT date_trunc('day', ts) AS day, count(*) AS fires, sum(prompt_tokens) AS prompt_tokens,
                       sum(completion_tokens) AS completion_tokens, sum(total_tokens) AS total_tokens
                FROM fleet_usage WHERE ts > now() - ($1::int * interval '1 day') GROUP BY 1 ORDER BY 1
                """, days)
            by_job = await conn.fetch(
                """
                SELECT u.job_id, coalesce(j.name, u.job_id) AS name, count(*) AS fires, sum(total_tokens) AS total_tokens,
                       avg(total_tokens) AS avg_tokens, avg(duration_ms) AS avg_duration_ms
                FROM fleet_usage u LEFT JOIN fleet_jobs j ON j.job_id = u.job_id
                WHERE u.ts > now() - ($1::int * interval '1 day') GROUP BY 1, 2 ORDER BY sum(total_tokens) DESC LIMIT 25
                """, days)
            runs = await conn.fetchrow(
                """
                SELECT count(*) AS runs, count(*) FILTER (WHERE status = 'failed') AS failed,
                       count(*) FILTER (WHERE status = 'completed') AS completed
                FROM fleet_runs WHERE claimed_at > now() - ($1::int * interval '1 day')
                """, days)
        return {
            "schema_version": "fleet_usage_v1", "days": days,
            "daily": [{"day": d["day"].date().isoformat(), "fires": int(d["fires"]), "prompt_tokens": int(d["prompt_tokens"] or 0),
                       "completion_tokens": int(d["completion_tokens"] or 0), "total_tokens": int(d["total_tokens"] or 0)} for d in daily],
            "by_job": [{"job_id": b["job_id"], "name": b["name"], "fires": int(b["fires"]), "total_tokens": int(b["total_tokens"] or 0),
                        "avg_tokens": int(b["avg_tokens"] or 0), "avg_duration_ms": int(b["avg_duration_ms"] or 0)} for b in by_job],
            "runs": {k: int(runs[k] or 0) for k in ("runs", "failed", "completed")} if runs else {},
            "note": "Tokens are the fleet's own usage audit (model calls only; script jobs use none). No price is assumed: "
                    "multiply by your provider's rate to estimate cost.",
        }

    @router.post("/state/fleet/directives")
    async def create_directive(req: DirectiveRequest):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        if req.kind not in DIRECTIVE_KINDS:
            raise HTTPException(status_code=400, detail=f"kind must be one of {', '.join(DIRECTIVE_KINDS)}")
        if req.kind == "set_schedule":
            if req.preset not in SCHEDULE_PRESETS:
                raise HTTPException(status_code=400, detail=f"preset must be one of {', '.join(SCHEDULE_PRESETS)}")
            payload = {"schedule": SCHEDULE_PRESETS[req.preset], "preset": req.preset}
        elif req.kind == "set_enabled":
            if req.enabled is None:
                raise HTTPException(status_code=400, detail="enabled is required")
            payload = {"enabled": req.enabled}
        else:
            if not req.workdir:
                raise HTTPException(status_code=400, detail="workdir is required")
            payload = {"workdir": req.workdir}
        async with state.pool.acquire() as conn:
            exists = await conn.fetchval("SELECT 1 FROM fleet_jobs WHERE job_id = $1", req.job_id)
            if not exists:
                raise HTTPException(status_code=404, detail="unknown job; wait for the next fleet snapshot")
            row = await conn.fetchrow(
                "INSERT INTO fleet_directives (job_id, kind, payload, requested_by) VALUES ($1, $2, $3::jsonb, $4) RETURNING id, requested_at",
                req.job_id, req.kind, json.dumps(payload), req.requested_by,
            )
        return {"id": str(row["id"]), "job_id": req.job_id, "kind": req.kind, "payload": payload, "status": "pending",
                "requested_at": row["requested_at"].isoformat()}

    @router.get("/state/fleet/directives")
    async def list_directives(status: str | None = Query(None), limit: int = Query(50, ge=1, le=200)):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT d.*, j.name FROM fleet_directives d LEFT JOIN fleet_jobs j ON j.job_id = d.job_id "
                "WHERE ($1::text IS NULL OR d.status = $1) ORDER BY d.requested_at DESC LIMIT $2", status, limit)
        return {"directives": [{**{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in dict(r).items() if k not in ("payload", "previous")},
                                "id": str(r["id"]), "payload": _json(r["payload"]), "previous": _json(r["previous"])} for r in rows]}

    @router.post("/state/fleet/directives/report")
    async def report_directive(report: DirectiveReport):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        if report.status not in ("applied", "failed"):
            raise HTTPException(status_code=400, detail="status must be applied or failed")
        async with state.pool.acquire() as conn:
            n = await conn.execute(
                "UPDATE fleet_directives SET status = $2, applied_at = now(), previous = $3::jsonb, detail = $4 WHERE id = $1::uuid AND status = 'pending'",
                report.id, report.status, json.dumps(report.previous) if report.previous is not None else None, report.detail,
            )
        return {"updated": n.endswith("1")}

    app.include_router(router)


def _json(value: Any) -> Any:
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value
