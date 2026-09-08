"""Roll up old refusals, then remove them.

Runs on its own cadence beside the outcome job. Retention is not part of
deciding and must never delay a verdict.

The rollup and the deletion of the rows it summarises happen in **one
transaction**. There is no state in which rows are gone but unsummarised: a
committed delete without its rollup would quietly improve every admission rate
computed afterwards, and refusals are the denominator for all of them.

Should a pass ever re-read rows it already summarised, the merge absorbs them
correctly — it is keyed on (day, symbol, primary reason) and adds rather than
replaces — but the transaction means it should not have to.

Only refusals are touched. Admitted signals are the evidence trail behind
recorded opportunities and their outcomes; nothing here deletes one.
"""

from __future__ import annotations

import json
import os
from typing import Any

from tradesync_core.retention import (
    DEFAULT_REFUSAL_RETENTION_DAYS,
    merge_rollup,
    retention_cutoff,
    rollup_refusals,
)

RETENTION_INTERVAL_SECONDS = int(os.getenv("RETENTION_INTERVAL_SECONDS", "3600"))
REFUSAL_RETENTION_DAYS = int(
    os.getenv("REFUSAL_RETENTION_DAYS", str(DEFAULT_REFUSAL_RETENTION_DAYS))
)
# Bounded so one pass cannot hold a long transaction over the signals table.
# A backlog drains across passes rather than in one sweep.
RETENTION_BATCH = int(os.getenv("RETENTION_BATCH", "2000"))

REFUSAL_KIND = "regime_paper_refusal"


async def expired_refusals(conn, cutoff, batch: int) -> list[dict[str, Any]]:
    """Refusal rows older than the cutoff, oldest first.

    Oldest first so a backlog drains in order and a partial pass leaves a
    contiguous recent window rather than holes in the middle of it.
    """
    rows = await conn.fetch(
        """
        SELECT id, created_at, symbol, features
        FROM signals
        WHERE kind = $1
          AND created_at < $2
        ORDER BY created_at
        LIMIT $3
        """,
        REFUSAL_KIND,
        cutoff,
        batch,
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        features = row["features"]
        if isinstance(features, str):
            try:
                features = json.loads(features)
            except json.JSONDecodeError:
                features = {}
        out.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "symbol": row["symbol"],
                "features": features or {},
            }
        )
    return out


async def write_rollup(conn, entries: list[dict[str, Any]]) -> int:
    """Merge each entry into ``signal_refusal_daily``.

    Read-modify-write rather than a bare upsert, because combining two batches
    means recombining weighted means, which SQL's ``EXCLUDED`` cannot express
    without the per-measure counts on both sides.
    """
    written = 0
    for entry in entries:
        existing = await conn.fetchrow(
            """
            SELECT refusals, scored_rows, covered_rows, mean_score, mean_coverage,
                   min_coverage, max_coverage, reason_codes
            FROM signal_refusal_daily
            WHERE day = $1 AND symbol = $2 AND reason = $3
            """,
            entry["day"],
            entry["symbol"],
            entry["reason"],
        )
        previous = None
        if existing is not None:
            previous = dict(existing)
            codes = previous.get("reason_codes")
            if isinstance(codes, str):
                previous["reason_codes"] = json.loads(codes)

        merged = merge_rollup(previous, entry)
        await conn.execute(
            """
            INSERT INTO signal_refusal_daily (
                day, symbol, reason, refusals, reason_codes,
                scored_rows, covered_rows,
                mean_score, mean_coverage, min_coverage, max_coverage
            )
            VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (day, symbol, reason) DO UPDATE SET
                refusals = EXCLUDED.refusals,
                reason_codes = EXCLUDED.reason_codes,
                scored_rows = EXCLUDED.scored_rows,
                covered_rows = EXCLUDED.covered_rows,
                mean_score = EXCLUDED.mean_score,
                mean_coverage = EXCLUDED.mean_coverage,
                min_coverage = EXCLUDED.min_coverage,
                max_coverage = EXCLUDED.max_coverage,
                last_rolled_at = now()
            """,
            merged["day"],
            merged["symbol"],
            merged["reason"],
            merged["refusals"],
            json.dumps(merged.get("reason_codes") or {}),
            merged.get("scored_rows") or 0,
            merged.get("covered_rows") or 0,
            merged.get("mean_score"),
            merged.get("mean_coverage"),
            merged.get("min_coverage"),
            merged.get("max_coverage"),
        )
        written += 1
    return written


async def run_retention_pass(conn) -> dict[str, int]:
    """Roll up and remove one batch of expired refusals.

    Returns counts rather than logging them itself, so the caller decides what
    is worth saying. A pass that found nothing returns zeros and is silent.
    """
    cutoff = retention_cutoff(REFUSAL_RETENTION_DAYS)
    rows = await expired_refusals(conn, cutoff, RETENTION_BATCH)
    if not rows:
        return {"examined": 0, "rolled": 0, "deleted": 0}

    entries = rollup_refusals(rows)

    # One transaction: the aggregate and the deletion of the rows it summarises
    # either both land or neither does. A committed delete with no rollup would
    # quietly improve every admission rate computed afterwards.
    async with conn.transaction():
        rolled = await write_rollup(conn, entries)
        await conn.execute(
            "DELETE FROM signals WHERE id = ANY($1::uuid[])",
            [row["id"] for row in rows],
        )

    return {"examined": len(rows), "rolled": rolled, "deleted": len(rows)}
