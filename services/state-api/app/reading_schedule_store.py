"""Where reading schedules and their audit live: ``ops/migrations/033``, or memory without a database (tests, tooling)."""

from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any

from app.reading_schedule_rules import time_text

COLUMNS = "symbol, scope, enabled, daily_time, updated_by, updated_at, last_slot, last_result, last_detail"

_memory: dict[tuple[str, str], dict[str, Any]] = {}
_audit_memory: list[dict[str, Any]] = []


def value(row: Any) -> dict[str, Any] | None:
    """The part of a schedule an operator sets, as the audit keeps it; None when there was no schedule."""
    return {"enabled": bool(row["enabled"]), "daily_time": time_text(row["daily_time"])} if row else None


async def for_symbol(pool, symbol: str) -> dict[str, dict[str, Any]]:
    if not pool:
        return {scope: dict(row) for (row_symbol, scope), row in _memory.items() if row_symbol == symbol}
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"SELECT {COLUMNS} FROM horizon_reading_schedules WHERE symbol = $1", symbol)
    return {row["scope"]: dict(row) for row in rows}


async def enabled(pool) -> list[dict[str, Any]]:
    if not pool:
        return [dict(row) for row in _memory.values() if row["enabled"]]
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"SELECT {COLUMNS} FROM horizon_reading_schedules WHERE enabled ORDER BY symbol, scope")
    return [dict(row) for row in rows]


async def save(pool, symbol: str, scope: str, is_enabled: bool, daily_time: time, changed_by: str,
               now: datetime) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Set one schedule and keep an audit row with the value it replaced: (the schedule, the previous value)."""
    if not pool:
        before = _memory.get((symbol, scope))
        previous = value(before)
        row = {"last_slot": None, "last_result": None, "last_detail": None, **(before or {}), "symbol": symbol, "scope": scope,
               "enabled": is_enabled, "daily_time": daily_time, "updated_by": changed_by, "updated_at": now}
        _memory[(symbol, scope)] = row
        _audit_memory.insert(0, {"symbol": symbol, "scope": scope, "changed_by": changed_by, "changed_at": now,
                                 "previous": previous, "next": value(row)})
        return dict(row), previous
    async with pool.acquire() as conn:
        async with conn.transaction():
            before = await conn.fetchrow(
                "SELECT enabled, daily_time FROM horizon_reading_schedules WHERE symbol = $1 AND scope = $2 FOR UPDATE", symbol, scope)
            row = await conn.fetchrow(
                "INSERT INTO horizon_reading_schedules (symbol, scope, enabled, daily_time, updated_by, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (symbol, scope) DO UPDATE SET enabled = EXCLUDED.enabled, "
                f"daily_time = EXCLUDED.daily_time, updated_by = EXCLUDED.updated_by, updated_at = EXCLUDED.updated_at RETURNING {COLUMNS}",
                symbol, scope, is_enabled, daily_time, changed_by, now)
            previous = value(before)
            await conn.execute(
                "INSERT INTO horizon_reading_schedule_audit (symbol, scope, changed_by, changed_at, previous, next) "
                "VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)",
                symbol, scope, changed_by, now, json.dumps(previous) if previous else None, json.dumps(value(row)))
    return dict(row), previous


async def claim(pool, symbol: str, scope: str, slot: datetime, armed_at: datetime, result: str, detail: str) -> bool:
    """Record a slot as handled, only while the schedule is still enabled and unchanged and the slot is new to it."""
    if not pool:
        row = _memory.get((symbol, scope))
        if not row or not row["enabled"] or row["updated_at"] != armed_at or (row["last_slot"] and row["last_slot"] >= slot):
            return False
        row.update(last_slot=slot, last_result=result, last_detail=detail)
        return True
    async with pool.acquire() as conn:
        claimed = await conn.fetchval(
            "UPDATE horizon_reading_schedules SET last_slot = $3, last_result = $4, last_detail = $5 "
            "WHERE symbol = $1 AND scope = $2 AND enabled AND updated_at = $6 AND (last_slot IS NULL OR last_slot < $3) RETURNING 1",
            symbol, scope, slot, result, detail, armed_at)
    return bool(claimed)


async def finish(pool, symbol: str, scope: str, slot: datetime, result: str, detail: str) -> None:
    """What happened to a claimed slot: started, or skipped with the reason."""
    if not pool:
        row = _memory.get((symbol, scope))
        if row and row["last_slot"] == slot:
            row.update(last_result=result, last_detail=detail)
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE horizon_reading_schedules SET last_result = $4, last_detail = $5 WHERE symbol = $1 AND scope = $2 AND last_slot = $3",
            symbol, scope, slot, result, detail)


async def changes(pool, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    if not pool:
        return [dict(change) for change in _audit_memory if change["symbol"] == symbol][:limit]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT scope, changed_by, changed_at, previous, next FROM horizon_reading_schedule_audit "
            "WHERE symbol = $1 ORDER BY changed_at DESC LIMIT $2", symbol, limit)
    return [dict(row) for row in rows]
