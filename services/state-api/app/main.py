import os
import json
import uuid
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Any, Dict
from datetime import datetime
from collections import defaultdict

import asyncpg
import redis.asyncio as redis
import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field
from tradesync_core import RiskGuardian
from tradesync_core import normalize_symbol, normalize_venue
from app.macro_feed import macro_feed, MacroHeadline

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] trace_id=%(trace_id)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger("state-api")

# --- Metrics Storage ---
class MetricsCollector:
    def __init__(self):
        self.request_count = defaultdict(int)  # {(method, path, status): count}
        self.request_latency_sum = defaultdict(float)  # {(method, path): sum_ms}
        self.request_latency_count = defaultdict(int)  # {(method, path): count}
        self.startup_time = time.time()

    def record_request(self, method: str, path: str, status: int, latency_ms: float):
        key = (method, path, status)
        self.request_count[key] += 1
        latency_key = (method, path)
        self.request_latency_sum[latency_key] += latency_ms
        self.request_latency_count[latency_key] += 1

    def to_prometheus(self, db_stats: dict = None) -> str:
        lines = []

        # HTTP request metrics
        lines.append("# HELP http_requests_total Total HTTP requests")
        lines.append("# TYPE http_requests_total counter")
        for (method, path, status), count in self.request_count.items():
            lines.append(f'http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')

        lines.append("# HELP http_request_duration_ms_sum Sum of HTTP request durations in ms")
        lines.append("# TYPE http_request_duration_ms_sum counter")
        for (method, path), total in self.request_latency_sum.items():
            lines.append(f'http_request_duration_ms_sum{{method="{method}",path="{path}"}} {total:.2f}')

        lines.append("# HELP http_request_duration_ms_count Count of HTTP requests for latency")
        lines.append("# TYPE http_request_duration_ms_count counter")
        for (method, path), count in self.request_latency_count.items():
            lines.append(f'http_request_duration_ms_count{{method="{method}",path="{path}"}} {count}')

        # Uptime
        lines.append("# HELP process_uptime_seconds Uptime in seconds")
        lines.append("# TYPE process_uptime_seconds gauge")
        lines.append(f"process_uptime_seconds {time.time() - self.startup_time:.2f}")

        # Database pool stats
        if db_stats:
            lines.append("# HELP db_pool_size Current database pool size")
            lines.append("# TYPE db_pool_size gauge")
            lines.append(f"db_pool_size {db_stats.get('size', 0)}")

            lines.append("# HELP db_pool_free Free connections in pool")
            lines.append("# TYPE db_pool_free gauge")
            lines.append(f"db_pool_free {db_stats.get('free', 0)}")

        return "\n".join(lines) + "\n"

metrics = MetricsCollector()

# --- Trace ID Middleware ---
class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Get or generate trace ID
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())

        # Store in request state for access in endpoints
        request.state.trace_id = trace_id

        # Log request start
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={"trace_id": trace_id}
        )

        # Time the request
        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Request failed: {request.method} {request.url.path} - {str(e)}",
                extra={"trace_id": trace_id}
            )
            metrics.record_request(request.method, request.url.path, 500, latency_ms)
            raise

        latency_ms = (time.time() - start_time) * 1000

        # Record metrics
        metrics.record_request(request.method, request.url.path, response.status_code, latency_ms)

        # Log request completion
        logger.info(
            f"Request completed: {request.method} {request.url.path} {response.status_code} {latency_ms:.2f}ms",
            extra={"trace_id": trace_id}
        )

        # Add trace ID to response headers
        response.headers["X-Trace-Id"] = trace_id

        return response

# --- Config ---
PG_DSN = os.getenv("PG_DSN", "postgresql://tradesync:CHANGE_ME@postgres:5432/tradesync")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
POOL_MIN_SIZE = int(os.getenv("POOL_MIN_SIZE", "5"))
POOL_MAX_SIZE = int(os.getenv("POOL_MAX_SIZE", "20"))
POOL_TIMEOUT = float(os.getenv("POOL_TIMEOUT", "5.0"))
OPPORTUNITY_TTL_SECONDS = int(os.getenv("OPPORTUNITY_TTL_SECONDS", "300"))
# Capital base for account risk load calculation during preview.
# Not exchange margin — this is: total_open_notional / ACCOUNT_EQUITY_USD.
# Override via env var to match the real funded account size.
ACCOUNT_EQUITY_USD = float(os.getenv("ACCOUNT_EQUITY_USD", "50000.0"))
VALID_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "1d"]

# Canonical exec service positions endpoints — single source of truth within state-api.
# Used by _fetch_aggregated_positions() and the /state/positions route.
_EXEC_POSITIONS_URLS: Dict[str, str] = {
    "drift":       "http://exec-drift-svc:8003/exec/drift/positions",
    "hyperliquid": "http://exec-hl-svc:8004/exec/hl/positions",
}

# Daily notional cap across all executed orders. Enforced at preview time.
# Resets at midnight (calendar day boundary, UTC). Override via env var.
DAILY_NOTIONAL_LIMIT = float(os.getenv("DAILY_NOTIONAL_LIMIT", "50000.0"))

# RiskGuardian reason codes that indicate an opportunity is permanently ineligible.
# On preview rejection with one of these codes, status is written to 'blocked' so the
# opportunity is not retried by the cockpit and is not swept to 'expired' by TTL.
# Transient codes (rate limits, market microstructure, portfolio state) are excluded —
# those conditions change over time and the opportunity should remain retryable.
_NON_TRANSIENT_CODES = frozenset({
    "DNT",          # Symbol permanently on the Do-Not-Trade list; won't be removed per-opp
    "MIN_QUALITY",  # Quality is a fixed property of this snapshot; won't improve
    "STALE_DATA",   # Signal is too old; this opportunity's data will not get fresher
    "EXPIRED",      # Past expiry window; mirrors what the background TTL sweep does
    "MIN_SIZE",     # Request size is static for this opportunity lifecycle
    "MAX_LEVERAGE", # Derived from size vs capital base; static for this opportunity
})

# --- Global Client ---
redis_client = None

async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    return redis_client

# --- Models ---
class EventResponse(BaseModel):
    id: str
    ts: datetime
    source: str
    kind: str
    symbol: str
    timeframe: str
    payload: Dict[str, Any]

class SignalResponse(BaseModel):
    id: str
    created_at: datetime
    agent: str
    symbol: str
    timeframe: str
    kind: str
    confidence: float
    direction: str = Field(alias="dir")
    features: Dict[str, Any]

class HealthResponse(BaseModel):
    status: str
    postgres: bool
    last_event_ts: Optional[datetime]
    last_signal_ts: Optional[datetime]
    latency_ms: float

class OpportunityResponse(BaseModel):
    id: str
    symbol: str
    timeframe: str
    bias: float
    quality: float
    direction: str = Field(alias="dir")
    status: str
    snapshot_ts: datetime
    expires_at: Optional[datetime] = None
    links: Dict[str, Any]
    # Phase 3C: Enhanced scoring data
    confluence: Optional[Dict[str, Any]] = None

class ExecutionError(BaseModel):
    code: str
    message: str

class ExecutionResult(BaseModel):
    ok: bool
    venue: str
    dry_run: bool
    execution_enabled: bool
    status: str # "placed" | "rejected" | "error"
    order_id: Optional[str] = None
    idempotency_key: str
    request_payload: Dict[str, Any]
    response_payload: Dict[str, Any]
    error: Optional[ExecutionError] = None
    ts: str

class DecisionResponse(BaseModel):
    id: str
    opportunity_id: str
    venue: str
    requested: Dict[str, Any]
    risk: Dict[str, Any]
    created_at: datetime

class ExecOrderResponse(BaseModel):
    id: str
    decision_id: str
    venue: str
    status: str
    request: Dict[str, Any]
    response: Dict[str, Any]
    dry_run: bool
    created_at: datetime

class EvidenceResponse(BaseModel):
    opportunity: Optional[OpportunityResponse]
    signals: List[SignalResponse] = []
    events: List[EventResponse] = []
    decisions: List[Dict[str, Any]] = []
    exec_orders: List[Dict[str, Any]] = []

class Position(BaseModel):
    venue: str
    symbol: str
    side: str
    size_usd: float
    entry_price: float
    mark_price: float
    pnl_usd: float
    leverage: float
    timestamp: datetime

class SnapshotResponse(BaseModel):
    latest_event_ts: Optional[datetime]
    latest_signal_ts: Optional[datetime]
    latest_opportunity_ts: Optional[datetime]
    execution_gate: str
    # Backward-compatible per-service status strings
    drift_status: str
    hl_status: str
    drift_circuit: Optional[Dict[str, Any]] = None
    hl_circuit: Optional[Dict[str, Any]] = None
    stream_lengths: Dict[str, int] = {}
    ingest_sources: List[Dict[str, Any]] = []
    # Truthfulness additions: explicit degraded state and per-service health map
    service_health: Dict[str, Any] = {}
    degraded: bool = False
    errors: Dict[str, str] = {}
    snapshot_ts: Optional[datetime] = None

class RiskLimitResponse(BaseModel):
    max_leverage: float
    min_quality: float
    max_open_positions: int
    min_size_usd: float
    max_event_age: int
    max_signal_age: int
    blacklist: List[str]
    daily_notional_limit: float
    # Capital base used for account risk load calculation at preview time.
    # Matches ACCOUNT_EQUITY_USD env var (default $50k). Used as denominator in
    # margin_utilization = total_open_notional / account_equity_usd.
    account_equity_usd: float
    current_counters: Dict[str, Any]

class PreviewRequest(BaseModel):
    opportunity_id: str
    size_usd: float = 1000.0
    venue: str = "drift"

class PreviewResponse(BaseModel):
    decision_id: Optional[str] = None
    plan: Dict[str, Any]
    risk_verdict: Dict[str, Any]
    suggested_adjustments: Optional[Dict[str, Any]] = None

class ExecuteRequest(BaseModel):
    decision_id: str
    confirm: bool

# ExecutionResult is used as the response model for execute_action

# --- Lifespan & State ---
class AppState:
    pool: asyncpg.Pool = None

state = AppState()


async def expire_stale_opportunities():
    """Background task: marks stale 'new'/'previewed' opportunities as 'expired' using server-side TTL.

    Runs every 60 seconds. Uses OPPORTUNITY_TTL_SECONDS (default 300s).
    Respects the explicit expires_at field if set by fusion-engine; otherwise falls back to
    snapshot_ts + TTL. Only transitions 'new' and 'previewed' statuses — never touches
    'executed', 'blocked', or already-'expired' rows.
    The 'blocked' exclusion is intentional: blocked opportunities were permanently rejected
    at preview time and must not be silently overwritten to 'expired' by the TTL sweep.
    """
    while True:
        await asyncio.sleep(60)
        if not state.pool:
            continue
        try:
            async with state.pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE opportunities
                    SET status = 'expired'
                    WHERE status IN ('new', 'previewed')
                      AND (
                            (expires_at IS NOT NULL AND expires_at < now())
                         OR (expires_at IS NULL AND snapshot_ts < now() - make_interval(secs => $1))
                          )
                """, float(OPPORTUNITY_TTL_SECONDS))
                # asyncpg returns "UPDATE N" — extract count
                count = int(result.split()[-1]) if result else 0
                if count > 0:
                    logger.info(
                        f"TTL expiry: marked {count} opportunities as expired",
                        extra={"trace_id": "ttl-expiry"}
                    )
        except Exception as e:
            logger.error(f"TTL expiry task failed: {e}", extra={"trace_id": "ttl-expiry"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    ttl_task = None
    try:
        print(f"Connecting to DB pool: min={POOL_MIN_SIZE} max={POOL_MAX_SIZE}")
        state.pool = await asyncpg.create_pool(
            dsn=PG_DSN,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            command_timeout=POOL_TIMEOUT
        )
        ttl_task = asyncio.create_task(expire_stale_opportunities())
        yield
    finally:
        if ttl_task:
            ttl_task.cancel()
            try:
                await ttl_task
            except asyncio.CancelledError:
                pass
        if state.pool:
            print("Closing DB pool")
            await state.pool.close()

app = FastAPI(
    title="TradeSync State API",
    version="0.1.0",
    lifespan=lifespan
)

# Add Trace ID Middleware
app.add_middleware(TraceIdMiddleware)

def apply_deprecation_headers(response: Response, successor: str):
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'<{successor}>; rel="successor-version"'

# --- Endpoints ---

@app.get("/healthz")
async def healthz():
    """Simple liveness probe for k8s/docker."""
    return {"ok": True}

@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Prometheus-compatible metrics endpoint."""
    db_stats = {}
    if state.pool:
        db_stats = {
            "size": state.pool.get_size(),
            "free": state.pool.get_idle_size()
        }

    # Get additional application metrics from database
    app_metrics = {}
    if state.pool:
        try:
            async with state.pool.acquire() as conn:
                # Get counts
                row = await conn.fetchrow("""
                    SELECT
                        (SELECT COUNT(*) FROM events) as events_total,
                        (SELECT COUNT(*) FROM signals) as signals_total,
                        (SELECT COUNT(*) FROM opportunities) as opportunities_total,
                        (SELECT COUNT(*) FROM opportunities WHERE status = 'new') as opportunities_new,
                        (SELECT COUNT(*) FROM decisions) as decisions_total,
                        (SELECT COUNT(*) FROM exec_orders) as exec_orders_total,
                        (SELECT COUNT(*) FROM exec_orders WHERE status = 'placed') as exec_orders_placed
                """)
                if row:
                    app_metrics = dict(row)
        except Exception as e:
            logger.warning(f"Failed to fetch app metrics: {e}", extra={"trace_id": "metrics"})

    # Build Prometheus output
    output = metrics.to_prometheus(db_stats)

    # Add application-specific metrics
    if app_metrics:
        output += "\n# HELP tradesync_events_total Total events in database\n"
        output += "# TYPE tradesync_events_total gauge\n"
        output += f"tradesync_events_total {app_metrics.get('events_total', 0)}\n"

        output += "\n# HELP tradesync_signals_total Total signals in database\n"
        output += "# TYPE tradesync_signals_total gauge\n"
        output += f"tradesync_signals_total {app_metrics.get('signals_total', 0)}\n"

        output += "\n# HELP tradesync_opportunities_total Total opportunities in database\n"
        output += "# TYPE tradesync_opportunities_total gauge\n"
        output += f"tradesync_opportunities_total {app_metrics.get('opportunities_total', 0)}\n"

        output += "\n# HELP tradesync_opportunities_new New opportunities awaiting action\n"
        output += "# TYPE tradesync_opportunities_new gauge\n"
        output += f"tradesync_opportunities_new {app_metrics.get('opportunities_new', 0)}\n"

        output += "\n# HELP tradesync_decisions_total Total decisions made\n"
        output += "# TYPE tradesync_decisions_total gauge\n"
        output += f"tradesync_decisions_total {app_metrics.get('decisions_total', 0)}\n"

        output += "\n# HELP tradesync_exec_orders_total Total execution orders\n"
        output += "# TYPE tradesync_exec_orders_total gauge\n"
        output += f"tradesync_exec_orders_total {app_metrics.get('exec_orders_total', 0)}\n"

        output += "\n# HELP tradesync_exec_orders_placed Successfully placed orders\n"
        output += "# TYPE tradesync_exec_orders_placed gauge\n"
        output += f"tradesync_exec_orders_placed {app_metrics.get('exec_orders_placed', 0)}\n"

    return output

@app.get("/state/health", response_model=HealthResponse)
async def state_health():
    """Aggregated health check with component status and data freshness."""
    if not state.pool:
         raise HTTPException(status_code=503, detail="DB Pool not ready")
    
    t0 = time.time()
    try:
        async with state.pool.acquire() as conn:
            # Check DB + get latest timestamps in one go for efficiency
            row = await conn.fetchrow("""
                SELECT 
                    (SELECT ts FROM events ORDER BY ts DESC LIMIT 1) as last_evt,
                    (SELECT created_at FROM signals ORDER BY created_at DESC LIMIT 1) as last_sig
            """)
            
            latency = (time.time() - t0) * 1000
            
            return HealthResponse(
                status="healthy",
                postgres=True,
                last_event_ts=row['last_evt'] if row else None,
                last_signal_ts=row['last_sig'] if row else None,
                latency_ms=round(latency, 2)
            )
    except Exception as e:
        # Log error in real app
        print(f"Health check failed: {e}")
        return HealthResponse(
            status="degraded",
            postgres=False,
            last_event_ts=None,
            last_signal_ts=None,
            latency_ms=round((time.time() - t0) * 1000, 2)
        )

@app.get("/state/snapshot", response_model=SnapshotResponse)
async def get_state_snapshot():
    """Returns a high-level overview of system status.

    Never fails the entire response due to an optional upstream being unavailable.
    Returns partial data with explicit per-service health flags and error metadata.
    Critical section (postgres) is distinguished from optional upstreams.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    snapshot_ts = datetime.utcnow()
    errors: Dict[str, str] = {}
    service_health: Dict[str, Any] = {}

    # --- Critical section: DB timestamps ---
    latest_event_ts = None
    latest_signal_ts = None
    latest_opportunity_ts = None
    t0 = time.time()
    try:
        async with state.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    (SELECT ts FROM events ORDER BY ts DESC LIMIT 1) as last_evt,
                    (SELECT created_at FROM signals ORDER BY created_at DESC LIMIT 1) as last_sig,
                    (SELECT snapshot_ts FROM opportunities ORDER BY snapshot_ts DESC LIMIT 1) as last_opp
            """)
            if row:
                latest_event_ts = row['last_evt']
                latest_signal_ts = row['last_sig']
                latest_opportunity_ts = row['last_opp']
        service_health["postgres"] = {"ok": True, "latency_ms": round((time.time() - t0) * 1000, 2)}
    except Exception as e:
        err_msg = str(e)[:200]
        errors["postgres"] = err_msg
        service_health["postgres"] = {"ok": False, "latency_ms": round((time.time() - t0) * 1000, 2), "error": err_msg}
        logger.error(f"Snapshot: DB query failed: {err_msg}", extra={"trace_id": "snapshot"})

    # --- Optional section: upstream services ---
    drift_status = "error"
    hl_status = "error"
    drift_circuit = None
    hl_circuit = None
    ingest_sources = []

    async with httpx.AsyncClient() as client:
        # exec-drift-svc circuit status (optional)
        t0 = time.time()
        try:
            resp = await client.get("http://exec-drift-svc:8003/exec/drift/circuit-status", timeout=1.0)
            latency = round((time.time() - t0) * 1000, 2)
            if resp.status_code == 200:
                drift_circuit = resp.json()
                drift_status = "ok"
                service_health["exec-drift-svc"] = {"ok": True, "latency_ms": latency}
            else:
                err_msg = f"HTTP {resp.status_code}"
                errors["exec-drift-svc"] = err_msg
                service_health["exec-drift-svc"] = {"ok": False, "latency_ms": latency, "error": err_msg}
        except Exception as e:
            err_msg = str(e)[:200]
            errors["exec-drift-svc"] = err_msg
            service_health["exec-drift-svc"] = {"ok": False, "error": err_msg}

        # exec-hl-svc circuit status (optional)
        t0 = time.time()
        try:
            resp = await client.get("http://exec-hl-svc:8004/exec/hl/circuit-status", timeout=1.0)
            latency = round((time.time() - t0) * 1000, 2)
            if resp.status_code == 200:
                hl_circuit = resp.json()
                hl_status = "ok"
                service_health["exec-hl-svc"] = {"ok": True, "latency_ms": latency}
            else:
                err_msg = f"HTTP {resp.status_code}"
                errors["exec-hl-svc"] = err_msg
                service_health["exec-hl-svc"] = {"ok": False, "latency_ms": latency, "error": err_msg}
        except Exception as e:
            err_msg = str(e)[:200]
            errors["exec-hl-svc"] = err_msg
            service_health["exec-hl-svc"] = {"ok": False, "error": err_msg}

        # ingest-gateway sources (optional)
        t0 = time.time()
        try:
            resp = await client.get("http://ingest-gateway:8080/ingest/sources", timeout=1.0)
            latency = round((time.time() - t0) * 1000, 2)
            if resp.status_code == 200:
                raw = resp.json()
                ingest_sources = raw if isinstance(raw, list) else []
                service_health["ingest-gateway"] = {"ok": True, "latency_ms": latency}
            else:
                err_msg = f"HTTP {resp.status_code}"
                errors["ingest-gateway"] = err_msg
                service_health["ingest-gateway"] = {"ok": False, "latency_ms": latency, "error": err_msg}
        except Exception as e:
            err_msg = str(e)[:200]
            errors["ingest-gateway"] = err_msg
            service_health["ingest-gateway"] = {"ok": False, "error": err_msg}

    # --- Optional section: Redis stream lengths ---
    stream_lengths = {}
    t0 = time.time()
    try:
        r = await get_redis()
        for s in ["x:events.norm", "x:signals.funding"]:
            try:
                stream_lengths[s] = await r.xlen(s)
            except Exception as e:
                stream_lengths[s] = -1
                errors[f"redis.{s}"] = str(e)[:100]
        service_health["redis"] = {"ok": True, "latency_ms": round((time.time() - t0) * 1000, 2)}
    except Exception as e:
        err_msg = str(e)[:200]
        errors["redis"] = err_msg
        service_health["redis"] = {"ok": False, "error": err_msg}

    degraded = len(errors) > 0
    if degraded:
        logger.warning(
            f"Snapshot returned degraded state, unavailable services: {list(errors.keys())}",
            extra={"trace_id": "snapshot"}
        )

    return SnapshotResponse(
        latest_event_ts=latest_event_ts,
        latest_signal_ts=latest_signal_ts,
        latest_opportunity_ts=latest_opportunity_ts,
        execution_gate=os.getenv("EXECUTION_ENABLED", "false"),
        drift_status=drift_status,
        hl_status=hl_status,
        drift_circuit=drift_circuit,
        hl_circuit=hl_circuit,
        stream_lengths=stream_lengths,
        ingest_sources=ingest_sources,
        service_health=service_health,
        degraded=degraded,
        errors=errors,
        snapshot_ts=snapshot_ts,
    )

@app.get("/state/events/latest", response_model=List[EventResponse])
async def get_latest_events(
    request: Request,
    symbol: str, 
    tf: Optional[str] = None,
    timeframe: str = Query("1m"), 
    kind: str = "market_snapshot", 
    limit: int = Query(20, le=100)
):
    """Fetch latest events for a given symbol/tf/kind."""
    # Logic for tf vs timeframe
    params = request.query_params
    final_tf = timeframe
    if "tf" in params and "timeframe" not in params:
        final_tf = tf
    
    if final_tf not in VALID_TIMEFRAMES:
        final_tf = "1m" # Default back to 1m if invalid variant passed
        
    symbol = normalize_symbol(symbol)

    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, ts, source, kind, symbol, timeframe, payload
                FROM events
                WHERE symbol = $1 AND timeframe = $2 AND kind = $3
                ORDER BY ts DESC
                LIMIT $4
            """, symbol, final_tf, kind, limit)
            
            return [
                {
                    "id": str(r["id"]),
                    "ts": r["ts"],
                    "source": r["source"],
                    "kind": r["kind"],
                    "symbol": r["symbol"],
                    "timeframe": r["timeframe"],
                    "payload":  r["payload"]
                }
                for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/state/signals/latest", response_model=List[SignalResponse])
async def get_latest_signals(
    request: Request,
    symbol: str, 
    tf: Optional[str] = None,
    timeframe: str = Query("1m"), 
    kind: str = "funding_oi_squeeze",
    limit: int = Query(20, le=100)
):
    """Fetch latest signals for a given symbol/tf/kind."""
    params = request.query_params
    final_tf = timeframe
    if "tf" in params and "timeframe" not in params:
        final_tf = tf
    
    if final_tf not in VALID_TIMEFRAMES:
        final_tf = "1m"

    symbol = normalize_symbol(symbol)

    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, created_at, agent, symbol, timeframe, kind, confidence, dir, features
                FROM signals
                WHERE symbol = $1 AND timeframe = $2 AND kind = $3
                ORDER BY created_at DESC
                LIMIT $4
            """, symbol, final_tf, kind, limit)
            
            return [
                {
                    "id": str(r["id"]),
                    "created_at": r["created_at"],
                    "agent": r["agent"],
                    "symbol": r["symbol"],
                    "timeframe": r["timeframe"],
                    "kind": r["kind"],
                    "confidence": r["confidence"],
                    "dir": r["dir"],
                    "features": r["features"]
                }
                for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/state/opportunities", response_model=List[OpportunityResponse])
async def get_opportunities(
    symbol: Optional[str] = None, 
    status: str = "new",
    limit: int = Query(20, le=100)
):
    """Fetch opportunities."""
    if symbol:
        symbol = normalize_symbol(symbol)

    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    try:
        async with state.pool.acquire() as conn:
            if symbol:
                rows = await conn.fetch("""
                    SELECT id, symbol, timeframe, bias, quality, dir, status, snapshot_ts, expires_at, links, confluence
                    FROM opportunities
                    WHERE symbol = $1 AND status = $2
                    ORDER BY snapshot_ts DESC
                    LIMIT $3
                """, symbol, status, limit)
            else:
                rows = await conn.fetch("""
                    SELECT id, symbol, timeframe, bias, quality, dir, status, snapshot_ts, expires_at, links, confluence
                    FROM opportunities
                    WHERE status = $1
                    ORDER BY snapshot_ts DESC
                    LIMIT $2
                """, status, limit)

            return [
                {
                    "id": str(r["id"]),
                    "symbol": r["symbol"],
                    "timeframe": r["timeframe"],
                    "bias": r["bias"],
                    "quality": r["quality"],
                    "dir": r["dir"],
                    "status": r["status"],
                    "snapshot_ts": r["snapshot_ts"],
                    "expires_at": r["expires_at"],
                    "links": json.loads(r["links"]) if isinstance(r["links"], str) else r["links"],
                    # Phase 3C: Include confluence with score_breakdown, execution_risk, warnings
                    "confluence": json.loads(r["confluence"]) if isinstance(r["confluence"], str) else (r["confluence"] or {})
                }
                for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/state/evidence", response_model=EvidenceResponse)
async def get_evidence(opportunity_id: str):
    """Assembles all evidence for a given opportunity ID."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    try:
        async with state.pool.acquire() as conn:
            # 1. Fetch Opportunity
            opp_row = await conn.fetchrow("SELECT * FROM opportunities WHERE id = $1", opportunity_id)
            if not opp_row:
                return EvidenceResponse(opportunity=None)
            
            opportunity = {
                "id": str(opp_row["id"]),
                "symbol": opp_row["symbol"],
                "timeframe": opp_row["timeframe"],
                "bias": opp_row["bias"],
                "quality": opp_row["quality"],
                "dir": opp_row["dir"],
                "status": opp_row["status"],
                "snapshot_ts": opp_row["snapshot_ts"],
                "expires_at": opp_row.get("expires_at"),
                "links": json.loads(opp_row["links"]) if isinstance(opp_row["links"], str) else opp_row["links"],
                "confluence": json.loads(opp_row["confluence"]) if isinstance(opp_row.get("confluence"), str) else (opp_row.get("confluence") or {})
            }
            links = opportunity["links"] or {}
            
            # 2. Fetch Signals
            signal_ids = links.get("signal_id")
            signals = []
            if signal_ids:
                if not isinstance(signal_ids, list):
                    signal_ids = [signal_ids]
                sig_rows = await conn.fetch("SELECT * FROM signals WHERE id = ANY($1)", signal_ids)
                signals = [
                    {
                        "id": str(r["id"]), "created_at": r["created_at"], "agent": r["agent"],
                        "symbol": r["symbol"], "timeframe": r["timeframe"], "kind": r["kind"],
                        "confidence": r["confidence"], "dir": r["dir"],
                        "features": json.loads(r["features"]) if isinstance(r["features"], str) else r["features"]
                    } for r in sig_rows
                ]

            # 3. Fetch Events
            event_ids = links.get("event_ids", [])
            events = []
            if event_ids:
                evt_rows = await conn.fetch("SELECT * FROM events WHERE id = ANY($1)", event_ids)
                events = [
                    {
                        "id": str(r["id"]), "ts": r["ts"], "source": r["source"], "kind": r["kind"],
                        "symbol": r["symbol"], "timeframe": r["timeframe"],
                        "payload": json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
                    } for r in evt_rows
                ]

            # 4. Fetch Decisions
            dec_rows = await conn.fetch("SELECT * FROM decisions WHERE opportunity_id = $1", opportunity_id)
            decisions = [
                {
                    "id": str(r["id"]), "venue": r["venue"], 
                    "requested": json.loads(r["requested"]) if isinstance(r["requested"], str) else r["requested"],
                    "risk": json.loads(r["risk"]) if isinstance(r["risk"], str) else r["risk"]
                } for r in dec_rows
            ]

            # 5. Fetch Exec Orders
            decision_ids = [r["id"] for r in dec_rows]
            exec_orders = []
            if decision_ids:
                ord_rows = await conn.fetch("SELECT * FROM exec_orders WHERE decision_id = ANY($1)", decision_ids)
                exec_orders = [
                    {
                        "id": str(r["id"]), "decision_id": str(r["decision_id"]), "venue": r["venue"],
                        "status": r["status"], 
                        "request": json.loads(r["request"]) if isinstance(r["request"], str) else r["request"],
                        "response": json.loads(r["response"]) if isinstance(r["response"], str) else r["response"],
                        "dry_run": r["dry_run"]
                    } for r in ord_rows
                ]

            return EvidenceResponse(
                opportunity=opportunity,
                signals=signals,
                events=events,
                decisions=decisions,
                exec_orders=exec_orders
            )
    except Exception as e:
        print(f"Evidence error: {e}")
        return EvidenceResponse(opportunity=None) # Empty instead of 500

async def _fetch_aggregated_positions(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """
    Fetch and combine positions from all known exec services using one shared HTTP client.
    Partial results are returned on any upstream failure — unavailable services are excluded
    rather than failing the whole call.

    Used by both the /state/positions route and preview_action to ensure exposure calculations
    are always cross-venue. Callers must not assume all venues responded successfully.
    """
    tasks = [client.get(url, timeout=2.0) for url in _EXEC_POSITIONS_URLS.values()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    positions: List[Dict[str, Any]] = []
    for res in results:
        if not isinstance(res, Exception) and res.status_code == 200:
            positions.extend(res.json())
    return positions


@app.get("/state/positions", response_model=List[Position])
async def get_aggregated_positions(venue: str = "all"):
    """Aggregates positions from all execution services (or a specific venue)."""
    venue = normalize_venue(venue)
    async with httpx.AsyncClient() as client:
        if venue == "all":
            return await _fetch_aggregated_positions(client)
        url = _EXEC_POSITIONS_URLS.get(venue)
        if not url:
            return []
        try:
            resp = await client.get(url, timeout=2.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"Failed to fetch positions for {venue}: {e}")
        return []

@app.post("/actions/preview", response_model=PreviewResponse)
async def preview_action(req: PreviewRequest):
    """Generates an execution plan and validates it against risk rules."""
    req.venue = normalize_venue(req.venue)
    risk_engine = RiskGuardian()
    
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    try:
        async with state.pool.acquire() as conn:
            # 1. Fetch Opportunity
            row = await conn.fetchrow("SELECT * FROM opportunities WHERE id = $1", req.opportunity_id)
            if not row:
                raise HTTPException(status_code=404, detail="Opportunity not found")
            opportunity = dict(row)
            symbol = opportunity["symbol"]

            # 2. Idempotency Check: Existing Decision for this venue?
            existing_decision = await conn.fetchrow("""
                SELECT id, requested, risk FROM decisions WHERE opportunity_id = $1 AND venue = $2
            """, req.opportunity_id, req.venue)
            
            plan = {
                "action": "Market Order",
                "symbol": symbol,
                "size_usd": req.size_usd,
                "venue": req.venue,
                "slippage_tolerance": 0.01
            }

            if existing_decision:
                return PreviewResponse(
                    decision_id=str(existing_decision["id"]),
                    plan=json.loads(existing_decision["requested"]) if isinstance(existing_decision["requested"], str) else existing_decision["requested"],
                    risk_verdict=json.loads(existing_decision["risk"]) if isinstance(existing_decision["risk"], str) else existing_decision["risk"],
                    suggested_adjustments=None
                )

            # 3. Fetch Latest Signal for this symbol
            sig_row = await conn.fetchrow("""
                SELECT * FROM signals 
                WHERE symbol = $1 
                ORDER BY created_at DESC LIMIT 1
            """, symbol)
            latest_signal = dict(sig_row) if sig_row else None

            # 4. Check for existing decisions (count for cooldown/limit rules)
            recent_decisions = await conn.fetchval("""
                SELECT count(*) FROM decisions
                WHERE EXISTS (SELECT 1 FROM opportunities o WHERE o.id = decisions.opportunity_id AND o.symbol = $1)
            """, symbol)

            # 4c. Daily notional usage — sum of all orders placed today regardless of fill status.
            # Used to enforce DAILY_NOTIONAL_LIMIT at preview time.
            daily_notional_usd = await conn.fetchval("""
                SELECT COALESCE(SUM((request->>'size_usd')::float), 0.0)
                FROM exec_orders
                WHERE created_at >= CURRENT_DATE
            """) or 0.0

            # Phase 3C: 4b. Fetch microstructure data for risk assessment
            microstructure = None
            margin_utilization = 0.0
            symbol_exposure_usd = 0.0

            try:
                async with httpx.AsyncClient() as client:
                    # Fetch market snapshot with microstructure
                    market_resp = await client.get(
                        f"{MARKET_DATA_URL}/snapshot/{req.venue}/{symbol}",
                        timeout=2.0
                    )
                    if market_resp.status_code == 200:
                        market_data = market_resp.json()
                        if isinstance(market_data, dict):
                            microstructure = market_data.get("microstructure")

                    # Phase 3F-3: Fetch positions from ALL venues via canonical helper.
                    # Replaces the single-venue fetch from Phase 3F-2 — that version was
                    # blind to positions on other venues and overwrote rather than summed.
                    all_positions = await _fetch_aggregated_positions(client)
                    for pos in all_positions:
                        if pos.get("symbol") == symbol:
                            symbol_exposure_usd += abs(pos.get("size_usd", 0))
                    # Account risk load: fraction of configured capital deployed in open positions.
                    # Variable kept as margin_utilization for RiskGuardian interface compatibility,
                    # but this is NOT exchange margin — it is total_open_notional / ACCOUNT_EQUITY_USD.
                    total_position_usd = sum(abs(p.get("size_usd", 0)) for p in all_positions)
                    margin_utilization = total_position_usd / ACCOUNT_EQUITY_USD
            except Exception as e:
                logger.warning(f"Failed to fetch market/exposure data for risk check: {e}", extra={"trace_id": "preview"})

            # 5. Check Risk (Phase 3C: with microstructure + exposure data)
            verdict = risk_engine.check(
                symbol=symbol,
                size_usd=req.size_usd,
                opportunity=opportunity,
                latest_signal=latest_signal,
                recent_decisions_count=recent_decisions,
                microstructure=microstructure,
                margin_utilization=margin_utilization,
                symbol_exposure_usd=symbol_exposure_usd,
                account_equity=ACCOUNT_EQUITY_USD,
                daily_notional_usd=daily_notional_usd,
                daily_notional_limit=DAILY_NOTIONAL_LIMIT,
            )

            # Phase 3F-3: Non-transient rejection → write 'blocked' status.
            # Also stores the rejection reason in links.rejection so the cockpit can
            # surface why the opportunity was permanently blocked without a separate query.
            # Blocked rows are intentionally excluded from TTL expiry (see expire_stale_opportunities).
            if not verdict.allowed and verdict.reason_code in _NON_TRANSIENT_CODES:
                if opportunity.get("status") == "new":
                    rejection = json.dumps({
                        "reason_code": verdict.reason_code.value,
                        "reason": verdict.reason
                    })
                    await conn.execute(
                        """UPDATE opportunities
                           SET status = 'blocked',
                               links = jsonb_set(COALESCE(links, '{}'::jsonb), '{rejection}', $2::jsonb, true)
                           WHERE id = $1 AND status = 'new'""",
                        req.opportunity_id,
                        rejection
                    )
                return PreviewResponse(
                    decision_id=None,
                    plan=plan,
                    risk_verdict=verdict.model_dump(),
                    suggested_adjustments=verdict.suggested_adjustment
                )

            decision_id = None
            if verdict.allowed:
                # 6. Idempotent Decision Insert (Safety unique constraint)
                decision_id = await conn.fetchval("""
                    INSERT INTO decisions (opportunity_id, venue, requested, risk)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (opportunity_id, venue) DO NOTHING
                    RETURNING id
                """, req.opportunity_id, req.venue, json.dumps(plan), verdict.model_dump_json())

                if not decision_id:
                    decision_id = await conn.fetchval("""
                        SELECT id FROM decisions WHERE opportunity_id = $1 AND venue = $2
                    """, req.opportunity_id, req.venue)
                
                # 7. Update Status
                await conn.execute("""
                    UPDATE opportunities SET status = 'previewed' 
                    WHERE id = $1 AND status = 'new'
                """, req.opportunity_id)

            return PreviewResponse(
                decision_id=str(decision_id) if decision_id else None,
                plan=plan,
                risk_verdict=verdict.model_dump(),
                suggested_adjustments=verdict.suggested_adjustment
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Preview error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/state/execution/status")
async def get_execution_status():
    """Aggregates execution status and circuit breaker states from all venues."""
    venues = ["drift", "hyperliquid"]
    urls = {
        "drift": "http://exec-drift-svc:8003/exec/drift/circuit-status",
        "hyperliquid": "http://exec-hl-svc:8004/exec/hl/circuit-status"
    }
    
    status_report = []
    async with httpx.AsyncClient() as client:
        tasks = []
        for v in venues:
            tasks.append(client.get(urls[v], timeout=2.0))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, res in enumerate(results):
            venue_name = venues[i]
            if isinstance(res, httpx.Response) and res.status_code == 200:
                status_report.append(res.json())
            else:
                status_report.append({
                    "venue": venue_name,
                    "circuit_open": "unknown",
                    "error": str(res)
                })
                
    return {
        "execution_enabled": os.getenv("EXECUTION_ENABLED", "false"),
        "venues": status_report
    }

@app.get("/state/risk/limits", response_model=RiskLimitResponse)
async def get_risk_limits():
    """Returns the current risk policy and counters."""
    guardian = RiskGuardian()
    
    # Calculate current daily notional usage
    current_notional = 0.0
    if state.pool:
        try:
            async with state.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT COALESCE(SUM((request->>'size_usd')::float), 0.0) as total
                    FROM exec_orders
                    WHERE created_at >= CURRENT_DATE
                """)
                current_notional = row["total"] if row else 0.0
        except Exception as e:
            print(f"Error fetching daily notional: {e}")

    return RiskLimitResponse(
        max_leverage=guardian.max_leverage,
        min_quality=guardian.min_quality,
        max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "10")),
        min_size_usd=float(os.getenv("MIN_SIZE_USD", "10.0")),
        max_event_age=guardian.max_event_age,
        max_signal_age=guardian.max_signal_age,
        blacklist=guardian.blacklist,
        daily_notional_limit=DAILY_NOTIONAL_LIMIT,
        account_equity_usd=ACCOUNT_EQUITY_USD,
        current_counters={
            "daily_notional_usage": current_notional,
            "today_date": datetime.utcnow().date().isoformat()
        }
    )

@app.post("/admin/cleanup")
async def cleanup_old_opportunities(
    days: int = Query(30, ge=1, le=365),
    dry_run: bool = Query(True)
):
    """Delete old terminal opportunities (blocked/expired) older than N days.

    Cascades to decisions rows (decisions.opportunity_id has ON DELETE CASCADE).
    Only touches 'blocked' and 'expired' rows — never 'executed' or 'new'.

    Query params:
      days     — retention window in days (default 30, min 1, max 365)
      dry_run  — if true (default) returns count without deleting; set false to delete
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    async with state.pool.acquire() as conn:
        if dry_run:
            row = await conn.fetchrow("""
                SELECT COUNT(*) as count
                FROM opportunities
                WHERE status IN ('blocked', 'expired')
                  AND snapshot_ts < now() - make_interval(days => $1)
            """, days)
            return {"dry_run": True, "would_delete": int(row["count"]) if row else 0, "older_than_days": days}
        else:
            result = await conn.execute("""
                DELETE FROM opportunities
                WHERE status IN ('blocked', 'expired')
                  AND snapshot_ts < now() - make_interval(days => $1)
            """, days)
            count = int(result.split()[-1]) if result else 0
            return {"dry_run": False, "deleted": count, "older_than_days": days}


@app.post("/actions/execute", response_model=ExecutionResult)
async def execute_action(req: ExecuteRequest):
    """Executes a decision (Routes to venue microservice)."""
    if not req.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required")
        
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
        
    try:
        async with state.pool.acquire() as conn:
            # 1. Idempotency Check (Simplified: check if decision already has an order)
            existing_order = await conn.fetchrow("""
                SELECT response FROM exec_orders WHERE decision_id = $1
            """, req.decision_id)
            if existing_order:
                # Return the previously stored standardized response
                return ExecutionResult(**json.loads(existing_order["response"]))

            # 2. Re-validate Decision & Risk
            dec_row = await conn.fetchrow("""
                SELECT d.*, o.symbol, o.status as opp_status, o.quality, o.expires_at 
                FROM decisions d
                JOIN opportunities o ON d.opportunity_id = o.id
                WHERE d.id = $1
            """, req.decision_id)
            
            if not dec_row:
                raise HTTPException(status_code=404, detail="Decision not found")

            # FETCH Risk verdict again or use stored? Prompt says "Always return the same shape".
            # If rejected by risk now, we should still return an ExecutionResult.
            
            sig_row = await conn.fetchrow("""
                SELECT * FROM signals WHERE symbol = $1 ORDER BY created_at DESC LIMIT 1
            """, dec_row["symbol"])

            risk_engine = RiskGuardian()
            opp_for_risk = {
                "status": dec_row["opp_status"],
                "quality": dec_row["quality"],
                "expires_at": dec_row["expires_at"]
            }
            
            requested_data = json.loads(dec_row["requested"]) if isinstance(dec_row["requested"], str) else dec_row["requested"]
            verdict = risk_engine.check(
                symbol=dec_row["symbol"],
                size_usd=requested_data["size_usd"],
                opportunity=opp_for_risk,
                latest_signal=dict(sig_row) if sig_row else None,
                phase="execute"
            )

            if not verdict.allowed:
                # Return standard ExecutionResult for Risk Rejection
                return ExecutionResult(
                    ok=False,
                    venue=dec_row["venue"],
                    dry_run=False, # Risk check phase
                    execution_enabled=True,
                    status="rejected",
                    idempotency_key=str(req.decision_id),
                    request_payload=requested_data,
                    response_payload={},
                    error=ExecutionError(code="RISK_REJECTION", message=verdict.reason),
                    ts=datetime.utcnow().isoformat()
                )

            # 3. Venue Routing
            venue = dec_row["venue"]
            exec_result = None
            
            exec_url_map = {
                "drift": "http://exec-drift-svc:8003/exec/drift/order",
                "hyperliquid": "http://exec-hl-svc:8004/exec/hl/order"
            }
            
            if venue not in exec_url_map:
                 raise HTTPException(status_code=400, detail=f"Unsupported venue: {venue}")

            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.post(
                        exec_url_map[venue],
                        json={
                            "symbol": dec_row["symbol"],
                            "side": "buy",
                            "order_type": "market",
                            "size_usd": requested_data["size_usd"],
                            "venue": venue,
                            "idempotency_key": req.decision_id
                        },
                        timeout=5.0
                    )
                    if resp.status_code == 200:
                        exec_result = ExecutionResult(**resp.json())
                    else:
                        # Handle non-200 from exec svc
                        exec_result = ExecutionResult(
                            ok=False,
                            venue=venue,
                            dry_run=False,
                            execution_enabled=True,
                            status="error",
                            idempotency_key=str(req.decision_id),
                            request_payload=requested_data,
                            response_payload={"http_status": resp.status_code, "body": resp.text},
                            error=ExecutionError(code="RPC_FAIL", message=f"Venue service returned {resp.status_code}"),
                            ts=datetime.utcnow().isoformat()
                        )
                except Exception as e:
                    exec_result = ExecutionResult(
                        ok=False,
                        venue=venue,
                        dry_run=False,
                        execution_enabled=True,
                        status="error",
                        idempotency_key=str(req.decision_id),
                        request_payload=requested_data,
                        response_payload={},
                        error=ExecutionError(code="UNKNOWN", message=str(e)),
                        ts=datetime.utcnow().isoformat()
                    )

            # 4. Persist Execution Order
            order_id = exec_result.order_id or str(uuid.uuid4())
            
            await conn.execute("""
                INSERT INTO exec_orders (
                    id, decision_id, venue, request, response, status, dry_run
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7
                )
            """, order_id, req.decision_id, venue,
                 json.dumps(dec_row["requested"]) if isinstance(dec_row["requested"], dict) else dec_row["requested"], 
                 exec_result.model_dump_json(),
                 exec_result.status,
                 exec_result.dry_run
            )

            if exec_result.ok and exec_result.status == "placed":
                await conn.execute("""
                    UPDATE opportunities SET status = 'executed' 
                    WHERE id = $1
                """, dec_row["opportunity_id"])

            return exec_result

    except HTTPException:
        raise
    except Exception as e:
        print(f"Execution error: {e}")
        # Final fallback for unexpected errors
        return ExecutionResult(
            ok=False,
            venue="unknown",
            dry_run=False,
            execution_enabled=False,
            status="error",
            idempotency_key="unknown",
            request_payload={},
            response_payload={},
            error=ExecutionError(code="UNKNOWN", message=str(e)),
            ts=datetime.utcnow().isoformat()
        )

# --- Market Data Endpoints (Phase 3B) ---

MARKET_DATA_URL = os.getenv("MARKET_DATA_URL", "http://market-data:8005")
KNOWN_VENUES = [v.strip() for v in os.getenv("KNOWN_VENUES", "drift,hyperliquid").split(",")]

class MarketSnapshotResponse(BaseModel):
    """Market snapshot with truthfulness indicators — always single venue/symbol."""
    venue: str
    symbol: str
    scope: str = "single_venue"  # Explicit: this is never an all-venues aggregate
    ts: int
    data_age_ms: int
    available_metrics: List[Dict[str, Any]]
    funding: Optional[Dict[str, Any]] = None
    oi: Optional[Dict[str, Any]] = None
    liquidations: Optional[Dict[str, Any]] = None
    volume: Optional[Dict[str, Any]] = None
    orderbook: Optional[Dict[str, Any]] = None
    # Phase 3C: Derived microstructure data
    microstructure: Optional[Dict[str, Any]] = None
    regimes: Dict[str, Any]
    sources: List[Dict[str, Any]] = []


# --- Market Aggregate Models ---

class VenueAvailability(BaseModel):
    venue: str
    available: bool
    data_age_ms: Optional[int] = None
    error: Optional[str] = None


class OIAggregate(BaseModel):
    """OI aggregate across venues. total_usd only reflects contributing_venues."""
    total_usd: float
    per_venue: Dict[str, Optional[float]]          # venue -> current_usd or None
    contributing_venues: List[str]                  # Venues included in total_usd
    missing_venues: List[str]                       # Venues excluded (unavailable/no data)
    regime_per_venue: Dict[str, Optional[str]]      # venue -> OI regime string or None


class FundingAggregate(BaseModel):
    """Funding rates per venue. Spread is only valid when exactly 2 venues contribute."""
    per_venue: Dict[str, Optional[float]]           # venue -> funding rate now (decimal) or None
    spread: Optional[float] = None                  # Absolute spread in BPS; None if < 2 venues
    available_venues: List[str]
    missing_venues: List[str]


class MarketAggregateResponse(BaseModel):
    """All-venues aggregate for a symbol. Always scope='all_venues'."""
    symbol: str
    scope: str = "all_venues"
    aggregate_ts: str                               # ISO UTC datetime when aggregated
    partial: bool                                   # True if any known venue was unavailable
    venue_availability: List[VenueAvailability]
    oi: OIAggregate
    funding: FundingAggregate
    per_venue: Dict[str, Optional[Dict[str, Any]]]  # Full per-venue snapshot or None
    notes: List[str] = []                           # Human-readable transparency notes

class MarketAlertResponse(BaseModel):
    """Market alert for regime changes."""
    id: str
    venue: str
    symbol: str
    ts: int
    alert_type: str
    metric: str
    previous_value: Optional[str] = None
    new_value: str
    context: Dict[str, Any] = {}

@app.get("/state/market/snapshot", response_model=MarketSnapshotResponse)
async def get_market_snapshot(venue: str, symbol: str):
    """
    Get latest market snapshot for venue/symbol.

    Returns truthful market data with available_metrics[] showing
    REAL/PROXY/UNAVAILABLE status for each metric.
    """
    symbol = normalize_symbol(symbol)
    venue = normalize_venue(venue)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{MARKET_DATA_URL}/snapshot/{venue}/{symbol}",
                timeout=5.0
            )
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"No snapshot for {venue}:{symbol}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except Exception as e:
            logger.error(f"Error fetching market snapshot: {e}", extra={"trace_id": "market"})
            raise HTTPException(status_code=503, detail="Market data service unavailable")

@app.get("/state/market/snapshots")
async def get_all_market_snapshots():
    """Get all current market snapshots."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{MARKET_DATA_URL}/snapshots", timeout=5.0)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error fetching market snapshots: {e}", extra={"trace_id": "market"})
            raise HTTPException(status_code=503, detail="Market data service unavailable")

@app.get("/state/market/timeseries")
async def get_market_timeseries(
    venue: str,
    symbol: str,
    metric: str = "funding",
    window: str = "1h"
):
    """
    Get rolling timeseries data for a metric.

    Useful for sparklines and charts.
    """
    symbol = normalize_symbol(symbol)
    venue = normalize_venue(venue)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{MARKET_DATA_URL}/timeseries/{venue}/{symbol}/{metric}",
                params={"window": window},
                timeout=5.0
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error fetching market timeseries: {e}", extra={"trace_id": "market"})
            raise HTTPException(status_code=503, detail="Market data service unavailable")

@app.get("/state/market/alerts", response_model=List[MarketAlertResponse])
async def get_market_alerts(limit: int = 50):
    """
    Get recent market alerts (regime changes, extreme values).

    These appear in the /logs page.
    """
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{MARKET_DATA_URL}/alerts",
                params={"limit": limit},
                timeout=5.0
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("alerts", [])
        except Exception as e:
            logger.error(f"Error fetching market alerts: {e}", extra={"trace_id": "market"})
            raise HTTPException(status_code=503, detail="Market data service unavailable")

@app.get("/state/market/status")
async def get_market_data_status():
    """Get status of market data service and providers."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{MARKET_DATA_URL}/status", timeout=5.0)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error fetching market status: {e}", extra={"trace_id": "market"})
            return {
                "status": "unavailable",
                "error": str(e),
                "providers": []
            }


@app.get("/state/market/aggregate/{symbol}", response_model=MarketAggregateResponse)
async def get_market_aggregate(symbol: str):
    """All-venues aggregate market metrics for a symbol.

    Normalization rules (documented, not implied):
    - OI: oi.current_usd is always USD-notional (market-data normalizer converts asset units).
      total_usd is the sum across contributing_venues only. Never imputed for missing venues.
    - Funding: per-venue decimal rate (e.g., 0.0001 = 0.01% per 8h). Not averaged across venues
      because venues are independent markets. Spread in BPS returned only when exactly 2 venues
      have live data.
    - OI delta windows: exposed per-venue via per_venue[venue].oi.horizons — not re-aggregated here.
    - Regimes: per-venue from each snapshot; no cross-venue regime synthesized at this layer.

    Truthfulness guarantees:
    - scope is always "all_venues"
    - partial=True whenever any known venue was unavailable
    - oi.total_usd only reflects contributing_venues — not an all-venues number if partial
    - funding.spread is None unless exactly 2 venues provided a live rate
    - per_venue always has an entry for every KNOWN_VENUE (None if unavailable)
    """
    symbol = normalize_symbol(symbol)
    per_venue: Dict[str, Optional[Dict[str, Any]]] = {}
    venue_availability: List[VenueAvailability] = []
    notes: List[str] = []

    async with httpx.AsyncClient() as client:
        for venue in KNOWN_VENUES:
            t0 = time.time()
            try:
                resp = await client.get(
                    f"{MARKET_DATA_URL}/snapshot/{venue}/{symbol}",
                    timeout=3.0
                )
                latency_ms = round((time.time() - t0) * 1000, 2)
                if resp.status_code == 200:
                    snap = resp.json()
                    per_venue[venue] = snap
                    venue_availability.append(VenueAvailability(
                        venue=venue,
                        available=True,
                        data_age_ms=snap.get("data_age_ms"),
                    ))
                elif resp.status_code == 404:
                    per_venue[venue] = None
                    venue_availability.append(VenueAvailability(
                        venue=venue,
                        available=False,
                        error="no_snapshot",
                    ))
                    notes.append(f"{venue}: no snapshot available for {symbol}")
                else:
                    per_venue[venue] = None
                    venue_availability.append(VenueAvailability(
                        venue=venue,
                        available=False,
                        error=f"HTTP {resp.status_code}",
                    ))
            except Exception as e:
                per_venue[venue] = None
                err_msg = str(e)[:100]
                venue_availability.append(VenueAvailability(
                    venue=venue,
                    available=False,
                    error=err_msg,
                ))
                notes.append(f"{venue}: unavailable — {err_msg}")

    # --- Aggregate: OI ---
    # Rule: sum current_usd from venues where data is present and non-null.
    # Do not impute or estimate missing venues.
    oi_per_venue: Dict[str, Optional[float]] = {}
    oi_regime_per_venue: Dict[str, Optional[str]] = {}
    contributing_oi: List[str] = []
    missing_oi: List[str] = []
    total_oi_usd = 0.0

    for venue in KNOWN_VENUES:
        snap = per_venue.get(venue)
        if snap and snap.get("oi") and snap["oi"].get("current_usd") is not None:
            val = float(snap["oi"]["current_usd"])
            oi_per_venue[venue] = val
            oi_regime_per_venue[venue] = snap["oi"].get("regime")
            total_oi_usd += val
            contributing_oi.append(venue)
        else:
            oi_per_venue[venue] = None
            oi_regime_per_venue[venue] = None
            missing_oi.append(venue)

    if missing_oi:
        notes.append(
            f"OI aggregate is partial: contributing={contributing_oi}, missing={missing_oi}"
        )

    # --- Aggregate: Funding ---
    # Rule: per-venue current rate only. No cross-venue average.
    # Spread = abs difference in BPS, only when exactly 2 venues have live data.
    funding_per_venue: Dict[str, Optional[float]] = {}
    available_funding: List[str] = []
    missing_funding: List[str] = []

    for venue in KNOWN_VENUES:
        snap = per_venue.get(venue)
        rate = None
        if snap and snap.get("funding"):
            horizons = snap["funding"].get("horizons") or {}
            rate = horizons.get("now")
        funding_per_venue[venue] = rate
        if rate is not None:
            available_funding.append(venue)
        else:
            missing_funding.append(venue)

    funding_spread: Optional[float] = None
    if len(available_funding) == 2:
        rates = [funding_per_venue[v] for v in available_funding]
        funding_spread = round(abs(rates[0] - rates[1]) * 10000, 4)
    elif len(available_funding) < 2:
        notes.append(
            f"Funding spread unavailable: need 2 venues with data, "
            f"have {len(available_funding)} ({available_funding})"
        )

    partial = any(not va.available for va in venue_availability)

    return MarketAggregateResponse(
        symbol=symbol,
        scope="all_venues",
        aggregate_ts=datetime.utcnow().isoformat(),
        partial=partial,
        venue_availability=venue_availability,
        oi=OIAggregate(
            total_usd=total_oi_usd,
            per_venue=oi_per_venue,
            contributing_venues=contributing_oi,
            missing_venues=missing_oi,
            regime_per_venue=oi_regime_per_venue,
        ),
        funding=FundingAggregate(
            per_venue=funding_per_venue,
            spread=funding_spread,
            available_venues=available_funding,
            missing_venues=missing_funding,
        ),
        per_venue=per_venue,
        notes=notes,
    )


# --- Phase 3C: Macro Feed Endpoints ---

class MacroHeadlineResponse(BaseModel):
    title: str
    source: str
    category: str
    url: str
    published_at: Optional[str] = None
    summary: Optional[str] = None
    sentiment: Optional[str] = None

class MacroFeedResponse(BaseModel):
    headlines: List[MacroHeadlineResponse]
    status: Dict[str, Any]
    cached: bool
    ts: str

@app.get("/state/macro/headlines", response_model=MacroFeedResponse, tags=["macro"])
async def get_macro_headlines(
    refresh: bool = Query(False, description="Force refresh from sources"),
    limit: int = Query(20, le=50, description="Max headlines to return"),
    category: Optional[str] = Query(None, description="Filter by category (crypto, macro)")
):
    """
    Get macro news headlines from RSS feeds.

    Phase 3C MVP: Simple RSS aggregation for trading context.
    """
    try:
        headlines = await macro_feed.fetch_headlines(force_refresh=refresh)

        # Filter by category if specified
        if category:
            headlines = [h for h in headlines if h.category == category]

        # Apply limit
        headlines = headlines[:limit]

        return MacroFeedResponse(
            headlines=[MacroHeadlineResponse(**h.to_dict()) for h in headlines],
            status=macro_feed.get_status(),
            cached=not refresh,
            ts=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Error fetching macro headlines: {e}", extra={"trace_id": "macro"})
        return MacroFeedResponse(
            headlines=[],
            status={"error": str(e), **macro_feed.get_status()},
            cached=False,
            ts=datetime.now(timezone.utc).isoformat()
        )

@app.get("/state/macro/status", tags=["macro"])
async def get_macro_status():
    """Get macro feed service status."""
    return macro_feed.get_status()

# --- Legacy Aliases (Step 0 Compat) ---

@app.get("/opps", response_model=List[OpportunityResponse], tags=["legacy"])
async def get_opportunities_alias(
    response: Response,
    symbol: Optional[str] = None, 
    status: str = "new", 
    limit: int = Query(20, le=100)
):
    apply_deprecation_headers(response, "/state/opportunities")
    return await get_opportunities(symbol=symbol, status=status, limit=limit)

@app.get("/opps/{opportunity_id}", response_model=EvidenceResponse, tags=["legacy"])
async def get_opportunity_by_id_alias(response: Response, opportunity_id: str):
    apply_deprecation_headers(response, f"/state/evidence?opportunity_id={opportunity_id}")
    return await get_evidence(opportunity_id=opportunity_id)

@app.post("/preview", response_model=PreviewResponse, tags=["legacy"])
async def preview_action_alias(response: Response, req: PreviewRequest):
    apply_deprecation_headers(response, "/actions/preview")
    return await preview_action(req)

@app.post("/execute", response_model=ExecutionResult, tags=["legacy"])
async def execute_action_alias(response: Response, req: ExecuteRequest):
    apply_deprecation_headers(response, "/actions/execute")
    return await execute_action(req)

@app.get("/execution/status", tags=["legacy"])
async def get_execution_status_alias(response: Response):
    apply_deprecation_headers(response, "/state/execution/status")
    return await get_execution_status()
