import os
import json
import uuid
import asyncpg
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

from .models import TradingViewAlert, NormalizedEvent
from .db import insert_event, close_redis, get_redis

class SourceInfo(BaseModel):
    source: str
    last_seen: datetime
    age_seconds: float
    status: str
    kind: Optional[str] = None
    symbol: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
import sys
import os
# Add parent dir to path if not present (for running as app.main)
# Actually, if running from root, sources should be importable if root is in path.
# But let's assume standard uvicorn run from ingest-gateway dir.
# Then 'sources' is top level.
from sources.drift import poll_drift_markets
from sources.hyperliquid import poll_hyperliquid_markets

# Config
ENABLE_DRIFT = os.getenv("ENABLE_DRIFT", "true").lower() == "true"

# Background tasks
background_tasks = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    task_hl = asyncio.create_task(poll_hyperliquid_markets())
    background_tasks.append(task_hl)
    
    if ENABLE_DRIFT:
        task_drift = asyncio.create_task(poll_drift_markets())
        background_tasks.append(task_drift)
        
    yield
    # Shutdown
    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)
    await close_redis()

app = FastAPI(title="TradeSync Ingest Gateway", version="0.1.0", lifespan=lifespan)

# --- Exception Handlers ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"error": "validation_failed", "details": str(exc)},
    )

# --- Endpoints ---

@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.get("/ingest/sources", response_model=List[SourceInfo])
async def get_ingest_sources(mirror: bool = False):
    """
    Returns metadata about all ingestion sources.
    If mirror=true, includes the latest payload.
    """
    r = await get_redis()
    keys = await r.keys("ingest:source_mirror:*")
    sources = []
    
    now = datetime.now()
    for key in keys:
        try:
            data = await r.hgetall(key)
            if not data:
                continue
                
            source_name = key.replace("ingest:source_mirror:", "")
            last_seen_str = data.get("last_seen")
            if not last_seen_str:
                continue
                
            last_seen = datetime.fromisoformat(last_seen_str)
            age_seconds = (now - last_seen).total_seconds()
            
            source_info = {
                "source": source_name,
                "last_seen": last_seen,
                "age_seconds": round(age_seconds, 1),
                "status": "healthy" if age_seconds < 30 else "stale",
                "kind": data.get("kind"),
                "symbol": data.get("symbol")
            }
            
            if mirror:
                source_info["payload"] = json.loads(data.get("payload", "{}"))
                
            sources.append(source_info)
        except Exception as e:
            print(f"Error processing source mirror {key}: {e}")
            
    return sources

@app.post("/ingest/tv")
async def ingest_tv(
    alert: TradingViewAlert, 
    request: Request,
    user_agent: Optional[str] = Header(None),
    x_forwarded_for: Optional[str] = Header(None)
):
    """
    Ingest a webhook alert from TradingView.
    """
    ts = datetime.now()
    event_id = str(uuid.uuid4())
    
    # Provenance data
    client_host = request.client.host if request.client else "unknown"
    provenance = {
        "ip": x_forwarded_for or client_host,
        "user_agent": user_agent,
        "received_at": ts.isoformat()
    }

    # Map to NormalizedEvent
    # We use source:symbol:ts:bias to allow multiple alerts for same symbol if timestamps differ
    event_hash = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{alert.source}:{alert.symbol}:{ts.isoformat()}:{alert.bias}"))
    
    normalized_event = NormalizedEvent(
        id=event_id,
        ts=ts,
        source=alert.source,
        kind="alert",
        symbol=alert.symbol,
        timeframe=alert.timeframe,
        payload=alert.model_dump(),
        provenance=provenance,
        hash=event_hash
    )

    try:
        result = await insert_event(normalized_event)
        if result is None:
            return {"status": "ok", "id": event_id, "info": "duplicate"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "db_error"})

    return {"status": "ok", "id": event_id}
