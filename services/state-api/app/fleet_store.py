"""Writes for the fleet read model: the job registry, execution ledger and token usage from bridge snapshots."""

from __future__ import annotations

import json

from app.fleet_models import JobSnapshot, RunSnapshot, UsageSnapshot


async def _upsert_jobs(conn, jobs: list[JobSnapshot]) -> None:
    for j in jobs:
        await conn.execute(
            """
            INSERT INTO fleet_jobs (job_id, name, enabled, schedule, schedule_display, deliver, workdir, script, no_agent, model,
                                    description, last_run_at, last_status, next_run_at, state, last_error, last_delivery_error, snapshot_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, now())
            ON CONFLICT (job_id) DO UPDATE SET name = EXCLUDED.name, enabled = EXCLUDED.enabled, schedule = EXCLUDED.schedule,
                schedule_display = EXCLUDED.schedule_display, deliver = EXCLUDED.deliver, workdir = EXCLUDED.workdir,
                script = EXCLUDED.script, no_agent = EXCLUDED.no_agent, model = EXCLUDED.model, description = EXCLUDED.description,
                last_run_at = EXCLUDED.last_run_at, last_status = EXCLUDED.last_status, next_run_at = EXCLUDED.next_run_at,
                state = EXCLUDED.state, last_error = EXCLUDED.last_error, last_delivery_error = EXCLUDED.last_delivery_error,
                snapshot_at = now()
            """,
            j.job_id, j.name, j.enabled, json.dumps(j.schedule), j.schedule_display, j.deliver, j.workdir, j.script,
            j.no_agent, j.model, j.description, j.last_run_at, j.last_status, j.next_run_at, j.state,
            j.last_error, j.last_delivery_error,
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
