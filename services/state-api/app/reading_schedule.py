"""Hermes readings of the timeframe outlook on an operator's daily schedule, off unless turned on.

Hermes compute is constrained, so no band of any market is read on a schedule
until an operator sets one on the Timeframes page, with a confirmation. Every
change keeps an audit row with who made it, when and the value it replaced
(``ops/migrations/033``). Once a minute the loop starts a reading for each
enabled band whose daily time has come (``reading_schedule_rules``), through the
same start and run logic as the page's own button (``horizon_reading.start``). It
skips the slot, and records why, when a reading of the current measurement
already exists, when one is running, when there is nothing measured to read, or
when the Hermes gateway is not configured.

- ``GET /state/market/horizons/reading-schedule?symbol=``: each band's schedule,
  its next reading, the last slot handled and what happened, and recent changes.
- ``PUT /state/market/horizons/reading-schedule``: set one band's schedule.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import agent_connector, background, horizon_reading, horizons
from app import reading_schedule_rules as rules
from app import reading_schedule_store as store

router = APIRouter(tags=["market"])

CHECK_EVERY_S = 60
GRACE_MINUTES = int(rules.GRACE.total_seconds() // 60)
NOTE = ("Off unless an operator turns it on, because Hermes compute is constrained. Times are UTC. A scheduled reading "
        "goes through the same harness boundary as the page's own button; a slot is skipped, with the reason, when a "
        "reading of the current measurement already exists or one is running, and a slot missed by more than "
        f"{GRACE_MINUTES} minutes is not started late.")


class ScheduleChange(BaseModel):
    symbol: str = Field(max_length=24)
    scope: str = Field(pattern="^(short|lower|medium|higher)$")
    enabled: bool
    daily_time: str = Field(max_length=5)
    changed_by: str = Field(default="operator", min_length=1, max_length=64)


def _loads(value: Any) -> Any:
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def band_view(row: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
    if not row:
        return {"enabled": False, "daily_time": None, "next_reading_at": None, "updated_by": None, "updated_at": None, "last": None}
    next_at = rules.next_slot(now, row["daily_time"], row["updated_at"], row.get("last_slot")) if row["enabled"] else None
    last = ({"slot": rules.iso(row["last_slot"]), "result": row.get("last_result"), "detail": row.get("last_detail") or None}
            if row.get("last_slot") else None)
    return {"enabled": bool(row["enabled"]), "daily_time": rules.time_text(row["daily_time"]), "next_reading_at": rules.iso(next_at),
            "updated_by": row["updated_by"], "updated_at": rules.iso(row["updated_at"]), "last": last}


def change_view(change: dict[str, Any]) -> dict[str, Any]:
    return {"scope": change["scope"], "changed_by": change["changed_by"], "changed_at": rules.iso(change["changed_at"]),
            "previous": _loads(change.get("previous")), "next": _loads(change.get("next"))}


async def start_scheduled(pool, market_data_url: str, symbol: str, scope: str) -> tuple[str, str]:
    """Start one scheduled reading through the page's own start logic, or say why it was skipped."""
    if not agent_connector.configured():
        return "skipped", "the Hermes gateway is not configured"
    entry, error = await horizons.part_or_error(market_data_url, symbol, "short" if scope == "short" else "long")
    if entry is None:
        return "skipped", f"no measurement to read ({error})"
    if not entry["outlook"].get("available"):
        return "skipped", "not enough history to read"
    measured_at = datetime.fromtimestamp(entry["at"], timezone.utc)
    current = (await horizon_reading.latest(pool, symbol)).get(scope) or {}
    if current.get("status") == "running":
        return "skipped", "a reading is already running"
    if current.get("measured_at") and datetime.fromisoformat(current["measured_at"]) >= measured_at:
        return "skipped", f"a reading of the measurement of {measured_at:%d %b %H:%M} UTC already exists"
    started = await horizon_reading.start(pool, symbol, scope, entry["outlook"], entry["evaluation"], measured_at)
    if started.get("status") != "started":
        return "skipped", "a reading is already running"
    return "started", f"reading the measurement of {measured_at:%d %b %H:%M} UTC"


async def run_due(pool, market_data_url: str, now: datetime | None = None) -> list[dict[str, Any]]:
    """One pass: record missed slots, then start every enabled band whose slot is due. Returns what was handled."""
    now = now or datetime.now(timezone.utc)
    handled: list[dict[str, Any]] = []
    for row in await store.enabled(pool):
        symbol, scope, armed, last = row["symbol"], row["scope"], row["updated_at"], row.get("last_slot")
        missed = rules.missed_slot(now, row["daily_time"], armed, last)
        if missed and await store.claim(pool, symbol, scope, missed, armed, "missed",
                                        f"the state API was not running within {GRACE_MINUTES} minutes of the slot"):
            last = missed
            handled.append({"symbol": symbol, "scope": scope, "slot": missed, "result": "missed"})
        slot = rules.due_slot(now, row["daily_time"], armed, last)
        if slot is None or not await store.claim(pool, symbol, scope, slot, armed, "starting", ""):
            continue
        try:
            result, detail = await start_scheduled(pool, market_data_url, symbol, scope)
        except Exception as exc:  # the slot stays claimed: it is not retried, and the page says it failed
            result, detail = "failed", type(exc).__name__
        await store.finish(pool, symbol, scope, slot, result, detail)
        handled.append({"symbol": symbol, "scope": scope, "slot": slot, "result": result, "detail": detail})
    return handled


def register(app, state, *, market_data_url: str) -> None:
    @router.get("/state/market/horizons/reading-schedule")
    async def get_schedule(symbol: str = Query("BTC-PERP", max_length=24)):
        symbol = horizons.checked_symbol(symbol)
        pool, now = getattr(state, "pool", None), datetime.now(timezone.utc)
        rows = await store.for_symbol(pool, symbol)
        return {
            "schema_version": "horizon_reading_schedule_v1", "symbol": symbol, "generated_at": rules.iso(now),
            "timezone": "UTC", "grace_minutes": GRACE_MINUTES,
            "bands": {scope: band_view(rows.get(scope), now) for scope in horizon_reading.SCOPES},
            "changes": [change_view(change) for change in await store.changes(pool, symbol)],
            "note": NOTE,
        }

    @router.put("/state/market/horizons/reading-schedule")
    async def put_schedule(change: ScheduleChange):
        symbol = horizons.checked_symbol(change.symbol)
        try:
            daily_time = rules.parse_time(change.daily_time)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        now, changed_by = datetime.now(timezone.utc), change.changed_by.strip() or "operator"
        row, previous = await store.save(getattr(state, "pool", None), symbol, change.scope, change.enabled, daily_time, changed_by, now)
        return {"symbol": symbol, "scope": change.scope, "schedule": band_view(row, now), "previous": previous,
                "changed_by": changed_by, "changed_at": rules.iso(now)}

    async def loop() -> None:
        await asyncio.sleep(90)  # let the first measurements land after a restart
        while True:
            try:
                if state.pool:
                    await run_due(state.pool, market_data_url)
            except Exception as exc:  # the next pass tries again; a claimed slot is never started twice
                print(f"[ReadingSchedule] pass failed: {type(exc).__name__}")
            await asyncio.sleep(CHECK_EVERY_S)

    background.add("horizon_reading_schedule", loop)
    app.include_router(router)
