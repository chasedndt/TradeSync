"""Persistent entry pause and kill switch, with operator-named audit rows.

Both change only under the advisory lock entry admission takes
(``ENTRY_LOCK_KEY``, the same literal ``managed_paper.py`` uses), so an entry
racing a kill or a pause either committed before it or sees it. Nothing here
switches a pause off on its own; ``pause_automatically`` only switches it on.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.paper_json import decode

ENTRY_LOCK_KEY = 230914
SYSTEM_OPERATOR = "paper-risk-engine"


async def take_entry_lock(conn) -> None:
    await conn.execute("SELECT pg_advisory_xact_lock($1)", ENTRY_LOCK_KEY)


async def pause_state(conn, *, lock: bool = False):
    return await conn.fetchrow(
        "SELECT entries_paused, reason, updated_at FROM managed_paper_control WHERE singleton" + (" FOR UPDATE" if lock else "")
    )


async def set_pause(conn, *, paused: bool, operator: str, reason: str):
    row = await conn.fetchrow(
        "UPDATE managed_paper_control SET entries_paused = $1, reason = $2, updated_at = clock_timestamp() "
        "WHERE singleton RETURNING entries_paused, reason, updated_at",
        paused, reason,
    )
    if row is not None:
        await conn.execute(
            "INSERT INTO managed_paper_control_events (id, entries_paused, reason, operator) VALUES ($1, $2, $3, $4)",
            uuid.uuid4(), paused, reason, operator,
        )
    return row


async def pause_automatically(conn, reason: str) -> bool:
    """Switch the pause on for a breach or a mismatch. The caller holds the entry lock."""
    current = await pause_state(conn, lock=True)
    if current is None or current["entries_paused"] is not False:
        return False
    await set_pause(conn, paused=True, operator=SYSTEM_OPERATOR, reason=reason[:240])
    return True


async def kill_state(conn, *, lock: bool = False):
    return await conn.fetchrow(
        "SELECT active, operator, reason, changed_at FROM paper_kill_switch WHERE singleton" + (" FOR UPDATE" if lock else "")
    )


async def set_kill(conn, *, active: bool, operator: str, reason: str):
    return await conn.fetchrow(
        "UPDATE paper_kill_switch SET active = $1, operator = $2, reason = $3, changed_at = clock_timestamp() "
        "WHERE singleton RETURNING active, operator, reason, changed_at",
        active, operator, reason,
    )


async def kill_event(conn, *, action: str, operator: str, reason: str, position_id: Any = None, detail: dict | None = None) -> None:
    await conn.execute(
        "INSERT INTO paper_kill_switch_events (id, action, operator, reason, position_id, detail) VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        uuid.uuid4(), action, operator, reason, position_id, json.dumps(detail or {}, default=str),
    )


async def recent_control_events(conn, limit: int = 20) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT created_at, entries_paused, reason, operator FROM managed_paper_control_events ORDER BY created_at DESC LIMIT $1", limit
    )
    return [dict(r) for r in rows]


async def recent_kill_events(conn, limit: int = 20) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT created_at, action, operator, reason, position_id, detail FROM paper_kill_switch_events ORDER BY created_at DESC LIMIT $1", limit
    )
    return [{**dict(r), "detail": decode(r["detail"])} for r in rows]
