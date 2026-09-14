"""One regime-backed paper verdict per symbol per cycle, admitted or refused."""

import time
import asyncpg
from tradesync_core.paper_signal import AdmissionPolicy, decide_paper_signal
from tradesync_core.symbols import normalize_symbol

from .active_weights import apply_active_rulebook
from .paper_producer import (
    direction_hold_max_age_seconds,
    has_active_opportunity,
    last_admitted_direction,
    persist_decision,
    publish_decision,
)
from .redis_conn import get_redis
from .regime_source import fetch_regime_evidence
from .settings import (
    DIRECTION_DEADBAND,
    MAXIMUM_EVIDENCE_AGE_MS,
    MINIMUM_COVERAGE_TO_EMIT,
    PG_DSN,
    SCORING_INTERVAL,
    SYMBOLS,
)


def admission_policy() -> AdmissionPolicy:
    return AdmissionPolicy(
        minimum_coverage_to_emit=MINIMUM_COVERAGE_TO_EMIT,
        direction_deadband=DIRECTION_DEADBAND,
        maximum_evidence_age_ms=MAXIMUM_EVIDENCE_AGE_MS,
    )


async def run_regime_paper_cycle():
    """Ask the regime engine for evidence, then record one verdict per symbol."""
    for configured in SYMBOLS:
        symbol = normalize_symbol(configured.strip())
        if not symbol:
            continue
        try:
            await record_symbol_verdict(symbol)
        except Exception as exc:
            print(f"[RegimePaper] {symbol} failed: {exc}")


async def record_symbol_verdict(symbol: str):
    """Record exactly one verdict for ``symbol``, admitted or refused."""
    evidence = await fetch_regime_evidence(symbol)
    if not evidence.available:
        print(f"[RegimePaper] {symbol}: no admissible evidence: {evidence.reason}")
        return

    evaluated_at_ms = int(time.time() * 1000)

    conn = await asyncpg.connect(PG_DSN)
    try:
        # Read every cycle: an adoption or a revert takes effect on the next
        # verdict, and anything unreadable falls back to the file weights.
        evidence, weights = await apply_active_rulebook(conn, evidence)
        if weights.fell_back:
            print(f"[RegimePaper] {symbol}: {weights.reason}")
        # A side counts as held only while it is still current. Passing the
        # bound explicitly keeps the cadence and the stickiness in one place.
        previous_direction = await last_admitted_direction(
            conn, symbol, direction_hold_max_age_seconds(SCORING_INTERVAL)
        )
        decision = decide_paper_signal(
            symbol=symbol,
            evaluation=evidence.evaluation,
            feature_results=evidence.feature_results,
            catalog_summary=evidence.catalog,
            evaluated_at_ms=evaluated_at_ms,
            policy=admission_policy(),
            directional=evidence.directional or None,
            previous_direction=previous_direction,
        )
        signal_id, created_at = await persist_decision(conn, decision)
        duplicate = decision.admitted and await has_active_opportunity(
            conn, symbol, decision.direction
        )
    finally:
        await conn.close()

    if decision.admitted and duplicate:
        # The side has not changed and the previous opportunity is still live.
        # The verdict is recorded, but republishing would create a duplicate.
        print(
            f"[RegimePaper] {symbol} still {decision.direction}; "
            "active opportunity retained, not duplicated."
        )
    elif decision.admitted:
        r = await get_redis()
        await publish_decision(r, decision, signal_id, created_at)
        print(
            f"[RegimePaper] Admitted {decision.direction} {symbol} "
            f"directional={decision.directional_score} coverage={decision.data_coverage}"
        )
    else:
        codes = ", ".join(reason["code"] for reason in decision.rejection_reasons)
        print(f"[RegimePaper] No opportunity for {symbol}. Reasons: {codes}")
