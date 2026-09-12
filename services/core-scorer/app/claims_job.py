"""Extract claims from quarantined material and measure what happened after them.

Two passes on one cadence, both idempotent and oldest-first:

1. **Extraction.** Every accepted quarantine row from an extractable source
   that has no extraction record yet goes through
   ``tradesync_core.claim_extraction``. The result — claims, or the reason
   there were none — is recorded, so a row is read exactly once.
2. **Measurement.** Every claim with an open horizon is measured against
   venue candles exactly as a paper opportunity is, reusing the outcome job's
   candle fetching (1m, with the 5m fallback for old windows) and the same
   guards: a final "no candles" is only written for a window that was asked
   for and answered.

Nothing here scores anything. A measured claim is a row a source card can be
built from; what a source has earned is decided at read time, together with
every other cell, by the same Holm-adjusted machinery as the skill gate.
"""

from __future__ import annotations

import os
import time
from dataclasses import replace

from tradesync_core.claim_extraction import EXTRACTOR, NoClaim, extract
from tradesync_core.outcomes import OutcomeError, measure_opportunity

from .claims_store import (
    pending_claims,
    record_extraction,
    store_claim_outcome,
    unextracted_rows,
)
from .outcome_job import (
    EMPTY_AT_FINE,
    SymbolCandles,
    fall_back_per_window,
    fetch_candles_for,
    guard_unrequested,
)

CLAIMS_INTERVAL_SECONDS = int(os.getenv("CLAIMS_INTERVAL_SECONDS", "300"))
CLAIMS_BATCH = int(os.getenv("CLAIMS_BATCH", "200"))


async def run_extraction_pass(conn) -> dict[str, int]:
    rows = await unextracted_rows(conn, CLAIMS_BATCH)
    counts = {"rows": len(rows), "claims": 0, "no_claim": 0}
    for row in rows:
        received_ms = int(row["received_at"].timestamp() * 1000)
        observed_ms = int(row["observed_at"].timestamp() * 1000) if row["observed_at"] else None
        result = extract(row["source"], row["payload"], received_ms, observed_ms)
        if isinstance(result, NoClaim):
            await record_extraction(conn, str(row["id"]), EXTRACTOR, [], result.reason)
            counts["no_claim"] += 1
        else:
            await record_extraction(conn, str(row["id"]), EXTRACTOR, result, "")
            counts["claims"] += len(result)
    return counts


async def run_measurement_pass(conn, client) -> dict[str, int]:
    pending = await pending_claims(conn, CLAIMS_BATCH)
    if not pending:
        return {"claims": 0, "measured": 0}
    now_s = int(time.time())
    by_symbol: dict[str, list[int]] = {}
    for row in pending:
        by_symbol.setdefault(row["symbol"], []).append(int(row["claimed_at"].timestamp()))
    series: dict[str, SymbolCandles] = {}
    for symbol, opened in by_symbol.items():
        series[symbol] = await fetch_candles_for(symbol, opened, client, now_s)

    measured = 0
    for row in pending:
        claimed_at_s = int(row["claimed_at"].timestamp())
        sc = series.get(row["symbol"]) or SymbolCandles([], [], [], [])

        def measure(candles):
            return measure_opportunity(
                opportunity_id=str(row["id"]), symbol=row["symbol"], direction=row["direction"],
                opened_at_s=claimed_at_s, candles=candles, now_s=now_s,
            )

        try:
            outcome = measure(sc.fine)
            fine = guard_unrequested(outcome.horizons, sc.fine_ranges, claimed_at_s)
            coarse = None
            if sc.coarse_ranges and any(h.status == "insufficient_candles" and h.reason == EMPTY_AT_FINE for h in fine):
                coarse = guard_unrequested(measure(sc.coarse).horizons, sc.coarse_ranges, claimed_at_s)
        except OutcomeError as exc:
            print(f"[Claims] skipping {row['id']}: {exc}")
            continue
        outcome = replace(outcome, horizons=fall_back_per_window(fine, coarse))
        await store_claim_outcome(conn, outcome, row["symbol"], row["direction"])
        measured += sum(1 for h in outcome.horizons if h.status == "measured")
    return {"claims": len(pending), "measured": measured}


async def run_claims_pass(conn, client) -> dict[str, int]:
    extracted = await run_extraction_pass(conn)
    measured = await run_measurement_pass(conn, client)
    return {**{f"extract_{k}": v for k, v in extracted.items()}, **{f"measure_{k}": v for k, v in measured.items()}}
