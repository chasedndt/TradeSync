"""Database access for the outcome job: which rows to review, how to write results.

Kept apart from the measurement logic so the query that decides "what is still
unfinished" can be read on its own. That query is where one of the job's worst
defects lived: counting only ``measured`` as finished kept every window with a
gap in the queue forever, and taking the newest forty meant the same forty were
re-reviewed every pass while the real backlog was never reached.
"""

from __future__ import annotations

from typing import Any

from tradesync_core.outcomes import DEFAULT_HORIZONS_MINUTES

# Both are final. A row is revisited only while a horizon is missing or pending.
FINAL_STATUSES = ("measured", "insufficient_candles")


async def pending_opportunities(conn, batch: int) -> list[dict[str, Any]]:
    """Opportunities with a horizon still open or never written, oldest first.

    Oldest first so a backlog drains instead of ageing; new rows are reached
    within a few passes at the default batch size.
    """
    rows = await conn.fetch(
        """
        SELECT o.id, o.symbol, o.dir, o.snapshot_ts
        FROM opportunities o
        WHERE o.dir IN ('LONG', 'SHORT')
          AND (
            SELECT count(*) FROM opportunity_outcomes x
            WHERE x.opportunity_id = o.id
              AND x.status = ANY($3::text[])
          ) < $1
        ORDER BY o.snapshot_ts ASC
        LIMIT $2
        """,
        len(DEFAULT_HORIZONS_MINUTES),
        batch,
        list(FINAL_STATUSES),
    )
    return [dict(r) for r in rows]


async def store_outcome(conn, outcome, symbol: str, direction: str) -> None:
    """Write every horizon, replacing any earlier verdict for the same one."""
    for horizon in outcome.horizons:
        await conn.execute(
            """
            INSERT INTO opportunity_outcomes (
                opportunity_id, symbol, direction, horizon_minutes, status,
                entry_price, exit_price, forward_return_pct, signed_return_pct,
                max_favourable_pct, max_adverse_pct, candles_used, reason,
                opened_at, measured_at
            ) VALUES (
                $1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                to_timestamp($14), now()
            )
            ON CONFLICT (opportunity_id, horizon_minutes) DO UPDATE SET
                status = EXCLUDED.status,
                entry_price = EXCLUDED.entry_price,
                exit_price = EXCLUDED.exit_price,
                forward_return_pct = EXCLUDED.forward_return_pct,
                signed_return_pct = EXCLUDED.signed_return_pct,
                max_favourable_pct = EXCLUDED.max_favourable_pct,
                max_adverse_pct = EXCLUDED.max_adverse_pct,
                candles_used = EXCLUDED.candles_used,
                reason = EXCLUDED.reason,
                measured_at = now()
            """,
            str(outcome.opportunity_id),
            symbol,
            direction,
            horizon.horizon_minutes,
            horizon.status,
            horizon.entry_price,
            horizon.exit_price,
            horizon.forward_return_pct,
            horizon.signed_return_pct,
            horizon.max_favourable_pct,
            horizon.max_adverse_pct,
            horizon.candles_used,
            horizon.reason,
            outcome.opened_at_s,
        )
