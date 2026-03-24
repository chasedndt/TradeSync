import os
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
import redis.asyncio as redis
import httpx

app = FastAPI(title="TradeSync Drift Execution Service", version="0.1.0")

# --- Config ---
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
EXECUTION_ENABLED = os.getenv("EXECUTION_ENABLED", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

# Existing repo env names
DRIFT_RPC_URL = os.getenv("DRIFT_RPC_URL")
DRIFT_WALLET_PRIVATE_KEY = os.getenv("DRIFT_WALLET_PRIVATE_KEY")
DRIFT_ENV = os.getenv("DRIFT_ENV", "devnet")

# Static symbol mapping for demo/v1
MARKET_INDEX_MAP = {
    "BTC-PERP": 0,
    "ETH-PERP": 1,
    "SOL-PERP": 2,
    "BTC": 0,
    "ETH": 1,
    "SOL": 2
}

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
    base_size: Optional[float] = None
    venue: str
    limit_price: Optional[float] = None
    reduce_only: bool = False
    idempotency_key: Optional[str] = None

class Position(BaseModel):
    venue: str = "drift"
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
    venue: str = "drift"
    checks: Dict[str, Any]

class ExecutionError(BaseModel):
    code: str
    message: str

class ExecutionResult(BaseModel):
    ok: bool
    venue: str = "drift"
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
async def perform_drift_preflight(symbol: Optional[str] = None):
    checks = {
        "env_ok": all([DRIFT_RPC_URL, DRIFT_WALLET_PRIVATE_KEY]),
        "rpc_ok": False,
        "market_map_ok": True if symbol is None else (map_symbol_to_index(symbol) is not None),
        "account_ok": "unknown"
    }
    
    # RPC Check
    if DRIFT_RPC_URL:
        try:
            async with httpx.AsyncClient() as client:
                # Simple post to verify RPC is alive
                resp = await client.post(DRIFT_RPC_URL, json={"jsonrpc":"2.0","id":1,"method":"getHealth","params":[]}, timeout=2.0)
                checks["rpc_ok"] = (resp.status_code == 200)
        except Exception:
             checks["rpc_ok"] = False
    
    return checks

def map_symbol_to_index(symbol: str) -> int:
    idx = MARKET_INDEX_MAP.get(symbol.upper())
    if idx is None:
        return None
    return idx

# --- Endpoints ---

@app.get("/healthz")
async def healthz():
    return {
        "ok": True, 
        "venue": "drift", 
        "dry_run": DRY_RUN, 
        "execution_enabled": EXECUTION_ENABLED,
        "config_valid": all([DRIFT_RPC_URL, DRIFT_WALLET_PRIVATE_KEY]) if EXECUTION_ENABLED else True
    }

@app.get("/exec/drift/preflight", response_model=PreflightResponse)
async def get_drift_preflight(symbol: Optional[str] = None):
    checks = await perform_drift_preflight(symbol)
    return PreflightResponse(ok=all([checks["env_ok"], checks["rpc_ok"], checks["market_map_ok"]]), checks=checks)

@app.get("/exec/drift/circuit-status")
async def get_drift_circuit_status():
    r = await get_redis()
    disabled = await r.get("exec:disabled:drift")
    failcount = await r.get("exec:failcount:drift")
    return {
        "venue": "drift",
        "circuit_open": disabled == "true",
        "consecutive_failures": int(failcount or 0),
        "threshold": 5
    }

@app.get("/exec/drift/positions", response_model=List[Position])
async def get_drift_positions():
    """Returns current positions. Mocks one if DRY_RUN."""
    if DRY_RUN:
        return [
            Position(
                venue="drift",
                symbol="BTC-PERP",
                side="LONG",
                size_usd=1200.50,
                entry_price=93250.0,
                mark_price=93510.2,
                pnl_usd=14.2,
                leverage=3.0,
                timestamp=datetime.utcnow()
            )
        ]
    return []

@app.post("/exec/drift/order", response_model=ExecutionResult)
async def execute_drift_order(req: OrderRequest):
    execution_id = str(uuid.uuid4())
    idempo_val = req.idempotency_key or execution_id
    
    r = await get_redis()
    idempo_key = f"exec:idempo:drift:{idempo_val}"
    
    # 1. Idempotency Check
    cached = await r.get(idempo_key)
    if cached:
        return ExecutionResult(**json.loads(cached))

    # 2. Circuit Breaker Check
    disabled_flag = await r.get("exec:disabled:drift")
    if disabled_flag == "true":
        return ExecutionResult(
            ok=False,
            venue="drift",
            dry_run=DRY_RUN,
            execution_enabled=EXECUTION_ENABLED,
            status="error",
            idempotency_key=idempo_val,
            request_payload=req.model_dump(),
            response_payload={},
            error=ExecutionError(code="RPC_FAIL", message="Circuit breaker active: Venue temporarily disabled due to failures"),
            ts=datetime.utcnow().isoformat()
        )

    base_result = {
        "venue": "drift",
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
        fail_key = "exec:failcount:drift"
        disabled_key = "exec:disabled:drift"
        
        if status == "error":
            # Increment failure count
            new_count = await r.incr(fail_key)
            if new_count >= 5:
                # Open the circuit for 10 minutes
                await r.set(disabled_key, "true", ex=600)
                print(f"[Circuit Breaker] Venue 'drift' disabled for 600s after {new_count} failures")
        elif status == "placed":
            # Reset success
            await r.delete(fail_key)

        # Cache for 24h
        await r.set(idempo_key, res.model_dump_json(), ex=86400)
        return res

    # 3. Execution Enabled Check
    if not EXECUTION_ENABLED:
        return await finish(False, "rejected", error=ExecutionError(code="EXEC_DISABLED", message="Execution is disabled"))

    # 3. Preflight Checks
    checks = await perform_drift_preflight(req.symbol)
    
    if not checks["env_ok"]:
        return await finish(False, "error", error=ExecutionError(code="UNKNOWN", message="Environment config incomplete"))
    
    if not checks["rpc_ok"]:
        return await finish(False, "error", error=ExecutionError(code="RPC_FAIL", message="RPC connectivity failed"))
        
    if not checks["market_map_ok"]:
        return await finish(False, "rejected", error=ExecutionError(code="MARKET_NOT_FOUND", message=f"Symbol {req.symbol} not found"))

    # 3. Validation (Remaining)
    if req.order_type == "limit" and req.limit_price is None:
        return await finish(False, "rejected", error=ExecutionError(code="UNKNOWN", message="limit_price required"))
    
    if req.size_usd is None and req.base_size is None:
        return await finish(False, "rejected", error=ExecutionError(code="INVALID_SIZE", message="Missing size"))

    mock_price = req.limit_price or 50000.0 if "BTC" in req.symbol.upper() else 2500.0
    computed_base_size = req.base_size or (req.size_usd / mock_price if req.size_usd else 0)
    
    if (req.size_usd or 0) < 10.0 and req.base_size is None:
         return await finish(False, "rejected", error=ExecutionError(code="NOTIONAL_TOO_SMALL", message="Min order $10"))

    drift_payload = {
        "order_params": {
            "order_type": req.order_type.upper(),
            "market_index": map_symbol_to_index(req.symbol),
            "direction": "LONG" if req.side.lower() == "buy" else "SHORT",
            "base_asset_amount": int(computed_base_size * 1e9),
            "price": int((req.limit_price or 0) * 1e6),
            "reduce_only": req.reduce_only
        }
    }

    # 4. Handle DRY_RUN
    if DRY_RUN:
        return await finish(True, "placed", order_id=f"sim_tx_{os.urandom(8).hex()}", response_payload=drift_payload)

    # 5. Real Execution (Fallback)
    return await finish(False, "error", error=ExecutionError(code="RPC_FAIL", message="Real execution not implemented"), response_payload=drift_payload)
