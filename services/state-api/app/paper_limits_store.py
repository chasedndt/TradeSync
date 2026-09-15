"""Operator-editable paper limits and their audit rows.

``update`` is the only function that writes a limit, and only the operator's
audited route calls it. No loop, hook or evaluation changes a limit.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.paper_json import decode
from tradesync_core.paper_limits import LIMIT_KEYS, check_limits

COLUMNS = ", ".join(LIMIT_KEYS)


async def load(conn, *, lock: bool = False) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        f"SELECT {COLUMNS}, operator, reason, updated_at FROM paper_risk_limits WHERE singleton" + (" FOR UPDATE" if lock else "")
    )
    return None if row is None else dict(row)


async def update(conn, *, changes: dict[str, Any], operator: str, reason: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply an operator's change; the caller holds the entry lock. Returns (previous, updated row)."""
    unknown = set(changes) - set(LIMIT_KEYS)
    if unknown:
        raise ValueError("Unknown paper limits: " + ", ".join(sorted(unknown)))
    current = await load(conn, lock=True)
    if current is None:
        raise LookupError("Paper limits missing; entries disabled")
    previous = {key: current[key] for key in LIMIT_KEYS}
    merged = check_limits({**previous, **changes})
    if all(merged[key] == previous[key] for key in LIMIT_KEYS):
        raise ValueError("No paper limit value changed")
    assignments = ", ".join(f"{key} = ${i}" for i, key in enumerate(LIMIT_KEYS, start=1))
    n = len(LIMIT_KEYS)
    row = await conn.fetchrow(
        f"UPDATE paper_risk_limits SET {assignments}, operator = ${n + 1}, reason = ${n + 2}, updated_at = clock_timestamp() "
        f"WHERE singleton RETURNING {COLUMNS}, operator, reason, updated_at",
        *[merged[key] for key in LIMIT_KEYS], operator, reason,
    )
    updated = {key: row[key] for key in LIMIT_KEYS}
    await conn.execute(
        "INSERT INTO paper_risk_limit_events (id, operator, reason, previous, updated) VALUES ($1, $2, $3, $4::jsonb, $5::jsonb)",
        uuid.uuid4(), operator, reason, json.dumps(previous), json.dumps(updated),
    )
    return previous, dict(row)


async def recent_events(conn, limit: int = 20) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT created_at, operator, reason, previous, updated FROM paper_risk_limit_events ORDER BY created_at DESC LIMIT $1", limit
    )
    return [{**dict(r), "previous": decode(r["previous"]), "updated": decode(r["updated"])} for r in rows]
