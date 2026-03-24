import os
import json
import uuid
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
import redis.asyncio as redis
import httpx

app = FastAPI(title="TradeSync Hyperliquid Execution Service", version="0.1.0")

# --- Config ---
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
EXECUTION_ENABLED = os.getenv("EXECUTION_ENABLED", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

# Existing repo env names
HYPERLIQUID_API_URL = os.getenv("HYPERLIQUID_API_URL", "https://api.hyperliquid.xyz/exchange")
HYPERLIQUID_WALLET_PK = os.getenv("HYPERLIQUID_WALLET_PK")

# --- Redis Client ---
_redis_client = None

async def get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    return _redis_client

# --- Models ---
class OrderRequest(BaseModel):
    symbol: str
    side: str # "buy" | "sell"
    order_type: str = "market" # "market" | "limit"
    size_usd: Optional[float] = None
    size: Optional[float] = None
    venue: str
    limit_px: Optional[float] = None
    reduce_only: bool = False
    idempotency_key: Optional[str] = None

class Position(BaseModel):
    venue: str = "hyperliquid"
    symbol: str
    side: str
    size_usd: float
    entry_price: float
    mark_price: float
    pnl_usd: float
    leverage: float
    timestamp: datetime

class PreflightResponse(BaseModel):
    ok: bool
    venue: str = "hyperliquid"
    checks: Dict[str, Any]

class ExecutionError(BaseModel):
    code: str
    message: str

class ExecutionResult(BaseModel):
    ok: bool
    venue: str = "hyperliquid"
    dry_run: bool
    execution_enabled: bool
    status: str # "placed" | "rejected" | "error"
    order_id: Optional[str] = None
    idempotency_key: str
    request_payload: Dict[str, Any]
    response_payload: Dict[str, Any]
    error: Optional[ExecutionError] = None
    ts: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

# --- Helpers ---
async def perform_hl_preflight(symbol: Optional[str] = None):
    coin = symbol.replace("-PERP", "").upper() if symbol else None
    valid_assets = ["BTC", "ETH", "SOL", "ARB"]
    
    checks = {
        "env_ok": HYPERLIQUID_WALLET_PK is not None,
        "rpc_ok": False,
        "market_map_ok": True if symbol is None else (coin in valid_assets),
        "account_ok": "unknown"
    }
    
    # HTTP Check to base URL
    try:
        async with httpx.AsyncClient() as client:
            # Simple metadata ping
            resp = await client.post(HYPERLIQUID_API_URL, json={"type":"info","item":"meta"}, timeout=2.0)
            checks["rpc_ok"] = (resp.status_code == 200)
    except Exception:
         checks["rpc_ok"] = False
         
    return checks

# --- Endpoints ---

@app.get("/healthz")
async def healthz():
    return {
        "ok": True, 
        "venue": "hyperliquid", 
        "dry_run": DRY_RUN,
        "execution_enabled": EXECUTION_ENABLED,
        "config_valid": HYPERLIQUID_WALLET_PK is not None if EXECUTION_ENABLED else True
    }

@app.get("/exec/hl/preflight", response_model=PreflightResponse)
async def get_hl_preflight(symbol: Optional[str] = None):
    checks = await perform_hl_preflight(symbol)
    return PreflightResponse(ok=all([checks["env_ok"], checks["rpc_ok"], checks["market_map_ok"]]), checks=checks)

@app.get("/exec/hl/circuit-status")
async def get_hl_circuit_status():
    r = await get_redis()
    disabled = await r.get("exec:disabled:hl")
    failcount = await r.get("exec:failcount:hl")
    return {
        "venue": "hyperliquid",
        "circuit_open": disabled == "true",
        "consecutive_failures": int(failcount or 0),
        "threshold": 5
    }

@app.get("/exec/hl/positions", response_model=List[Position])
async def get_hl_positions():
    """Returns current positions. Mocks one if DRY_RUN."""
    if DRY_RUN:
        return [
            Position(
                venue="hyperliquid",
                symbol="ETH-PERP",
                side="SHORT",
                size_usd=850.20,
                entry_price=2540.5,
                mark_price=2535.1,
                pnl_usd=5.1,
                leverage=2.5,
                timestamp=datetime.utcnow()
            )
        ]
    return []

@app.post("/exec/hl/order", response_model=ExecutionResult)
async def execute_hl_order(req: OrderRequest):
    execution_id = str(uuid.uuid4())
    idempo_val = req.idempotency_key or execution_id
    
    r = await get_redis()
    idempo_key = f"exec:idempo:hl:{idempo_val}"
    
    # 1. Idempotency Check
    cached = await r.get(idempo_key)
    if cached:
        return ExecutionResult(**json.loads(cached))
    
    # 2. Circuit Breaker Check
    disabled_flag = await r.get("exec:disabled:hl")
    if disabled_flag == "true":
        return ExecutionResult(
            ok=False,
            venue="hyperliquid",
            dry_run=DRY_RUN,
            execution_enabled=EXECUTION_ENABLED,
            status="error",
            idempotency_key=idempo_val,
            request_payload=req.model_dump(),
            response_payload={},
            error=ExecutionError(code="RPC_FAIL", message="Circuit breaker active: Venue temporarily disabled"),
            ts=datetime.utcnow().isoformat()
        )

    base_result = {
        "venue": "hyperliquid",
        "dry_run": DRY_RUN,
        "execution_enabled": EXECUTION_ENABLED,
        "idempotency_key": idempo_val,
        "request_payload": req.model_dump()
    }

    # Helper to return and cache
    async def finish(ok: bool, status: str, order_id: str = None, error: ExecutionError = None, response_payload: dict = {}):
        res = ExecutionResult(
            ok=ok,
            status=status,
            order_id=order_id,
            error=error,
            response_payload=response_payload,
            **base_result
        )

        # --- Circuit Breaker Logic ---
        fail_key = "exec:failcount:hl"
        disabled_key = "exec:disabled:hl"
        
        if status == "error":
            new_count = await r.incr(fail_key)
            if new_count >= 5:
                await r.set(disabled_key, "true", ex=600)
                print(f"[Circuit Breaker] Venue 'hl' disabled for 600s after {new_count} failures")
        elif status == "placed":
            await r.delete(fail_key)

        # Cache for 24h
        await r.set(idempo_key, res.model_dump_json(), ex=86400)
        return res

    # 3. Execution Enabled Check
    if not EXECUTION_ENABLED:
        return await finish(False, "rejected", error=ExecutionError(code="EXEC_DISABLED", message="Execution disabled"))

    # 3. Preflight Checks
    checks = await perform_hl_preflight(req.symbol)
    
    if not checks["env_ok"]:
        return await finish(False, "error", error=ExecutionError(code="UNKNOWN", message="Environment config incomplete"))
    
    if not checks["rpc_ok"]:
        return await finish(False, "error", error=ExecutionError(code="RPC_FAIL", message="Hyperliquid API connectivity failed"))
        
    if not checks["market_map_ok"]:
        return await finish(False, "rejected", error=ExecutionError(code="MARKET_NOT_FOUND", message=f"Symbol {req.symbol} not found on HL"))

    # 4. Validation (Remaining)
    if req.order_type == "limit" and req.limit_px is None:
        return await finish(False, "rejected", error=ExecutionError(code="UNKNOWN", message="limit_px required"))
    
    if req.size_usd is None and req.size is None:
        return await finish(False, "rejected", error=ExecutionError(code="INVALID_SIZE", message="Missing size"))

    coin = req.symbol.replace("-PERP", "").upper()
    # Mock size conversion
    mock_price = req.limit_px or 50000.0 if "BTC" in coin else 2500.0
    computed_sz = req.size or (req.size_usd / mock_price if req.size_usd else 0)
    
    hl_payload = {
        "action": {
            "type": "order",
            "orders": [{
                "asset": coin, 
                "isBuy": req.side.lower() == "buy",
                "limitPx": str(req.limit_px) if req.limit_px else str(mock_price),
                "sz": str(round(computed_sz, 4)),
                "reduceOnly": req.reduce_only
            }]
        }
    }

    # 5. Handle DRY_RUN
    if DRY_RUN:
        return await finish(True, "placed", order_id=f"sim_hl_{os.urandom(8).hex()}", response_payload=hl_payload)

    # 6. Real Execution (Fallback)
    return await finish(False, "error", error=ExecutionError(code="RPC_FAIL", message="Real HL execution not implemented"), response_payload=hl_payload)
