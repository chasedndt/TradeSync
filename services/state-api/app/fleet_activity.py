"""Each Hermes job's run progress and output on the Fleet page: what is running now, the last runs, the latest stored output.

Read-only over the fleet read model (``fleet_runs`` and ``fleet_usage``, posted by
the host fleet bridge from the fleet's execution ledger and usage audit) and the
job outputs the output bridge stored in quarantine. The directive controls stay in
``fleet.py``; nothing here changes a job or a stored output.

- ``GET /state/fleet/activity``: per job, runs running now with elapsed time, the
  last runs with status, duration and error, the latest stored output's summary and
  the latest model call, and how old each bridge snapshot is.
- ``GET /state/fleet/jobs/{job_id}/outputs``: the job's recent stored outputs.
- ``GET /state/fleet/outputs/{output_id}``: one stored output's full text.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app import fleet_activity_view as view
from app.fleet_output_index import INDEX

router = APIRouter(tags=["fleet"])

RUNS_SQL = """
SELECT id, job_id, status, claimed_at, started_at, finished_at, duration_ms, error, snapshot_at FROM (
    SELECT r.*, row_number() OVER (PARTITION BY job_id ORDER BY coalesce(claimed_at, started_at, finished_at) DESC NULLS LAST, id DESC) AS n
    FROM fleet_runs r
) ranked WHERE n <= $1 ORDER BY job_id, n
"""
RUNNING_SQL = """
SELECT id, job_id, status, claimed_at, started_at, finished_at, duration_ms, error, snapshot_at FROM fleet_runs
WHERE finished_at IS NULL AND NOT (lower(status) = ANY($1::text[])) ORDER BY coalesce(started_at, claimed_at)
"""
FIRES_SQL = """
SELECT DISTINCT ON (job_id) job_id, ts, model, duration_ms, deliver_target, response_silent, error
FROM fleet_usage ORDER BY job_id, ts DESC
"""
SNAPSHOT_SQL = """
SELECT (SELECT max(snapshot_at) FROM fleet_runs) AS runs_snapshot_at,
       (SELECT max(snapshot_at) FROM fleet_jobs) AS jobs_snapshot_at,
       (SELECT max(ts) FROM fleet_usage) AS usage_newest_at,
       (SELECT max(received_at) FROM quarantine_intake WHERE source = 'chaseos') AS outputs_received_at
"""
OUTPUT_SQL = ("SELECT id, accepted, reasons, observed_at, received_at, payload FROM quarantine_intake "
              "WHERE id = $1::uuid AND source = 'chaseos' AND payload->>'kind' = 'hermes_job_output'")


def register(app, state) -> None:
    def pool():
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        return state.pool

    @router.get("/state/fleet/activity")
    async def activity(runs: int = Query(5, ge=1, le=20)):
        now = datetime.now(timezone.utc)
        async with pool().acquire() as conn:
            run_rows = await conn.fetch(RUNS_SQL, runs)
            running_rows = await conn.fetch(RUNNING_SQL, sorted(view.TERMINAL))
            fire_rows = await conn.fetch(FIRES_SQL)
            snapshot = await conn.fetchrow(SNAPSHOT_SQL)
            await INDEX.refresh(conn, now)
        return view.activity_payload(run_rows, running_rows, INDEX.latest, fire_rows, snapshot, now, INDEX.since)

    @router.get("/state/fleet/jobs/{job_id}/outputs")
    async def job_outputs(job_id: str):
        async with pool().acquire() as conn:
            await INDEX.refresh(conn)
        return {"job_id": job_id, "outputs": INDEX.outputs_for(job_id), "latest": INDEX.latest.get(job_id),
                "indexed_since": view.iso(INDEX.since), "note": view.NOTE}

    @router.get("/state/fleet/outputs/{output_id}")
    async def output(output_id: str):
        try:
            uuid.UUID(output_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="no stored Hermes job output has that id") from None
        async with pool().acquire() as conn:
            row = await conn.fetchrow(OUTPUT_SQL, output_id)
        if row is None:
            raise HTTPException(status_code=404, detail="no stored Hermes job output has that id")
        return view.output_text(row)

    app.include_router(router)
