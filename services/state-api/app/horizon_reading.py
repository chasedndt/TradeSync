"""Hermes readings of the timeframe outlook, one per band, kept with the measurement they read.

A reading is drafted by Hermes from the measured numbers only, through the
harness boundary route, so the answer is filed in quarantine with a receipt and
stays advisory. Each band (short term, lower, medium and higher time frame)
has its own reading. Every attempt is stored (``ops/migrations/030``) with when
it started and finished and the measurement it read, so the page can show the
reading's exact time, keep the last good reading visible while a new one runs
or fails, and flag a reading older than the numbers under it. Without a
database (tests, tooling) attempts are kept in memory.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Mapping

import httpx

from app import agent_connector
from app.horizon_reading_facts import FEATURE_NAMES, facts
from tradesync_core.horizon_spec import BANDS, HORIZONS

SELF_URL = os.getenv("STATE_API_SELF_URL", "http://localhost:8000").rstrip("/")
READING_TIMEOUT_S = 300.0
RUNNING_EXPIRES_S = 600
SCOPES = tuple(BANDS)

_memory: dict[tuple[str, str], list[dict[str, Any]]] = {}
_tasks: set[asyncio.Task] = set()


def prompt(symbol: str, scope: str) -> str:
    horizons = ", ".join(h.label for h in HORIZONS if h.band == scope)
    return (
        f"Write a private reading of the {BANDS[scope].lower()} outlook ({horizons}) for {symbol}, for a crypto trader, "
        "from the measured facts below only. Plain prose in three short paragraphs: where trend and momentum stand at each "
        "horizon and what the record says; which features earned weight out of sample and what the weighted reading is "
        "(say plainly when nothing earned weight); and the levels that matter and what would change the picture. "
        f"Refer to features by exactly these names: {', '.join(FEATURE_NAMES)}. Each record says what followed past bars "
        "in the same state; say when a record is too thin to judge. These are records, not forecasts: do not predict "
        "prices, recommend trades or state probabilities beyond those given. No JSON, no lists, no headings, at most 250 words."
    )


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _view(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The newest attempt, and the newest good reading's text and times."""
    if not rows:
        return {"status": "none"}
    latest = rows[0]
    status = latest["status"]
    started = latest["started_at"]
    if status == "running" and (datetime.now(timezone.utc) - started).total_seconds() > RUNNING_EXPIRES_S:
        status = "unavailable"
    good = next((r for r in rows if r["status"] == "ok"), None)
    view: dict[str, Any] = {
        "status": status,
        "attempt": {"status": status, "started_at": _iso(started), "finished_at": _iso(latest.get("finished_at")),
                    "detail": latest.get("detail") if status == latest["status"] else "interrupted before it finished"},
    }
    if good:
        view.update(content=good.get("content") or "", model=good.get("model"), measured_at=_iso(good["measured_at"]),
                    started_at=_iso(good["started_at"]), finished_at=_iso(good.get("finished_at")),
                    authority="advisory_only", source="Hermes gateway via the harness boundary")
    return view


async def latest(pool, symbol: str) -> dict[str, dict[str, Any]]:
    if not pool:
        return {scope: _view(_memory.get((symbol, scope), [])) for scope in SCOPES}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT scope, status, measured_at, started_at, finished_at, content, model, detail FROM ("
            " SELECT *, row_number() OVER (PARTITION BY scope ORDER BY started_at DESC) AS n FROM horizon_readings"
            " WHERE symbol = $1) ranked WHERE n <= 6 ORDER BY scope, started_at DESC",
            symbol,
        )
    by_scope: dict[str, list[dict[str, Any]]] = {scope: [] for scope in SCOPES}
    for row in rows:
        by_scope.setdefault(row["scope"], []).append(dict(row))
    return {scope: _view(by_scope.get(scope, [])) for scope in SCOPES}


async def _insert(pool, symbol: str, scope: str, measured_at: datetime) -> Any:
    now = datetime.now(timezone.utc)
    if not pool:
        row = {"id": f"{symbol}:{scope}:{time.monotonic_ns()}", "status": "running", "measured_at": measured_at, "started_at": now}
        _memory.setdefault((symbol, scope), []).insert(0, row)
        return row["id"]
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO horizon_readings (symbol, scope, status, measured_at, started_at) VALUES ($1, $2, 'running', $3, $4) RETURNING id",
            symbol, scope, measured_at, now,
        )


async def _finish(pool, symbol: str, scope: str, row_id: Any, **fields: Any) -> None:
    fields["finished_at"] = datetime.now(timezone.utc)
    if not pool:
        for row in _memory.get((symbol, scope), []):
            if row["id"] == row_id:
                row.update(fields)
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE horizon_readings SET status = $2, content = $3, model = $4, detail = $5, receipt = $6::jsonb, finished_at = $7 WHERE id = $1",
            row_id, fields["status"], fields.get("content"), fields.get("model"), fields.get("detail"),
            json.dumps(fields["receipt"]) if fields.get("receipt") is not None else None, fields["finished_at"],
        )


async def run_reading(pool, symbol: str, scope: str, row_id: Any, outlook: Mapping[str, Any], evaluation: Mapping[str, Any]) -> None:
    if not agent_connector.configured():
        await _finish(pool, symbol, scope, row_id, status="not_configured", detail="the Hermes gateway is not configured")
        return
    text = prompt(symbol, scope) + "\n\nFACTS:\n" + facts(symbol, scope, outlook, evaluation)[:24000]
    try:
        async with httpx.AsyncClient(timeout=READING_TIMEOUT_S, trust_env=False) as client:
            response = await client.post(f"{SELF_URL}/state/agents/harness/ask", json={"intent": "summarise", "prompt": text})
    except httpx.HTTPError as exc:
        await _finish(pool, symbol, scope, row_id, status="unavailable", detail=type(exc).__name__)
        return
    if response.status_code == 422:
        await _finish(pool, symbol, scope, row_id, status="refused", detail=str(response.json().get("detail", ""))[:300])
    elif response.status_code != 200:
        await _finish(pool, symbol, scope, row_id, status="unavailable", detail=f"HTTP {response.status_code}")
    else:
        body = response.json()
        await _finish(pool, symbol, scope, row_id, status="ok", content=body.get("content", ""), model=body.get("model"),
                      receipt=body.get("receipt"))


async def start(pool, symbol: str, scope: str, outlook: Mapping[str, Any], evaluation: Mapping[str, Any],
                measured_at: datetime) -> dict[str, Any]:
    current = (await latest(pool, symbol)).get(scope) or {}
    if current.get("status") == "running":
        return {"status": "already_running", "reading": current}
    row_id = await _insert(pool, symbol, scope, measured_at)
    task = asyncio.create_task(run_reading(pool, symbol, scope, row_id, outlook, evaluation))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    await asyncio.sleep(0)
    return {"status": "started", "reading": (await latest(pool, symbol)).get(scope)}
