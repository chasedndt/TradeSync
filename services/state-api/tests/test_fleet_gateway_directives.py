"""Directives go through the Hermes gateway's jobs API first, and fall back to the host bridge only where it can."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import fleet, hermes_jobs
from app.main import app, state

client = TestClient(app)
JOB = "6a1fdf7894c7"


class FakeConn:
    def __init__(self) -> None:
        self.fetchval = AsyncMock(return_value=1)
        self.fetchrow = AsyncMock(return_value={"id": "11111111-1111-1111-1111-111111111111",
                                                "requested_at": __import__("datetime").datetime(2026, 9, 13)})
        self.execute = AsyncMock()


def fake_pool(conn: FakeConn) -> MagicMock:
    pool = MagicMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool.acquire = acquire
    return pool


def before_job(**extra):
    return {"id": JOB, "enabled": True, "state": "scheduled", "deliver": "discord:123456789",
            "schedule": {"kind": "interval", "minutes": 30, "display": "every 30m"}, "schedule_display": "every 30m", **extra}


def test_a_schedule_change_is_applied_by_the_gateway_and_recorded_with_what_it_replaced() -> None:
    conn = FakeConn()
    after = before_job(schedule={"kind": "interval", "minutes": 60, "display": "every 60m"}, schedule_display="every 60m")
    with patch.object(state, "pool", fake_pool(conn)), patch.object(hermes_jobs, "available", return_value=True), \
            patch.object(hermes_jobs, "get_job", AsyncMock(return_value=before_job())), \
            patch.object(hermes_jobs, "patch_job", AsyncMock(return_value=after)) as patch_job:
        resp = client.post("/state/fleet/directives", json={"job_id": JOB, "kind": "set_schedule", "preset": "1h"})
    body = resp.json()
    assert resp.status_code == 200 and body["status"] == "applied" and body["channel"] == "api"
    assert body["previous"] == {"schedule_display": "every 30m"} and body["detail"] == "schedule -> every 60m"
    patch_job.assert_awaited_once_with(JOB, {"schedule": "every 60m"})
    insert_args = conn.fetchrow.await_args.args
    assert insert_args[5] == "applied" and insert_args[6] == "api"
    assert "UPDATE fleet_jobs" in conn.execute.await_args.args[0]


def test_a_cron_preset_is_sent_as_its_expression() -> None:
    with patch.object(state, "pool", fake_pool(FakeConn())), patch.object(hermes_jobs, "available", return_value=True), \
            patch.object(hermes_jobs, "get_job", AsyncMock(return_value=before_job())), \
            patch.object(hermes_jobs, "patch_job", AsyncMock(return_value=before_job())) as patch_job:
        client.post("/state/fleet/directives", json={"job_id": JOB, "kind": "set_schedule", "preset": "daily-08"})
    patch_job.assert_awaited_once_with(JOB, {"schedule": "0 8 * * *"})


def test_when_the_gateway_is_down_a_schedule_change_waits_for_the_bridge() -> None:
    conn = FakeConn()
    failing = AsyncMock(side_effect=hermes_jobs.HermesJobsError(502, "gateway unreachable (ConnectError)"))
    with patch.object(state, "pool", fake_pool(conn)), patch.object(hermes_jobs, "available", return_value=True), \
            patch.object(hermes_jobs, "get_job", failing):
        resp = client.post("/state/fleet/directives", json={"job_id": JOB, "kind": "set_enabled", "enabled": False})
    body = resp.json()
    assert body["status"] == "pending" and body["channel"] == "bridge" and "left for the host bridge" in body["detail"]
    conn.execute.assert_not_awaited()


def test_run_now_and_delivery_need_the_gateway() -> None:
    with patch.object(state, "pool", fake_pool(FakeConn())), patch.object(hermes_jobs, "available", return_value=False):
        run = client.post("/state/fleet/directives", json={"job_id": JOB, "kind": "run_now"})
    assert run.status_code == 503
    failing = AsyncMock(side_effect=hermes_jobs.HermesJobsError(404, "Job not found"))
    with patch.object(state, "pool", fake_pool(FakeConn())), patch.object(hermes_jobs, "available", return_value=True), \
            patch.object(hermes_jobs, "get_job", failing):
        missing = client.post("/state/fleet/directives", json={"job_id": JOB, "kind": "pause"})
    assert missing.status_code == 404 and "no bridge fallback" in missing.json()["detail"]


def test_gateway_permission_denial_never_falls_back_to_host_file_edit():
    conn = FakeConn()
    with patch.object(state, 'pool', fake_pool(conn)), patch.object(hermes_jobs, 'available', return_value=True), \
            patch.object(hermes_jobs, 'get_job', AsyncMock(side_effect=hermes_jobs.HermesJobsError(403, 'denied'))):
        response = client.post('/state/fleet/directives', json={'job_id': JOB, 'kind': 'set_enabled', 'enabled': False})
    assert response.status_code == 403
    conn.fetchrow.assert_not_awaited()


def test_delivery_targets_are_validated() -> None:
    with patch.object(state, "pool", fake_pool(FakeConn())):
        bad = client.post("/state/fleet/directives", json={"job_id": JOB, "kind": "set_deliver", "deliver": "https://example.com"})
    assert bad.status_code == 400
    assert fleet.DELIVER_RE.fullmatch("local") and fleet.DELIVER_RE.fullmatch("discord:1520762323734888449")


def test_job_ids_are_checked_before_any_request() -> None:
    try:
        hermes_jobs._checked("../etc")
    except hermes_jobs.HermesJobsError as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("an invalid job id reached the gateway")
