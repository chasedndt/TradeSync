"""Measure what happened after each recorded paper opportunity.

Runs on its own cadence, separate from the producer: measuring is not part of
deciding, and a slow measurement must never delay or influence a verdict.

The job is idempotent. A horizon that is still open is written as ``pending``
and re-measured on a later pass, so restarting mid-run loses nothing.

Candles are fetched for the windows actually pending, not for "the latest N".
See ``outcome_windows`` for why: the latest-N shortcut wrote off every window
older than eight hours as having no candles, and then re-reviewed those rows
forever while the real backlog starved.
"""

from __future__ import annotations

import os
import time
from dataclasses import replace
from typing import Any

import httpx

from tradesync_core.outcomes import (
    DEFAULT_HORIZONS_MINUTES,
    HorizonOutcome,
    OutcomeError,
    measure_opportunity,
)

from .outcome_windows import (
    FetchRange,
    chunk_ranges,
    merge_candles,
    required_span_s,
    window_was_requested,
)

MARKET_DATA_URL = os.getenv("MARKET_DATA_URL", "http://market-data:8005")
OUTCOME_INTERVAL_SECONDS = int(os.getenv("OUTCOME_INTERVAL_SECONDS", "300"))
# Oldest-first with a batch this size drains an 800-row backlog in well under
# an hour while still reaching new rows within a few passes.
OUTCOME_BATCH = int(os.getenv("OUTCOME_BATCH", "120"))
# The candle interval used to measure. One minute keeps the shortest horizon
# meaningful; a coarser interval would round a 15 minute window badly.
OUTCOME_CANDLE_INTERVAL = os.getenv("OUTCOME_CANDLE_INTERVAL", "1m")
# Hyperliquid stops serving 1-minute candles after a few days but keeps 5-minute
# ones. A window older than that is measured at 5m if its horizon is long enough
# for the coarser entry not to matter; the row says so.
COARSE_CANDLE_INTERVAL = os.getenv("OUTCOME_COARSE_CANDLE_INTERVAL", "5m")
INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
CANDLE_SECONDS = INTERVAL_SECONDS[OUTCOME_CANDLE_INTERVAL]
COARSE_SECONDS = INTERVAL_SECONDS[COARSE_CANDLE_INTERVAL]
# Entry is the first candle at or after the signal, so a 5m candle can place it
# up to five minutes late. On a 60m window that is at most 8% of the horizon;
# on a 15m window it is a third, which is not the same measurement.
MIN_HORIZON_FOR_COARSE = 60
LONGEST_HORIZON = max(DEFAULT_HORIZONS_MINUTES)

NOT_FETCHED = "candles were not fetched for this window on this pass"
NO_FINE_HISTORY = (
    f"venue no longer serves {OUTCOME_CANDLE_INTERVAL} candles for this window "
    f"and {COARSE_CANDLE_INTERVAL} is too coarse for a {{horizon}}m horizon"
)
MEASURED_COARSE = (
    f"measured at {COARSE_CANDLE_INTERVAL} candles: venue no longer serves "
    f"{OUTCOME_CANDLE_INTERVAL} history for this window"
)


async def _fetch_interval(
    symbol: str, span: tuple[int, int], interval: str, client: httpx.AsyncClient
) -> tuple[list[dict[str, Any]], list[FetchRange]]:
    """One interval's candles across the span, chunked to the venue cap.

    A chunk that fails is left out of the returned ranges, so the caller can
    tell an unrequested window from an empty one.
    """
    received: list[FetchRange] = []
    batches: list[list[dict[str, Any]]] = []
    for chunk in chunk_ranges(span[0], span[1], INTERVAL_SECONDS[interval]):
        try:
            response = await client.get(
                f"{MARKET_DATA_URL}/candles/hyperliquid/{symbol}",
                params={"interval": interval, "start_ms": chunk.start_ms, "end_ms": chunk.end_ms},
                timeout=20.0,
            )
            response.raise_for_status()
            batches.append(response.json().get("candles", []))
            received.append(chunk)
        except (httpx.HTTPError, ValueError) as exc:
            # Reported per window below, as "not fetched", never as "empty".
            print(f"[Outcomes] {interval} candles unavailable for {symbol} {chunk}: {exc}")
    return merge_candles(batches), received


async def fetch_candles_for(
    symbol: str, opened_at_s: list[int], client: httpx.AsyncClient
) -> tuple[list[dict[str, Any]], list[FetchRange], str]:
    """Candles for the batch's windows, at 1m where the venue still has it.

    Returns the merged candles, the ranges actually received, and the interval
    they came at. The coarse interval is used only when the fine one came back
    empty for a span that was successfully requested — an empty answer, not a
    failed request.
    """
    span = required_span_s(opened_at_s, LONGEST_HORIZON, CANDLE_SECONDS)
    if span is None:
        return [], [], OUTCOME_CANDLE_INTERVAL
    candles, received = await _fetch_interval(symbol, span, OUTCOME_CANDLE_INTERVAL, client)
    if candles or not received:
        return candles, received, OUTCOME_CANDLE_INTERVAL
    coarse, coarse_received = await _fetch_interval(symbol, span, COARSE_CANDLE_INTERVAL, client)
    return coarse, coarse_received, COARSE_CANDLE_INTERVAL


async def pending_opportunities(conn, batch: int) -> list[dict[str, Any]]:
    """Opportunities with a horizon still open or never written.

    ``measured`` and ``insufficient_candles`` are both final. Counting only
    ``measured`` as final, as this once did, kept every window with a gap in
    the queue forever and the newest forty of them crowded out everything
    else. Oldest first, so a backlog drains instead of ageing.
    """
    rows = await conn.fetch(
        """
        SELECT o.id, o.symbol, o.dir, o.snapshot_ts
        FROM opportunities o
        WHERE o.dir IN ('LONG', 'SHORT')
          AND (
            SELECT count(*) FROM opportunity_outcomes x
            WHERE x.opportunity_id = o.id
              AND x.status IN ('measured', 'insufficient_candles')
          ) < $1
        ORDER BY o.snapshot_ts ASC
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


def guard_unrequested(
    horizons: list[HorizonOutcome], fetched: list[FetchRange], opened_at_s: int
) -> list[HorizonOutcome]:
    """Turn "no candles" into "not fetched" wherever the window was not asked for.

    ``insufficient_candles`` is final. It may only be written when the venue
    was asked for the whole window and answered; otherwise the row stays
    pending and is retried, which is the difference between a gap in the
    venue's history and a gap in our own request.
    """
    out = []
    for horizon in horizons:
        if horizon.status == "insufficient_candles" and not window_was_requested(
            fetched, opened_at_s, horizon.horizon_minutes
        ):
            horizon = replace(horizon, status="pending", reason=NOT_FETCHED, candles_used=0)
        out.append(horizon)
    return out


def guard_coarse(horizons: list[HorizonOutcome], interval: str) -> list[HorizonOutcome]:
    """Say when a measurement came from coarse candles, and refuse it when it matters.

    A horizon measured at the coarse interval carries that fact in its reason,
    so nobody later averages a 5m-entry result with a 1m-entry one without
    knowing. A horizon shorter than ``MIN_HORIZON_FOR_COARSE`` is not measured
    coarsely at all: the entry could be a third of the window late.
    """
    if interval == OUTCOME_CANDLE_INTERVAL:
        return horizons
    out = []
    for horizon in horizons:
        if horizon.horizon_minutes < MIN_HORIZON_FOR_COARSE and horizon.status != "pending":
            horizon = HorizonOutcome(
                horizon_minutes=horizon.horizon_minutes,
                status="insufficient_candles",
                reason=NO_FINE_HISTORY.format(horizon=horizon.horizon_minutes),
            )
        elif horizon.status == "measured":
            horizon = replace(horizon, reason=MEASURED_COARSE)
        out.append(horizon)
    return out


async def run_outcome_pass(conn) -> dict[str, int]:
    """Measure one batch. Returns counts for logging."""
    pending = await pending_opportunities(conn, OUTCOME_BATCH)
    if not pending:
        return {"opportunities": 0, "measured": 0}

    now_s = int(time.time())
    by_symbol: dict[str, list[int]] = {}
    for row in pending:
        by_symbol.setdefault(row["symbol"], []).append(int(row["snapshot_ts"].timestamp()))

    candles: dict[str, list[dict[str, Any]]] = {}
    fetched: dict[str, list[FetchRange]] = {}
    interval: dict[str, str] = {}
    async with httpx.AsyncClient() as client:
        for symbol, opened in by_symbol.items():
            candles[symbol], fetched[symbol], interval[symbol] = await fetch_candles_for(
                symbol, opened, client
            )

    measured = 0
    for row in pending:
        opened_at_s = int(row["snapshot_ts"].timestamp())
        try:
            outcome = measure_opportunity(
                opportunity_id=str(row["id"]),
                symbol=row["symbol"],
                direction=row["dir"],
                opened_at_s=opened_at_s,
                candles=candles.get(row["symbol"], []),
                now_s=now_s,
            )
        except OutcomeError as exc:
            print(f"[Outcomes] skipping {row['id']}: {exc}")
            continue
        horizons = guard_unrequested(outcome.horizons, fetched.get(row["symbol"], []), opened_at_s)
        horizons = guard_coarse(horizons, interval.get(row["symbol"], OUTCOME_CANDLE_INTERVAL))
        outcome = replace(outcome, horizons=horizons)
        await store_outcome(conn, outcome, row["symbol"], row["dir"])
        measured += sum(1 for h in outcome.horizons if h.status == "measured")

    return {"opportunities": len(pending), "measured": measured}
