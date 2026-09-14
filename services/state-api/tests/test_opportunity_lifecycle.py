"""Opportunities expire at their TTL: at read, in storage, and in the quiet-state summary."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app import background
from app.main import app, state
from app.opportunity_lifecycle import (
    DEFAULT_TTL_SECONDS,
    EXPIRES_AT_SQL,
    REFUSAL_LABELS,
    expire_pass,
    quiet_summary,
    status_filter,
)

client = TestClient(app)
NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _restore_pool():
    before = state.pool
    yield
    state.pool = before


def pool_with(conn):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__.return_value = conn
    cm.__aexit__.return_value = None
    pool.acquire.return_value = cm
    return pool


def test_rows_without_an_expiry_use_the_default_ttl() -> None:
    assert EXPIRES_AT_SQL == f"COALESCE(expires_at, snapshot_ts + make_interval(secs => {DEFAULT_TTL_SECONDS}))"


def test_new_means_not_yet_expired() -> None:
    params: list = []
    clause = status_filter("new", params)
    assert params == ["new"]
    assert "status = $1" in clause and f"{EXPIRES_AT_SQL} > now()" in clause


def test_expired_includes_new_rows_past_their_ttl() -> None:
    params: list = ["BTC-PERP"]
    clause = status_filter("expired", params)
    assert params == ["BTC-PERP", "expired"]
    assert "status = $2" in clause and "status = 'new'" in clause and f"{EXPIRES_AT_SQL} <= now()" in clause


def test_other_statuses_filter_as_stored() -> None:
    assert status_filter("previewed", []) == "status = $1"


def test_the_expiry_pass_marks_only_new_rows_past_expiry_and_counts_them() -> None:
    conn = AsyncMock()
    conn.execute.return_value = "UPDATE 3"
    assert asyncio.run(expire_pass(conn)) == 3
    sql = conn.execute.call_args[0][0]
    assert "SET status = 'expired'" in sql and "WHERE status = 'new'" in sql and EXPIRES_AT_SQL in sql


def test_the_expiry_loop_is_registered_with_the_lifespan() -> None:
    assert "opportunity_expiry" in background.registered()


def test_the_list_reports_effective_status_and_expiry() -> None:
    conn = AsyncMock()
    conn.fetch.return_value = [{
        "id": "opp-1", "symbol": "BTC-PERP", "timeframe": "1m", "bias": 0.2, "quality": 45.0, "dir": "LONG",
        "status": "expired", "snapshot_ts": NOW, "expires_at": NOW + timedelta(minutes=15),
        "links": {}, "confluence": {},
    }]
    state.pool = pool_with(conn)
    response = client.get("/state/opportunities?status=expired&limit=5")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["status"] == "expired"
    assert body[0]["expires_at"].startswith("2026-09-14T12:15")
    query = conn.fetch.call_args[0][0]
    assert "AS status" in query and "AS expires_at" in query
    assert conn.fetch.call_args[0][1:] == ("expired", 5)


def test_the_quiet_summary_names_the_last_opportunity_and_top_refusals() -> None:
    conn = AsyncMock()
    conn.fetchval.return_value = 0
    conn.fetchrow.side_effect = [
        {"id": "opp-9", "symbol": "ETH-PERP", "dir": "SHORT", "snapshot_ts": NOW, "expires_at": NOW + timedelta(minutes=15)},
        {"total": 600, "admitted": 0, "refused": 600, "last_verdict_at": NOW},
    ]
    conn.fetch.return_value = [
        {"code": "coverage_below_emit_floor", "refusals": 420, "example_detail": "data coverage 0.25 is below the 0.3 floor"},
        {"code": "score_inside_deadband", "refusals": 180, "example_detail": "directional score 0.08"},
    ]
    summary = asyncio.run(quiet_summary(conn, 60))
    assert summary["live"] == 0
    assert summary["last_opportunity"] == {
        "id": "opp-9", "symbol": "ETH-PERP", "direction": "SHORT",
        "opened_at": NOW.isoformat(), "expires_at": (NOW + timedelta(minutes=15)).isoformat(),
    }
    assert summary["verdicts"]["refused"] == 600
    top = summary["top_refusal_reasons"][0]
    assert top["label"] == REFUSAL_LABELS["coverage_below_emit_floor"]
    assert top["share_of_refusals"] == 0.7


def test_the_lifecycle_route_serves_the_summary() -> None:
    conn = AsyncMock()
    conn.fetchval.return_value = 2
    conn.fetchrow.side_effect = [None, {"total": 10, "admitted": 2, "refused": 8, "last_verdict_at": None}]
    conn.fetch.return_value = []
    state.pool = pool_with(conn)
    response = client.get("/state/opportunities/lifecycle?window_minutes=30")
    assert response.status_code == 200
    body = response.json()
    assert body["live"] == 2 and body["last_opportunity"] is None and body["window_minutes"] == 30


def test_the_lifecycle_route_needs_the_database() -> None:
    state.pool = None
    assert client.get("/state/opportunities/lifecycle").status_code == 503
