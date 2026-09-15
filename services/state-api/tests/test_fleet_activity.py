"""The Fleet page's run progress and outputs: running now, the last runs, each job's latest stored output and its full text.

Output text is served as stored with secret-shaped strings masked and nothing added.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import fleet_activity
from app.fleet_output_index import OVERLAP, OutputIndex
from app.main import app, state

client = TestClient(app)
NOW = datetime.now(timezone.utc)
JOB, SCRIPT_JOB, OLD_JOB = "6a1fdf7894c7", "0a1b2c3d4e5f", "ffffffffffff"
O1, O2, O3, O4, O5 = (str(uuid.UUID(int=n)) for n in (1, 2, 3, 4, 5))
WEBHOOK = "https://discord.com/api/webhooks/123456/abcDEF_-9xyz"
CONTENT = "Thesis for BTC\n\nposted to " + WEBHOOK + "\n" + "\n".join(f"line {i}: resting liquidity held above the wall" for i in range(80))


def ago(**delta) -> datetime:
    return NOW - timedelta(**delta)


def output_row(output_id, job_id, received, content, accepted=True, reasons=None):
    payload = {"schema_version": "hermes_job_output_v1", "kind": "hermes_job_output", "agent": "StrikeZone thesis", "job_id": job_id,
               "delivery": {"kind": "discord", "channel_id": "1517902266332348490", "channel_label": "thesis-desk"},
               "ran_at_stamp": "20260915_010000", "content": content, "content_truncated": False, "filename": f"{job_id}_20260915_010000.txt"}
    return {"id": uuid.UUID(output_id), "accepted": accepted, "reasons": json.dumps(reasons or []),
            "observed_at": received - timedelta(seconds=30), "received_at": received, "payload": json.dumps(payload)}


def run(run_id, job_id, status, claimed, started=None, finished=None, duration_ms=None, error=None, snapshot=None):
    return {"id": run_id, "job_id": job_id, "status": status, "claimed_at": claimed, "started_at": started, "finished_at": finished,
            "duration_ms": duration_ms, "error": error, "snapshot_at": snapshot or ago(minutes=2)}


def data():
    running = run("r3", JOB, "running", ago(minutes=4), started=ago(minutes=3))
    stuck = run("s0", SCRIPT_JOB, "claimed", ago(days=2), snapshot=ago(days=2))
    return {
        "runs": [running,
                 run("r2", JOB, "completed", ago(hours=1), ago(hours=1), ago(minutes=58), 120_000),
                 run("r1", JOB, "failed", ago(hours=2), ago(hours=2), ago(minutes=118), 3_000,
                     "Traceback (most recent call last):\nRuntimeError: token=abcdefghijklmnop rejected"),
                 run("s2", SCRIPT_JOB, "completed", ago(minutes=21), ago(minutes=21), ago(minutes=20), 40_000),
                 run("s1", SCRIPT_JOB, "completed", ago(hours=3), ago(hours=3), ago(hours=3), 41_000)],
        "running": [running, stuck],
        "fires": [{"job_id": JOB, "ts": ago(minutes=58), "model": "model-a", "duration_ms": 118_000,
                   "deliver_target": "discord:1517902266332348490", "response_silent": False, "error": None}],
        "snapshot": {"runs_snapshot_at": ago(minutes=2), "jobs_snapshot_at": ago(minutes=2), "usage_newest_at": ago(hours=8),
                     "outputs_received_at": ago(minutes=57)},
        "outputs": [output_row(O1, JOB, ago(hours=26), "an older thesis"),
                    output_row(O2, JOB, ago(minutes=57), CONTENT),
                    output_row(O3, SCRIPT_JOB, ago(hours=2), "quant bridge: 3 rows",
                               accepted=False, reasons=[{"code": "submission_stale", "detail": "observed 20 minutes before receipt"}]),
                    output_row(O4, OLD_JOB, ago(days=9), "outside the first read")],
    }


class Conn:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple]] = []

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        if "row_number()" in sql:
            return self.rows["runs"]
        if "finished_at IS NULL" in sql:
            return self.rows["running"]
        if "FROM fleet_usage" in sql:
            return self.rows["fires"]
        if "AS job_id FROM quarantine_intake" in sql:
            return [{"id": r["id"], "received_at": r["received_at"], "job_id": json.loads(r["payload"])["job_id"]}
                    for r in sorted(self.rows["outputs"], key=lambda r: r["received_at"]) if r["received_at"] > args[0]]
        if "id = ANY" in sql:
            return [r for r in self.rows["outputs"] if str(r["id"]) in args[0]]
        raise AssertionError(sql)

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        if "max(snapshot_at)" in sql:
            return self.rows["snapshot"]
        if "id = $1::uuid" in sql:
            return next((r for r in self.rows["outputs"] if str(r["id"]) == args[0]), None)
        raise AssertionError(sql)


def fake_pool(conn: Conn) -> MagicMock:
    pool = MagicMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool.acquire = acquire
    return pool


def test_activity_shows_what_runs_now_the_last_runs_and_each_jobs_latest_output() -> None:
    with patch.object(state, "pool", fake_pool(Conn(data()))), patch.object(fleet_activity, "INDEX", OutputIndex()):
        response = client.get("/state/fleet/activity?runs=5")
    body = response.json()
    assert response.status_code == 200 and body["schema_version"] == "fleet_activity_v1" and body["outputs_indexed_since"]

    job = body["jobs"][JOB]
    [running] = job["running"]
    assert running["id"] == "r3" and running["running"] and running["in_latest_snapshot"] and 175 <= running["elapsed_s"] <= 200
    assert [r["status"] for r in job["runs"]] == ["running", "completed", "failed"]
    assert job["runs"][1]["duration_ms"] == 120_000 and job["runs"][1]["finished_at"]
    assert "token=[redacted]" in job["runs"][2]["error"] and "abcdefghijklmnop" not in job["runs"][2]["error"]
    output = job["latest_output"]
    assert output["id"] == O2 and output["masked"] == 1 and WEBHOOK not in json.dumps(body)
    assert output["first_lines"][:2] == ["Thesis for BTC", "posted to https://discord.com/api/webhooks/[redacted]"]
    assert len(output["first_lines"]) == 6 and output["bytes"] == len(CONTENT.encode()) and output["lines"] == len(CONTENT.splitlines())
    assert output["delivery"] == {"kind": "discord", "channel_label": "thesis-desk"} and output["accepted"] and "text" not in output
    assert job["later_runs_without_output"] == 0
    assert job["latest_fire"] == {"ts": data()["fires"][0]["ts"].isoformat(), "model": "model-a", "duration_ms": 118_000, "silent": False,
                                  "deliver_target": "discord:1517902266332348490", "error": None}

    script = body["jobs"][SCRIPT_JOB]
    assert script["latest_output"]["accepted"] is False and script["latest_output"]["refused_because"] == ["submission_stale"]
    assert script["later_runs_without_output"] == 1 and script["latest_fire"] is None
    [stuck] = script["running"]
    assert stuck["id"] == "s0" and stuck["in_latest_snapshot"] is False and stuck["elapsed_s"] >= 2 * 86400
    assert OLD_JOB not in body["jobs"]  # its only output is older than the index's first read

    snapshot = body["snapshot"]
    assert 115 <= snapshot["runs_snapshot_age_s"] <= 140 and snapshot["usage_newest_age_s"] >= 8 * 3600
    assert snapshot["bridge_every_s"] == {"fleet": 300, "outputs": 120} and snapshot["outputs_received_at"]


def test_the_drawer_reads_the_full_stored_text_masked_and_with_nothing_added() -> None:
    with patch.object(state, "pool", fake_pool(Conn(data()))), patch.object(fleet_activity, "INDEX", OutputIndex()):
        listed = client.get(f"/state/fleet/jobs/{JOB}/outputs").json()
        full = client.get(f"/state/fleet/outputs/{O2}")
        unknown = client.get(f"/state/fleet/outputs/{uuid.uuid4()}")
        malformed = client.get("/state/fleet/outputs/not-a-uuid")
    assert [o["id"] for o in listed["outputs"]] == [O2, O1] and listed["latest"]["id"] == O2 and listed["indexed_since"]
    body = full.json()
    assert full.status_code == 200 and len(body["text"]) > 1500
    assert body["text"] == CONTENT.replace(WEBHOOK, "https://discord.com/api/webhooks/[redacted]") and body["masked"] == 1
    assert body["note"] and unknown.status_code == 404 and malformed.status_code == 404


def test_the_output_index_reads_only_rows_received_since_the_newest_it_has_seen() -> None:
    rows = data()
    conn = Conn(rows)
    index = OutputIndex()
    asyncio.run(index.refresh(conn, NOW))
    [first] = [args for sql, args in conn.calls if "AS job_id" in sql]
    assert NOW - first[0] == timedelta(days=8) and index.latest[JOB]["id"] == O2 and OLD_JOB not in index.latest

    rows["outputs"].append(output_row(O5, JOB, NOW + timedelta(seconds=1), "a fresh thesis"))
    conn.calls.clear()
    asyncio.run(index.refresh(conn, NOW))  # within the refresh interval: nothing is read
    assert conn.calls == []
    asyncio.run(index.refresh(conn, NOW, force=True))
    [since] = [args for sql, args in conn.calls if "AS job_id" in sql]
    assert since[0] == ago(minutes=57) - OVERLAP
    assert [args for sql, args in conn.calls if "id = ANY" in sql] == [([O5],)]  # only the job whose newest output changed
    assert index.latest[JOB]["id"] == O5 and [o["id"] for o in index.outputs_for(JOB)] == [O5, O2, O1]


def test_without_a_database_the_routes_say_so() -> None:
    with patch.object(state, "pool", None):
        assert client.get("/state/fleet/activity").status_code == 503
        assert client.get(f"/state/fleet/outputs/{O2}").status_code == 503


class SlowOutputs(Conn):
    async def fetch(self, sql, *args):
        if "AS job_id FROM quarantine_intake" in sql:
            raise asyncio.TimeoutError()
        return await super().fetch(sql, *args)


def test_a_failed_output_read_keeps_the_runs_and_says_why() -> None:
    with patch.object(state, "pool", fake_pool(SlowOutputs(data()))), patch.object(fleet_activity, "INDEX", OutputIndex()):
        page = client.get("/state/fleet/activity")
        listed = client.get(f"/state/fleet/jobs/{JOB}/outputs")
    body = page.json()
    assert page.status_code == 200 and "TimeoutError" in body["outputs_unavailable"]
    assert [r["status"] for r in body["jobs"][JOB]["runs"]] == ["running", "completed", "failed"]
    assert body["jobs"][JOB].get("latest_output") is None
    assert listed.status_code == 503 and "TimeoutError" in listed.json()["detail"]
