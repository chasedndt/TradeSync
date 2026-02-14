import os
import json
import uuid
import asyncio
import asyncpg
import redis.asyncio as redis
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from tradesync_core.core_score import calculate_score as _core_calculate_score, Event as CoreEvent

app = FastAPI(title="TradeSync Core Scorer", version="0.1.0")

# Env vars
PG_DSN = os.getenv("PG_DSN", "postgresql://tradesync:CHANGE_ME@localhost:5432/tradesync")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SCORING_INTERVAL = int(os.getenv("SCORING_INTERVAL", "60"))
SYMBOLS = os.getenv("SYMBOLS", "BTC,ETH,SOL").split(",")

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

async def score_loop():
    while True:
        await run_scoring_cycle()
        await asyncio.sleep(SCORING_INTERVAL)

# --- Lifecycle ---

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(score_loop())

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
