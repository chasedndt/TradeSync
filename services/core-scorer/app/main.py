import json
import asyncio
import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Query
# Event and calculate_score are imported from here by tests/test_core_scorer.py.
from .legacy_scoring import Event, SignalResponse, calculate_score, run_scoring_cycle  # noqa: F401
from .outcome_job import OUTCOME_INTERVAL_SECONDS, run_outcome_pass
from .regime_cycle import admission_policy, record_symbol_verdict, run_regime_paper_cycle  # noqa: F401
from .retention_job import RETENTION_INTERVAL_SECONDS, run_retention_pass
from .settings import PG_DSN, REGIME_CYCLE_INTERVAL, REGIME_PAPER_ENABLED, SCORING_INTERVAL

app = FastAPI(title="TradeSync Core Scorer", version="0.1.0")


async def score_loop():
    while True:
        if REGIME_PAPER_ENABLED:
            try:
                await run_regime_paper_cycle()
            except Exception as exc:
                print(f"[RegimePaper] Cycle error: {exc}")
            await asyncio.sleep(REGIME_CYCLE_INTERVAL)
        else:
            await run_scoring_cycle()
            await asyncio.sleep(SCORING_INTERVAL)

# --- Lifecycle ---

async def outcome_loop():
    """Measure past opportunities on its own cadence.

    Kept separate from the producer so a slow measurement can never delay or
    influence a live verdict.
    """
    while True:
        try:
            conn = await asyncpg.connect(PG_DSN)
            try:
                stats = await run_outcome_pass(conn)
            finally:
                await conn.close()
            if stats["opportunities"]:
                print(
                    f"[Outcomes] reviewed {stats['opportunities']} opportunities, "
                    f"{stats['measured']} horizons measured"
                )
        except Exception as exc:
            print(f"[Outcomes] pass failed: {exc}")
        await asyncio.sleep(OUTCOME_INTERVAL_SECONDS)


async def retention_loop():
    """Bound the refusal store, on its own slow cadence.

    Separate from scoring and from measurement: housekeeping must never delay a
    verdict or an outcome. Refusals are summarised into a permanent daily
    aggregate before they are removed, so the denominator behind every
    admission rate survives even though the rows do not.
    """
    while True:
        try:
            conn = await asyncpg.connect(PG_DSN)
            try:
                stats = await run_retention_pass(conn)
            finally:
                await conn.close()
            if stats["deleted"]:
                print(
                    f"[Retention] rolled {stats['rolled']} aggregate rows, "
                    f"removed {stats['deleted']} expired refusals"
                )
        except Exception as exc:
            print(f"[Retention] pass failed: {exc}")
        await asyncio.sleep(RETENTION_INTERVAL_SECONDS)


async def claims_loop():
    """Extract claims from quarantined material and measure them, on their own cadence.

    Separate from scoring and from the opportunity outcomes: a source's track
    record is bookkeeping about Tier B material and must never delay a
    verdict. See app/claims_job.py.
    """
    from .claims_job import CLAIMS_INTERVAL_SECONDS, run_claims_pass

    await asyncio.sleep(60)  # let the schema and market-data settle first
    while True:
        try:
            conn = await asyncpg.connect(PG_DSN)
            try:
                async with httpx.AsyncClient() as client:
                    stats = await run_claims_pass(conn, client)
            finally:
                await conn.close()
            if stats.get("extract_rows") or stats.get("measure_claims"):
                print(
                    f"[Claims] extracted {stats.get('extract_claims', 0)} claims from "
                    f"{stats.get('extract_rows', 0)} rows ({stats.get('extract_no_claim', 0)} no-claim); "
                    f"measured {stats.get('measure_measured', 0)} horizons over {stats.get('measure_claims', 0)} claims"
                )
        except Exception as exc:
            print(f"[Claims] pass failed: {exc}")
        await asyncio.sleep(CLAIMS_INTERVAL_SECONDS)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(score_loop())
    asyncio.create_task(outcome_loop())
    asyncio.create_task(retention_loop())
    asyncio.create_task(claims_loop())

# --- Endpoints ---

@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.get("/signals/latest", response_model=SignalResponse)
async def get_latest_signal(symbol: str = Query(..., description="Symbol to fetch signal for")):
    try:
        conn = await asyncpg.connect(PG_DSN)
        row = await conn.fetchrow("""
            SELECT id, created_at, confidence, dir, features, event_ids
            FROM signals
            WHERE symbol = $1 AND agent = 'core_scorer'
            ORDER BY created_at DESC
            LIMIT 1
        """, symbol)
        await conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="No signal found")

        features = json.loads(row["features"]) if isinstance(row["features"], str) else row["features"]
        score = features.get("score", 0.0)

        return SignalResponse(
            id=str(row["id"]),
            symbol=symbol,
            score=score,
            confidence=row["confidence"],
            direction=row["dir"],
            created_at=row["created_at"],
            inputs=[str(uid) for uid in row["event_ids"]]
        )

    except Exception as e:
        print(f"Error fetching signal: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail="Internal server error")
