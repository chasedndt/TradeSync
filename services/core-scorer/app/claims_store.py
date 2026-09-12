"""Database access for the claims job: what to extract, what to measure, how to write.

Kept apart from the job so the two queries that decide "what is still
unprocessed" can be read on their own. Both are oldest-first and bounded, so a
backlog drains instead of ageing and a restart loses nothing.
"""

from __future__ import annotations

import json
from typing import Any

from tradesync_core.claim_extraction import Claim
from tradesync_core.outcomes import DEFAULT_HORIZONS_MINUTES

EXTRACTABLE_SOURCES = ("tradingview", "discord", "chaseos")
FINAL_STATUSES = ("measured", "insufficient_candles")


async def unextracted_rows(conn, batch: int) -> list[dict[str, Any]]:
    """Accepted quarantine rows from extractable sources with no extraction record."""
    rows = await conn.fetch(
        """
        SELECT q.id, q.source, q.payload, q.observed_at, q.received_at
        FROM quarantine_intake q
        LEFT JOIN quarantine_extractions x ON x.quarantine_id = q.id
        WHERE q.accepted AND q.source = ANY($1::text[]) AND x.quarantine_id IS NULL
        ORDER BY q.received_at ASC
        LIMIT $2
        """,
        list(EXTRACTABLE_SOURCES),
        batch,
    )
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d["payload"]) if isinstance(d["payload"], str) else d["payload"]
        out.append(d)
    return out


async def record_extraction(conn, quarantine_id: str, extractor: str, claims: list[Claim], reason: str) -> None:
    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO quarantine_extractions (quarantine_id, extractor, claims, reason)
            VALUES ($1::uuid, $2, $3, $4) ON CONFLICT (quarantine_id) DO NOTHING
            """,
            quarantine_id, extractor, len(claims), reason,
        )
        for c in claims:
            await conn.execute(
                """
                INSERT INTO evidence_claims
                    (quarantine_id, source, source_id, symbol, direction, horizon_minutes, claimed_at, extractor, excerpt)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, to_timestamp($7::double precision / 1000.0), $8, $9)
                ON CONFLICT (quarantine_id, symbol) DO NOTHING
                """,
                quarantine_id, c.source, c.source_id, c.symbol, c.direction, c.horizon_minutes,
                c.claimed_at_ms, c.extractor, c.excerpt,
            )


async def pending_claims(conn, batch: int) -> list[dict[str, Any]]:
    """Claims with a horizon still open or never written, oldest first."""
    rows = await conn.fetch(
        """
        SELECT c.id, c.symbol, c.direction, c.claimed_at
        FROM evidence_claims c
        WHERE (
            SELECT count(*) FROM evidence_claim_outcomes o
            WHERE o.claim_id = c.id AND o.status = ANY($3::text[])
        ) < $1
        ORDER BY c.claimed_at ASC
        LIMIT $2
        """,
        len(DEFAULT_HORIZONS_MINUTES), batch, list(FINAL_STATUSES),
    )
    return [dict(r) for r in rows]


async def store_claim_outcome(conn, outcome, symbol: str, direction: str) -> None:
    """Write every horizon, replacing any earlier verdict for the same one."""
    for h in outcome.horizons:
        await conn.execute(
            """
            INSERT INTO evidence_claim_outcomes (
                claim_id, symbol, direction, horizon_minutes, status, entry_price, exit_price,
                forward_return_pct, signed_return_pct, candles_used, reason, claimed_at, measured_at
            ) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, to_timestamp($12), now())
            ON CONFLICT (claim_id, horizon_minutes) DO UPDATE SET
                status = EXCLUDED.status, entry_price = EXCLUDED.entry_price, exit_price = EXCLUDED.exit_price,
                forward_return_pct = EXCLUDED.forward_return_pct, signed_return_pct = EXCLUDED.signed_return_pct,
                candles_used = EXCLUDED.candles_used, reason = EXCLUDED.reason, measured_at = now()
            """,
            outcome.opportunity_id, symbol, direction, h.horizon_minutes, h.status, h.entry_price, h.exit_price,
            h.forward_return_pct, h.signed_return_pct, h.candles_used, h.reason, outcome.opened_at_s,
        )
