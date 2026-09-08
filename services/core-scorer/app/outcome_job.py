"""Measure what happened after each recorded paper opportunity.

Runs on its own cadence, separate from the producer: measuring is not part of
deciding, and a slow measurement must never delay or influence a verdict.

The job is idempotent. A horizon that is still open is written as ``pending``
and re-measured on a later pass, so restarting mid-run loses nothing.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from tradesync_core.outcomes import (
    DEFAULT_HORIZONS_MINUTES,
    OutcomeError,
    measure_opportunity,
)

MARKET_DATA_URL = os.getenv("MARKET_DATA_URL", "http://market-data:8005")
OUTCOME_INTERVAL_SECONDS = int(os.getenv("OUTCOME_INTERVAL_SECONDS", "300"))
OUTCOME_BATCH = int(os.getenv("OUTCOME_BATCH", "40"))
# The candle interval used to measure. One minute keeps the shortest horizon
# meaningful; a coarser interval would round a 15 minute window badly.
OUTCOME_CANDLE_INTERVAL = os.getenv("OUTCOME_CANDLE_INTERVAL", "1m")
LONGEST_HORIZON = max(DEFAULT_HORIZONS_MINUTES)


async def fetch_candles(symbol: str, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Fetch enough candles to cover the longest horizon plus a margin."""
    # Two horizons of headroom so an opportunity opened just before the window
    # edge still has its full measurement period available.
    limit = min(LONGEST_HORIZON * 2, 1000)
    response = await client.get(
        f"{MARKET_DATA_URL}/candles/hyperliquid/{symbol}",
        params={"interval": OUTCOME_CANDLE_INTERVAL, "limit": limit},
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json().get("candles", [])


async def pending_opportunities(conn, batch: int) -> list[dict[str, Any]]:
    """Opportunities with at least one horizon not yet measured.

    A row is revisited while any horizon is missing or still pending, so a
    15-minute result does not stop the 4-hour one from being recorded later.
    """
    rows = await conn.fetch(
        """
        SELECT o.id, o.symbol, o.dir, o.snapshot_ts
        FROM opportunities o
        WHERE o.dir IN ('LONG', 'SHORT')
          AND (
            SELECT count(*) FROM opportunity_outcomes x
            WHERE x.opportunity_id = o.id AND x.status = 'measured'
          ) < $1
        ORDER BY o.snapshot_ts DESC
        LIMIT $2
        """,
        len(DEFAULT_HORIZONS_MINUTES),
        batch,
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


async def run_outcome_pass(conn) -> dict[str, int]:
    """Measure one batch. Returns counts for logging."""
    pending = await pending_opportunities(conn, OUTCOME_BATCH)
    if not pending:
        return {"opportunities": 0, "measured": 0}

    now_s = int(time.time())
    symbols = sorted({row["symbol"] for row in pending})
    candles_by_symbol: dict[str, list[dict[str, Any]]] = {}
    async with httpx.AsyncClient() as client:
        for symbol in symbols:
            try:
                candles_by_symbol[symbol] = await fetch_candles(symbol, client)
            except (httpx.HTTPError, ValueError) as exc:
                # A missing series is reported per opportunity rather than
                # failing the whole pass.
                print(f"[Outcomes] candles unavailable for {symbol}: {exc}")
                candles_by_symbol[symbol] = []

    measured = 0
    for row in pending:
        try:
            outcome = measure_opportunity(
                opportunity_id=str(row["id"]),
                symbol=row["symbol"],
                direction=row["dir"],
                opened_at_s=int(row["snapshot_ts"].timestamp()),
                candles=candles_by_symbol.get(row["symbol"], []),
                now_s=now_s,
            )
        except OutcomeError as exc:
            print(f"[Outcomes] skipping {row['id']}: {exc}")
            continue
        await store_outcome(conn, outcome, row["symbol"], row["dir"])
        measured += sum(1 for h in outcome.horizons if h.status == "measured")

    return {"opportunities": len(pending), "measured": measured}
