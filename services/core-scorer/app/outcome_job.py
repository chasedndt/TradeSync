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
from dataclasses import dataclass, replace
from typing import Any

import httpx

from tradesync_core.outcomes import (
    DEFAULT_HORIZONS_MINUTES,
    HorizonOutcome,
    OutcomeError,
    measure_opportunity,
)

from .outcome_regime import (
    lookback_margin_s,
    missing_regime_opportunities,
    store_entry_regime,
)
from .outcome_store import pending_opportunities, store_outcome
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


# Below this age the venue has been seen to still serve 1m candles (probed
# 2026-09-12: present at 72h, gone at 96h). Older spans also fetch the coarse
# series so a window the fine series no longer covers can fall back per window.
FINE_RETENTION_S = int(os.getenv("OUTCOME_FINE_RETENTION_S", str(60 * 3600)))


@dataclass
class SymbolCandles:
    fine: list[dict[str, Any]]
    fine_ranges: list[FetchRange]
    coarse: list[dict[str, Any]]
    coarse_ranges: list[FetchRange]


async def fetch_candles_for(
    symbol: str, opened_at_s: list[int], client: httpx.AsyncClient, now_s: int
) -> SymbolCandles:
    """Candles for the batch's windows: 1m always, plus 5m when the span is old.

    The coarse series is fetched alongside rather than instead, so a batch that
    straddles the venue's 1m retention boundary can measure its newer windows
    at 1m and its older ones at 5m, window by window, instead of writing the
    older ones off because the batch as a whole had some 1m data.
    """
    span = required_span_s(opened_at_s, LONGEST_HORIZON, CANDLE_SECONDS)
    if span is None:
        return SymbolCandles([], [], [], [])
    # Start an hour earlier: the entry regime is read from the candles that
    # closed before each opportunity fired, out of the same fetch.
    span = (span[0] - lookback_margin_s(CANDLE_SECONDS), span[1])
    fine, fine_ranges = await _fetch_interval(symbol, span, OUTCOME_CANDLE_INTERVAL, client)
    coarse: list[dict[str, Any]] = []
    coarse_ranges: list[FetchRange] = []
    if span[0] < now_s - FINE_RETENTION_S:
        coarse, coarse_ranges = await _fetch_interval(symbol, span, COARSE_CANDLE_INTERVAL, client)
    return SymbolCandles(fine, fine_ranges, coarse, coarse_ranges)


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


EMPTY_AT_FINE = "no candles cover this window"


def fall_back_per_window(
    fine: list[HorizonOutcome], coarse: list[HorizonOutcome] | None
) -> list[HorizonOutcome]:
    """Use the coarse result only for horizons the fine series could not cover.

    A horizon that measured at 1m keeps its 1m result. One that found no 1m
    candles takes the 5m result if there is one — after ``guard_coarse`` has
    labelled it or refused it. With no coarse series the fine verdict stands.
    """
    if coarse is None:
        return fine
    by_horizon = {h.horizon_minutes: h for h in guard_coarse(coarse, COARSE_CANDLE_INTERVAL)}
    out = []
    for horizon in fine:
        empty = horizon.status == "insufficient_candles" and horizon.reason == EMPTY_AT_FINE
        out.append(by_horizon.get(horizon.horizon_minutes, horizon) if empty else horizon)
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

    series: dict[str, SymbolCandles] = {}
    async with httpx.AsyncClient() as client:
        for symbol, opened in by_symbol.items():
            series[symbol] = await fetch_candles_for(symbol, opened, client, now_s)

    measured = 0
    for row in pending:
        opened_at_s = int(row["snapshot_ts"].timestamp())
        sc = series.get(row["symbol"]) or SymbolCandles([], [], [], [])

        def measure(candles: list[dict[str, Any]]):
            return measure_opportunity(
                opportunity_id=str(row["id"]),
                symbol=row["symbol"],
                direction=row["dir"],
                opened_at_s=opened_at_s,
                candles=candles,
                now_s=now_s,
            )

        try:
            outcome = measure(sc.fine)
            fine = guard_unrequested(outcome.horizons, sc.fine_ranges, opened_at_s)
            coarse = None
            if sc.coarse_ranges and any(
                h.status == "insufficient_candles" and h.reason == EMPTY_AT_FINE for h in fine
            ):
                coarse = guard_unrequested(measure(sc.coarse).horizons, sc.coarse_ranges, opened_at_s)
        except OutcomeError as exc:
            print(f"[Outcomes] skipping {row['id']}: {exc}")
            continue
        outcome = replace(outcome, horizons=fall_back_per_window(fine, coarse))
        await store_outcome(conn, outcome, row["symbol"], row["dir"])
        measured += sum(1 for h in outcome.horizons if h.status == "measured")
        await _record_regime(conn, row, opened_at_s, sc)

    labelled = await _backfill_regimes(conn, {str(r["id"]) for r in pending}, now_s)
    return {"opportunities": len(pending), "measured": measured, "regimes_backfilled": labelled}


async def _record_regime(conn, row, opened_at_s: int, sc: SymbolCandles) -> None:
    """Label the entry regime from whichever series covers the hour before entry."""
    if any(c["time"] < opened_at_s for c in sc.fine):
        await store_entry_regime(conn, str(row["id"]), row["symbol"], opened_at_s, sc.fine,
                                 CANDLE_SECONDS, OUTCOME_CANDLE_INTERVAL)
    elif sc.coarse:
        await store_entry_regime(conn, str(row["id"]), row["symbol"], opened_at_s, sc.coarse,
                                 COARSE_SECONDS, COARSE_CANDLE_INTERVAL)
    # No candles before entry at either interval: no row, and it is retried
    # by the backfill on a later pass rather than labelled "unknown" now.


async def _backfill_regimes(conn, skip: set[str], now_s: int) -> int:
    """Label opportunities that already have outcomes but no entry regime.

    Their outcomes are not re-measured — only the regime is added — so a fetch
    at a coarser interval today cannot change a result recorded at 1m earlier.
    """
    rows = [r for r in await missing_regime_opportunities(conn, OUTCOME_BATCH) if str(r["id"]) not in skip]
    if not rows:
        return 0
    by_symbol: dict[str, list[int]] = {}
    for row in rows:
        by_symbol.setdefault(row["symbol"], []).append(int(row["snapshot_ts"].timestamp()))
    series: dict[str, SymbolCandles] = {}
    async with httpx.AsyncClient() as client:
        for symbol, opened in by_symbol.items():
            series[symbol] = await fetch_candles_for(symbol, opened, client, now_s)
    labelled = 0
    for row in rows:
        sc = series.get(row["symbol"]) or SymbolCandles([], [], [], [])
        before = await conn.fetchval(
            "SELECT count(*) FROM opportunity_entry_regimes WHERE opportunity_id = $1::uuid", str(row["id"])
        )
        await _record_regime(conn, row, int(row["snapshot_ts"].timestamp()), sc)
        after = await conn.fetchval(
            "SELECT count(*) FROM opportunity_entry_regimes WHERE opportunity_id = $1::uuid", str(row["id"])
        )
        labelled += int(after) - int(before)
    return labelled
