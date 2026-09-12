"""Record the entry-time regime for each opportunity the outcome job reviews.

The regime is computed by ``tradesync_core.entry_regime`` from candles that
had fully closed before the opportunity fired, so it is something the operator
could have known at the time. It is written once per opportunity; a row that
already has one is not recomputed, so a later fetch at a coarser interval
cannot silently relabel history.

Backfill is a separate query: opportunities that already have final outcomes
but no regime are labelled without re-measuring their outcomes.
"""

from __future__ import annotations

from typing import Any

from tradesync_core.entry_regime import DEFAULT_LOOKBACK_MINUTES, classify_entry_regime

LOOKBACK_MINUTES = DEFAULT_LOOKBACK_MINUTES


def lookback_margin_s(candle_s: int) -> int:
    """How far before the earliest opened_at the fetched span must start."""
    return LOOKBACK_MINUTES * 60 + candle_s


async def missing_regime_opportunities(conn, batch: int) -> list[dict[str, Any]]:
    """Opportunities with a direction but no entry regime yet, oldest first."""
    rows = await conn.fetch(
        """
        SELECT o.id, o.symbol, o.dir, o.snapshot_ts
        FROM opportunities o
        LEFT JOIN opportunity_entry_regimes r ON r.opportunity_id = o.id
        WHERE o.dir IN ('LONG', 'SHORT') AND r.opportunity_id IS NULL
        ORDER BY o.snapshot_ts ASC
        LIMIT $1
        """,
        batch,
    )
    return [dict(r) for r in rows]


async def store_entry_regime(
    conn,
    opportunity_id: str,
    symbol: str,
    opened_at_s: int,
    candles: list[dict[str, Any]],
    candle_s: int,
    candle_interval: str,
) -> str:
    """Classify and insert; returns the regime. Never overwrites an existing row."""
    result = classify_entry_regime(candles, opened_at_s, candle_s)
    await conn.execute(
        """
        INSERT INTO opportunity_entry_regimes (
            opportunity_id, symbol, regime, trailing_return_pct, lookback_minutes,
            candles_used, candle_interval, window_start_s, window_end_s, reason, schema_version
        ) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        ON CONFLICT (opportunity_id) DO NOTHING
        """,
        opportunity_id,
        symbol,
        result.regime,
        result.trailing_return_pct,
        result.lookback_minutes,
        result.candles_used,
        candle_interval,
        result.window_start_s,
        result.window_end_s,
        result.reason,
        result.to_dict()["schema_version"],
    )
    return result.regime
