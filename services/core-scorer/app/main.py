import os
import json
import time
import uuid
import asyncio
import asyncpg
import redis.asyncio as redis
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from tradesync_core.core_score import calculate_score as _core_calculate_score, Event as CoreEvent
from tradesync_core.paper_signal import AdmissionPolicy, decide_paper_signal
from tradesync_core.symbols import normalize_symbol
from .paper_producer import (
    direction_hold_max_age_seconds,
    has_active_opportunity,
    last_admitted_direction,
    persist_decision,
    publish_decision,
)
from .outcome_job import OUTCOME_INTERVAL_SECONDS, run_outcome_pass
from .regime_source import fetch_regime_evidence
from .retention_job import RETENTION_INTERVAL_SECONDS, run_retention_pass

app = FastAPI(title="TradeSync Core Scorer", version="0.1.0")

# Env vars
PG_DSN = os.getenv("PG_DSN", "postgresql://tradesync:CHANGE_ME@localhost:5432/tradesync")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SCORING_INTERVAL = int(os.getenv("SCORING_INTERVAL", "60"))
# One symbol list for the whole stack: MARKET_SYMBOLS, as market-data reads it.
# The scorer speaks in bare coins, so the -PERP suffix is dropped here rather
# than kept as a second, divergent list.
SYMBOLS = [
    s.strip().replace("-PERP", "")
    for s in os.getenv("MARKET_SYMBOLS", os.getenv("SYMBOLS", "BTC,ETH,SOL")).split(",")
    if s.strip()
]

# The regime path is the native Hyperliquid paper pipeline. The legacy
# events-table path below remains importable for replay of historical rows,
# but it is no longer what the running loop produces.
REGIME_PAPER_ENABLED = os.getenv("REGIME_PAPER_ENABLED", "true").lower() == "true"
# The fastest catalog feature samples every 60s, so a shorter cycle would
# re-read the same evidence and fan out history requests for nothing.
REGIME_CYCLE_INTERVAL = int(os.getenv("REGIME_CYCLE_INTERVAL", "60"))
MINIMUM_COVERAGE_TO_EMIT = float(os.getenv("MINIMUM_COVERAGE_TO_EMIT", "0.30"))
DIRECTION_DEADBAND = float(os.getenv("DIRECTION_DEADBAND", "0.05"))
MAXIMUM_EVIDENCE_AGE_MS = int(os.getenv("MAXIMUM_EVIDENCE_AGE_MS", "120000"))


def admission_policy() -> AdmissionPolicy:
    return AdmissionPolicy(
        minimum_coverage_to_emit=MINIMUM_COVERAGE_TO_EMIT,
        direction_deadband=DIRECTION_DEADBAND,
        maximum_evidence_age_ms=MAXIMUM_EVIDENCE_AGE_MS,
    )

# Redis Config
redis_client = None
async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    return redis_client

async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None

# --- Models ---

class Event(BaseModel):
    id: str
    ts: datetime
    source: str
    kind: str
    symbol: str
    payload: Dict[str, Any]

class SignalResponse(BaseModel):
    id: str
    symbol: str
    score: float
    confidence: float
    direction: str
    created_at: datetime
    inputs: List[str]

# --- Logic ---

def calculate_score(events: List[Event]) -> float:
    """Adapter: converts DB Event -> CoreEvent, delegates to shared library."""
    if not events:
        return 0.0
    core_events = [
        CoreEvent(ts=e.ts, source=e.source, kind=e.kind, payload=e.payload)
        for e in events
    ]
    return _core_calculate_score(core_events)

async def fetch_events(conn, symbol: str, minutes: int = 30) -> List[Event]:
    # Fetch events for the last N minutes
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    
    rows = await conn.fetch("""
        SELECT id, ts, source, kind, symbol, payload
        FROM events
        WHERE symbol = $1
          AND ts > $2
          AND (
            (source = 'tradingview') OR 
            (source = 'metrics' AND kind = 'market_snapshot')
          )
    """, symbol, cutoff)
    
    return [
        Event(
            id=str(r["id"]),
            ts=r["ts"],
            source=r["source"],
            kind=r["kind"],
            symbol=r["symbol"],
            payload=json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        )
        for r in rows
    ]

async def save_signal(conn, symbol: str, score: float, event_ids: List[str], signal_id: Optional[str] = None):
    # Confidence: abs(score) / 10
    confidence = abs(score) / 10.0
    if score > 0:
        direction = "LONG"
    elif score < 0:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"
        
    if not signal_id:
        signal_id = str(uuid.uuid4())
    ts = datetime.utcnow()
        
    # 1. Postgres
    await conn.execute("""
        INSERT INTO signals (
            id, agent, symbol, timeframe, kind, confidence, dir, features, event_ids, created_at
        ) VALUES (
            $1, 'core_scorer', $2, '1m', 'bias_score', $3, $4, $5, $6, $7
        )
    """, signal_id, symbol, confidence, direction, json.dumps({"score": score}), event_ids, ts)
    
    # 2. Redis
    try:
        r = await get_redis()
        payload = {
            "id": signal_id,
            "agent": "core_scorer",
            "symbol": symbol,
            "score": score,
            "confidence": confidence,
            "direction": direction,
            "event_ids": event_ids,
            "created_at": ts.isoformat()
        }
        await r.xadd("x:signals.funding", {"data": json.dumps(payload)})
    except Exception as e:
        print(f"Redis Signal Error: {e}")

async def run_scoring_cycle():
    print(f"Starting scoring cycle for {SYMBOLS}")
    try:
        conn = await asyncpg.connect(PG_DSN)
        try:
            for symbol in SYMBOLS:
                # Normalize symbol lookup
                events = await fetch_events(conn, symbol)
                if not events:
                    events = await fetch_events(conn, f"{symbol}-PERP")
                
                if not events:
                    continue
                
                score = calculate_score(events)
                event_ids = [e.id for e in events]
                
                # Save Signal
                signal_id = str(uuid.uuid4())
                await save_signal(conn, symbol, score, event_ids, signal_id)
                print(f"Scored {symbol}: {score} (based on {len(events)} events)")
                
        finally:
            await conn.close()
    except Exception as e:
        print(f"Error in scoring cycle: {e}")

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


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(score_loop())
    asyncio.create_task(outcome_loop())
    asyncio.create_task(retention_loop())

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
