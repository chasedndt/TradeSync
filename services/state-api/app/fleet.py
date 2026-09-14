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

from app import hermes_jobs, hermes_link, fleet_live
from app.fleet_models import DirectiveReport, DirectiveRequest, FleetSnapshot
from app.fleet_rules import BRIDGE_KINDS, GATEWAY_KINDS, SCHEDULE_PRESETS, directive_payload
from app.fleet_store import _upsert_jobs, _upsert_runs, _upsert_usage

router = APIRouter(tags=["fleet"])


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def apply_via_gateway(job_id: str, kind: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Apply a directive through the Hermes jobs API: (values it replaced, detail, job afterwards)."""
    before = await hermes_jobs.get_job(job_id)
    if kind == "set_schedule":
        schedule = payload["schedule"]
        text = schedule.get("expr") if schedule.get("kind") == "cron" else schedule.get("display")
        after = await hermes_jobs.patch_job(job_id, {"schedule": text})
        return {"schedule_display": hermes_jobs.schedule_display(before)}, f"schedule -> {hermes_jobs.schedule_display(after)}", after
    if kind == "set_enabled":
        after = await hermes_jobs.patch_job(job_id, {"enabled": payload["enabled"]})
        return {"enabled": before.get("enabled", True)}, f"enabled -> {after.get('enabled')}", after
    if kind == "set_deliver":
        after = await hermes_jobs.patch_job(job_id, {"deliver": payload["deliver"]})
        return {"deliver": before.get("deliver")}, f"deliver -> {after.get('deliver')}", after
    if kind == "pause":
        after = await hermes_jobs.pause_job(job_id)
        return {"state": before.get("state")}, f"state -> {after.get('state')}", after
    if kind == "resume":
        after = await hermes_jobs.resume_job(job_id)
        return {"state": before.get("state")}, f"state -> {after.get('state')}", after
    after = await hermes_jobs.run_job(job_id)
    return {"last_run_at": before.get("last_run_at")}, "run requested; the gateway runs it on its next tick", after


async def refresh_job_row(conn, job: dict[str, Any]) -> None:
    """Bring the read model in line with the gateway's answer instead of waiting for the next bridge snapshot."""
    schedule = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
    await conn.execute(
        """
        UPDATE fleet_jobs SET enabled = $2, schedule = $3::jsonb, schedule_display = $4, deliver = $5, state = $6,
            next_run_at = $7, snapshot_at = now() WHERE job_id = $1
        """,
        str(job.get("id")), bool(job.get("enabled", True)), json.dumps(schedule), hermes_jobs.schedule_display(job),
        str(job.get("deliver") or "local"), job.get("state"), _parse_ts(job.get("next_run_at")),
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
            if snapshot.gateway:
                await conn.execute(
                    """
                    INSERT INTO hermes_gateway_state (id, payload, source_updated_at, snapshot_at)
                    VALUES (1, $1::jsonb, $2, now())
                    ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload,
                        source_updated_at = EXCLUDED.source_updated_at, snapshot_at = now()
                    """,
                    json.dumps(snapshot.gateway), _parse_ts(snapshot.gateway.get("updated_at")),
                )
        return {"jobs": len(snapshot.jobs), "runs": len(snapshot.runs), "usage": len(snapshot.usage), "gateway": bool(snapshot.gateway)}

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
            # The Discord target a job had before an operator switched it to TradeSync only, so it can be restored.
            restorable = await conn.fetch(
                "SELECT DISTINCT ON (job_id) job_id, previous->>'deliver' AS deliver FROM fleet_directives "
                "WHERE kind = 'set_deliver' AND status = 'applied' AND previous ? 'deliver' ORDER BY job_id, applied_at DESC")
        restore_by = {r["job_id"]: r["deliver"] for r in restorable if str(r["deliver"] or "").startswith("discord:")}
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
                "restorable_deliver": restore_by.get(j["job_id"]) if j["deliver"] == "local" else None,
            })
        newest = max((j["snapshot_at"] for j in jobs), default=None)
        out, live_state = await fleet_live.overlay(out)
        return {"schema_version": "fleet_jobs_v1", "jobs": out, "snapshot_at": newest.isoformat() if newest else None,
                "live_state": live_state,
                "presets": SCHEDULE_PRESETS,
                "control": {"gateway_api": hermes_jobs.available(), "gateway_status": hermes_link.status_now()["status"],
                            "note": "Changes go through the Hermes gateway's jobs API on its port and apply at once; "
                                    "the host bridge edits jobs.json only for the working directory or when the gateway is down."},
                "note": "Job state is read from the gateway (15-second cache), falling back explicitly to the bridge. Run counts and token usage remain bridge snapshots. Gateway acceptance of run now is not completed execution."}

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
        """Apply through the gateway's jobs API when it can; otherwise leave it pending for the host bridge.

        Every directive is recorded with the channel that applied it and the values it replaced.
        """
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        payload = directive_payload(req)
        async with state.pool.acquire() as conn:
            exists = await conn.fetchval("SELECT 1 FROM fleet_jobs WHERE job_id = $1", req.job_id)
        if not exists:
            raise HTTPException(status_code=404, detail="unknown job; wait for the next fleet snapshot")
        status, channel, previous, detail, after = "pending", "bridge", None, "", None
        if req.kind in GATEWAY_KINDS and hermes_jobs.available():
            try:
                previous, detail, after = await apply_via_gateway(req.job_id, req.kind, payload)
                fleet_live.invalidate()
                status, channel = "applied", "api"
            except hermes_jobs.HermesJobsError as exc:
                # A rejected request is not an outage: never bypass an API denial through file editing.
                if 400 <= exc.status_code < 500:
                    raise HTTPException(status_code=exc.status_code, detail="Hermes gateway rejected the directive; no bridge fallback") from None
                if req.kind not in BRIDGE_KINDS:
                    code = exc.status_code if 400 <= exc.status_code < 500 else 502
                    raise HTTPException(status_code=code, detail=f"Hermes gateway: {exc.detail}") from None
                detail = f"gateway did not apply it ({exc.detail}); left for the host bridge"
        elif req.kind not in BRIDGE_KINDS:
            raise HTTPException(status_code=503, detail="pause, resume, run now and delivery need the Hermes gateway's jobs API, which is not configured")
        async with state.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO fleet_directives (job_id, kind, payload, requested_by, status, channel, previous, detail, applied_at)
                VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7::jsonb, $8, CASE WHEN $5 = 'applied' THEN now() END)
                RETURNING id, requested_at
                """,
                req.job_id, req.kind, json.dumps(payload), req.requested_by, status, channel,
                json.dumps(previous) if previous is not None else None, detail,
            )
            if after:
                await refresh_job_row(conn, after)
        return {"id": str(row["id"]), "job_id": req.job_id, "kind": req.kind, "payload": payload, "status": status,
                "channel": channel, "previous": previous, "detail": detail, "requested_at": row["requested_at"].isoformat()}

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
