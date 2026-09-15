"""Reads and writes for restart reconciliation: runs, event-derived states and observation gaps."""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.paper_json import decode
from tradesync_core.paper_reconciliation import event_state, latest_state

# The latest few events of every position by write time; the lifecycle-latest
# among them is picked in Python by ``latest_state``.
LATEST_STATES_SQL = """
SELECT p.id, e.kind, e.payload
FROM managed_paper_positions p
CROSS JOIN LATERAL (
  SELECT kind, payload FROM managed_paper_events
  WHERE position_id = p.id AND (kind = 'opened' OR payload ? 'position')
  ORDER BY created_at DESC LIMIT 5
) e
"""

# Consecutive events of positions open now or updated within a swing position's
# longest hold, where the pause between them passed the threshold.
GAP_PAIRS_SQL = """
SELECT position_id, symbol, prev_at, created_at,
       extract(epoch FROM prev_at)::float8 AS started_s, extract(epoch FROM created_at)::float8 AS ended_s
FROM (
  SELECT e.position_id, p.symbol, e.created_at,
         lag(e.created_at) OVER (PARTITION BY e.position_id ORDER BY e.created_at) AS prev_at
  FROM managed_paper_events e JOIN managed_paper_positions p ON p.id = e.position_id
  WHERE p.position_state->>'status' = 'open' OR p.updated_at > now() - interval '8 days'
) t
WHERE prev_at IS NOT NULL AND created_at - prev_at > make_interval(secs => $1)
"""

LAST_SEEN_SQL = """
SELECT p.id, p.symbol, max(e.created_at) AS last_at, extract(epoch FROM max(e.created_at))::float8 AS last_s
FROM managed_paper_positions p JOIN managed_paper_events e ON e.position_id = p.id
WHERE p.position_state->>'status' = 'open'
GROUP BY p.id, p.symbol
"""


async def positions(conn) -> list[dict[str, Any]]:
    rows = await conn.fetch("SELECT id, symbol, position_state FROM managed_paper_positions ORDER BY created_at")
    return [{"id": r["id"], "symbol": r["symbol"], "position_state": decode(r["position_state"])} for r in rows]


async def latest_states(conn) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in await conn.fetch(LATEST_STATES_SQL):
        state = event_state(row["kind"], decode(row["payload"]))
        if state is not None:
            grouped.setdefault(str(row["id"]), []).append(state)
    return {pid: latest_state(states) for pid, states in grouped.items()}


# The state each position's closed event recorded: what its realised entry is booked from.
CLOSE_STATES_SQL = """
SELECT DISTINCT ON (position_id) position_id, payload->'position' AS position
FROM managed_paper_events WHERE kind = 'closed'
ORDER BY position_id, created_at
"""


async def close_states(conn) -> dict[str, dict[str, Any]]:
    return {str(r["position_id"]): decode(r["position"]) for r in await conn.fetch(CLOSE_STATES_SQL)}


async def opened_ids(conn) -> set[str]:
    return {str(r["position_id"]) for r in await conn.fetch("SELECT DISTINCT position_id FROM managed_paper_events WHERE kind = 'opened'")}


async def gap_pairs(conn, threshold_s: float) -> list[dict[str, Any]]:
    return [dict(r) for r in await conn.fetch(GAP_PAIRS_SQL, threshold_s)]


async def open_last_seen(conn) -> list[dict[str, Any]]:
    return [dict(r) for r in await conn.fetch(LAST_SEEN_SQL)]


# A gap is keyed by its exact start; an ongoing gap gains its end once, and an end is never removed.
UPSERT_GAP_SQL = (
    "INSERT INTO paper_observation_gaps (id, position_id, symbol, started_at, ended_at) VALUES ($1, $2, $3, $4, $5) "
    "ON CONFLICT (position_id, started_at) DO UPDATE SET ended_at = EXCLUDED.ended_at "
    "WHERE paper_observation_gaps.ended_at IS NULL AND EXCLUDED.ended_at IS NOT NULL"
)


async def upsert_gaps(conn, gaps: list[dict[str, Any]]) -> None:
    for gap in gaps:
        await conn.execute(UPSERT_GAP_SQL, uuid.uuid4(), gap["position_id"], gap["symbol"], gap["started_at"], gap["ended_at"])


async def recent_gaps(conn, limit: int = 50) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT position_id, symbol, started_at, ended_at, detected_at FROM paper_observation_gaps "
        "ORDER BY (ended_at IS NULL) DESC, started_at DESC LIMIT $1", limit
    )
    return [dict(r) for r in rows]


async def insert_run(conn, run: dict[str, Any]) -> dict[str, Any]:
    row = await conn.fetchrow(
        "INSERT INTO paper_reconciliation_runs (id, trigger, started_at, status, positions_checked, open_positions, "
        "mismatches, gaps, account, error) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9::jsonb, $10) RETURNING *",
        uuid.uuid4(), run["trigger"], run["started_at"], run["status"], run["positions_checked"], run["open_positions"],
        json.dumps(run["mismatches"], default=str), json.dumps(run["gaps"], default=str),
        json.dumps(run["account"], default=str), run.get("error"),
    )
    return run_row(row)


def run_row(row: Any) -> dict[str, Any]:
    return {**dict(row), **{key: decode(row[key]) for key in ("mismatches", "gaps", "account")}}


async def latest_run(conn) -> dict[str, Any] | None:
    row = await conn.fetchrow("SELECT * FROM paper_reconciliation_runs ORDER BY finished_at DESC LIMIT 1")
    return None if row is None else run_row(row)


async def prune_runs(conn, keep_days: int = 14) -> None:
    await conn.execute("DELETE FROM paper_reconciliation_runs WHERE finished_at < now() - make_interval(days => $1)", keep_days)
