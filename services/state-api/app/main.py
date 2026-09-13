import os
import re
import json
import math
import uuid
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import asyncpg
import redis.asyncio as redis
import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field
from tradesync_core import RiskGuardian
from tradesync_core import normalize_symbol, normalize_venue
from tradesync_core.paper_signal import AdmissionPolicy
from tradesync_core.regime_weights import RulebookValidationError, validate_rulebook
from tradesync_core.quarantine import (
    content_digest,
    QuarantineError,
    evaluate_submission,
    promotion_blockers,
)
from tradesync_core.canvas_drawings import (
    DrawingError,
    next_version,
    validate_drawing,
)
from tradesync_core.state_history import annotate_node, detect_transitions
from tradesync_core.tradingview_webhook import parse_alert
from tradesync_core.replay import (
    ReplayError,
    case_from_stored_evidence,
    compare_rulebooks,
)
from app.macro_feed import macro_feed, MacroHeadline
from app.context_feed import context_feed
from tradesync_core.agent_harness import HarnessError
from tradesync_core.reconciliation import reconcile
from tradesync_core.timeparse import parse_utc
from tradesync_core.control_envelope import (
    CLOSED_AUTHORITY,
    ControlEnvelopeError,
    build_paper_control_envelope,
)
from tradesync_core.strike_zone import (
    ReceiptError,
    to_trade_candidate,
    validate_receipt,
)
from tradesync_core.graph_snapshot import SnapshotRejected
from app import agent_connector
from app.graph_projection import (
    available_snapshots,
    current_snapshot,
    neighbours,
    project_snapshot,
    read_snapshot,
    snapshot_directory,
)
from app.integration_pipeline import collect_integration_pipeline
from app.regime_lab import (
    RegimeLabEngine,
    RegimeLabValidationError,
    collect_live_feature_results,
    persist_experiment,
)

# --- Logging Setup ---
class DefaultTraceIdFilter(logging.Filter):
    """Supply a safe trace field for dependency and server log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] trace_id=%(trace_id)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
for handler in logging.getLogger().handlers:
    handler.addFilter(DefaultTraceIdFilter())
# httpx logs every request URL at INFO. FRED accepts its API key only as a
# query parameter, so that line would carry the key into the container log.
# Seen once on 2026-09-12 and closed here: no outbound URL is logged at all.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
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
VALID_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "1d"]
regime_lab_engine = RegimeLabEngine()

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
    hl_status: str
    hl_circuit: Optional[Dict[str, Any]] = None
    stream_lengths: Dict[str, int] = {}
    ingest_sources: List[Dict[str, Any]] = []

class RiskLimitResponse(BaseModel):
    max_leverage: float
    min_quality: float
    max_open_positions: int
    min_size_usd: float
    max_event_age: int
    max_signal_age: int
    blacklist: List[str]
    daily_notional_limit: float
    current_counters: Dict[str, Any]

class PreviewRequest(BaseModel):
    opportunity_id: str
    size_usd: float = 1000.0
    venue: str = "hyperliquid"

class PreviewResponse(BaseModel):
    decision_id: Optional[str] = None
    plan: Dict[str, Any]
    risk_verdict: Dict[str, Any]
    suggested_adjustments: Optional[Dict[str, Any]] = None

class ExecuteRequest(BaseModel):
    decision_id: str
    confirm: bool

class RegimeLabExperimentRequest(BaseModel):
    name: str = Field(default="Local paper challenger", min_length=3, max_length=120)
    version: str = Field(min_length=1, max_length=40)
    hypothesis: str = Field(min_length=20, max_length=800)
    evaluation_window: str = Field(
        default="current_evidence_snapshot", min_length=3, max_length=120
    )
    expected_effect: str = Field(default="uncertain", max_length=80)
    weights: Dict[str, float]
    arithmetic_answer: float
    reflection: str = Field(min_length=1, max_length=1200)
    risk_flags: List[str] = Field(default_factory=list)

# ExecutionResult is used as the response model for execute_action

# --- Lifespan & State ---
class AppState:
    pool: asyncpg.Pool = None

state = AppState()

async def _warm_macro_cache() -> None:
    """Populate the macro cache once, at startup, without blocking readiness."""
    try:
        await macro_feed.fetch_headlines()
        logger.info(
            f"Macro cache warmed: {len(macro_feed.cache)} headlines",
            extra={"trace_id": "startup"},
        )
    except Exception as exc:
        logger.warning(
            f"Macro cache warm failed; the feed will be fetched on first read: {exc}",
            extra={"trace_id": "startup"},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        print(f"Connecting to DB pool: min={POOL_MIN_SIZE} max={POOL_MAX_SIZE}")
        try:
            state.pool = await asyncpg.create_pool(
                dsn=PG_DSN,
                min_size=POOL_MIN_SIZE,
                max_size=POOL_MAX_SIZE,
                command_timeout=POOL_TIMEOUT
            )
        except Exception as exc:
            if os.getenv("STATE_API_DEGRADED_START", "false").lower() != "true":
                raise
            state.pool = None
            logger.warning(
                f"Starting without PostgreSQL for bounded read-only/development surfaces: {exc}",
                extra={"trace_id": "startup"},
            )
        # Warm the macro cache behind startup rather than making the first
        # caller pay for it. Three external RSS feeds take ~17s cold, and
        # stale-while-revalidate only helps once there is something to serve;
        # the very first request after a restart would otherwise still block.
        #
        # Deliberately not awaited: the API must come up whether or not a news
        # feed answers, and a failure here is logged, not fatal.
        asyncio.create_task(_warm_macro_cache())

        yield
    finally:
        # Shutdown
        await macro_feed.close()
        await context_feed.close()
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
    """Returns a high-level overview of system status."""
    if not state.pool:
         raise HTTPException(status_code=503, detail="DB Pool not ready")
    
    try:
        r = await get_redis()
        async with state.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    (SELECT ts FROM events ORDER BY ts DESC LIMIT 1) as last_evt,
                    (SELECT created_at FROM signals ORDER BY created_at DESC LIMIT 1) as last_sig,
                    (SELECT snapshot_ts FROM opportunities ORDER BY snapshot_ts DESC LIMIT 1) as last_opp
            """)
            
            # Check execution services health + circuit
            hl_status = "error"
            hl_circuit = None
            ingest_sources = []
            
            async with httpx.AsyncClient() as client:
                
                try:
                    resp = await client.get("http://exec-hl-svc:8004/exec/hl/circuit-status", timeout=1.0)
                    if resp.status_code == 200:
                        hl_circuit = resp.json()
                        hl_status = "ok"
                except Exception:
                    pass
                
                try:
                    resp = await client.get("http://ingest-gateway:8080/ingest/sources", timeout=1.0)
                    if resp.status_code == 200:
                        ingest_sources = resp.json()
                except Exception:
                    pass
            
            # Stream lengths
            stream_lengths = {}
            for s in ["x:events.norm", "x:signals.funding"]:
                try:
                    stream_lengths[s] = await r.xlen(s)
                except Exception:
                    stream_lengths[s] = -1

            return SnapshotResponse(
                latest_event_ts=row['last_evt'] if row else None,
                latest_signal_ts=row['last_sig'] if row else None,
                latest_opportunity_ts=row['last_opp'] if row else None,
                execution_gate=os.getenv("EXECUTION_ENABLED", "false"),
                hl_status=hl_status,
                hl_circuit=hl_circuit,
                stream_lengths=stream_lengths,
                ingest_sources=ingest_sources
            )
    except Exception as e:
        print(f"Snapshot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

    # "all" is a wildcard, not a stored status. Comparing it literally matched
    # no row and silently returned an empty list, which the Cockpit rendered as
    # "no scored opportunities available" even when opportunities existed.
    filters = []
    params: list = []
    if symbol:
        params.append(symbol)
        filters.append(f"symbol = ${len(params)}")
    if status and status.lower() != "all":
        params.append(status)
        filters.append(f"status = ${len(params)}")
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(limit)

    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                    SELECT id, symbol, timeframe, bias, quality, dir, status, snapshot_ts, links, confluence
                    FROM opportunities
                    {where}
                    ORDER BY snapshot_ts DESC
                    LIMIT ${len(params)}
                """,
                *params,
            )

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
                "links": json.loads(opp_row["links"]) if isinstance(opp_row["links"], str) else opp_row["links"]
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

@app.get("/state/positions", response_model=List[Position])
async def get_aggregated_positions(venue: str = "all"):
    """Aggregates positions from execution services."""
    venue = normalize_venue(venue)
    venues = ["hyperliquid"] if venue == "all" else [venue]
    urls = {
        "hyperliquid": "http://exec-hl-svc:8004/exec/hl/positions"
    }
    
    all_positions = []
    async with httpx.AsyncClient() as client:
        tasks = []
        for v in venues:
            if v in urls:
                tasks.append(client.get(urls[v], timeout=2.0))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, httpx.Response) and res.status_code == 200:
                all_positions.extend(res.json())
            else:
                print(f"Failed to fetch positions: {res}")
                
    return all_positions

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
                        microstructure = market_data.get("microstructure")

                    # Fetch current exposure (if available)
                    exposure_resp = await client.get(
                        "http://exec-hl-svc:8004/exec/hl/positions",
                        timeout=2.0
                    )
                    if exposure_resp.status_code == 200:
                        positions = exposure_resp.json()
                        for pos in positions:
                            if pos.get("symbol") == symbol:
                                symbol_exposure_usd = abs(pos.get("notional", 0))
                        # Rough margin utilization (simplified)
                        total_notional = sum(abs(p.get("notional", 0)) for p in positions)
                        margin_utilization = total_notional / 50000.0  # Assuming $50k account
            except Exception as e:
                logger.warning(f"Failed to fetch market/exposure data for risk check: {e}", extra={"trace_id": "preview"})

            # 5. Check Risk (Phase 3C: with microstructure data)
            verdict = risk_engine.check(
                symbol=symbol,
                size_usd=req.size_usd,
                opportunity=opportunity,
                latest_signal=latest_signal,
                recent_decisions_count=recent_decisions,
                microstructure=microstructure,
                margin_utilization=margin_utilization,
                symbol_exposure_usd=symbol_exposure_usd
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

def execution_gate_enabled() -> bool:
    """Whether the global execution gate is actually open.

    Read rather than assumed: three rejection paths previously reported
    `execution_enabled: True` from a literal while `EXECUTION_ENABLED` was
    false, which is precisely the kind of untruthful status this system exists
    to avoid.
    """
    return os.getenv("EXECUTION_ENABLED", "false").strip().lower() == "true"


def paper_mode_enabled() -> bool:
    """Whether the system is in paper mode. Defaults to true, like the boundary.

    Used on paths where nothing was ever sent to a venue — a risk rejection, an
    RPC failure. Those reported `dry_run: False` from a literal, which asserts
    "this was a live action" about a request that never left the building. It is
    the same untruthful-status defect as `execution_enabled` above, one level
    down, and it reads far worse: a consumer seeing `dry_run: false` would
    reasonably conclude the system is live.

    Same variable and same fail-safe default as `exec-hl-svc`, so the two cannot
    disagree about which mode the system is in.
    """
    return os.getenv("DRY_RUN", "true").strip().lower() == "true"


@app.get("/state/execution/status")
async def get_execution_status():
    """Aggregates execution status and circuit breaker states from all venues."""
    venues = ["hyperliquid"]
    urls = {
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
                    SELECT SUM((request->>'size_usd')::float) as total
                    FROM exec_orders
                    WHERE status = 'placed' 
                    AND created_at >= CURRENT_DATE
                """)
                current_notional = row["total"] or 0.0
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
        daily_notional_limit=float(os.getenv("DAILY_NOTIONAL_LIMIT", "50000.0")),
        current_counters={
            "daily_notional_usage": current_notional,
            "today_date": datetime.utcnow().date().isoformat()
        }
    )

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
                SELECT d.*, o.symbol, o.status as opp_status, o.quality, o.expires_at, o.dir
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
                    # Nothing was sent to a venue: report the configured mode,
                    # not a literal claiming this was a live action.
                    dry_run=paper_mode_enabled(),
                    execution_enabled=execution_gate_enabled(),
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
            direction = str(dec_row["dir"]).lower()
            side_by_direction = {"long": "buy", "buy": "buy", "short": "sell", "sell": "sell"}
            order_side = side_by_direction.get(direction)
            if order_side is None:
                raise HTTPException(status_code=400, detail=f"Unsupported opportunity direction: {direction}")

            exec_url_map = {
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
                            "side": order_side,
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
                            dry_run=paper_mode_enabled(),
                            execution_enabled=execution_gate_enabled(),
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
                        dry_run=paper_mode_enabled(),
                        execution_enabled=execution_gate_enabled(),
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
# The paper execution boundary. Outside the bounded profile by default;
# probing it is how the preflight reports what the venue side thinks.
EXEC_HL_URL = os.getenv("EXEC_HL_URL", "http://exec-hl-svc:8004")
SIGNER_URL = os.getenv("SIGNER_URL", "http://signer-svc:8006")
# The account to preview. An address is public — it appears in every
# transaction the account has ever made — so this is not a secret and is not
# treated as one. The key that controls it never appears in this service.
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "").strip()
# The venue's public info endpoint. Read-only by construction: it takes an
# address and returns state, and has no authenticated surface at all.
HYPERLIQUID_INFO_URL = os.getenv(
    "HYPERLIQUID_INFO_URL", "https://api.hyperliquid.xyz/info"
)


def _market_data_get(path: str, *, timeout: float = 10.0) -> httpx.Response:
    """Fetch an internal market-data route without blocking the API worker."""

    with httpx.Client(timeout=timeout, trust_env=False) as client:
        return client.get(f"{MARKET_DATA_URL}{path}")


class MarketSnapshotResponse(BaseModel):
    """Market snapshot with truthfulness indicators."""
    venue: str
    symbol: str
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
    try:
        # Keep the internal proxy off the main event loop: the legacy dashboard
        # polls several slower routes concurrently and must not create a false
        # market-data outage.
        resp = await asyncio.to_thread(_market_data_get, "/snapshots")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error fetching market snapshots: {e}", extra={"trace_id": "market"})
        raise HTTPException(status_code=503, detail="Market data service unavailable")

class ReplayRequest(BaseModel):
    """A frozen-window replay request. Weights must form a valid rulebook."""

    hours: int = Field(24, ge=1, le=720)
    symbol: Optional[str] = None
    horizon_minutes: int = Field(60, ge=1)
    challenger_weights: Optional[Dict[str, float]] = None


@app.post("/state/regime-lab/replay", tags=["regime-lab"])
async def replay_fixed_window(request: ReplayRequest):
    """Re-run the rulebook over a frozen window of recorded evidence.

    Champion and challenger see identical stored evidence, so any difference is
    attributable to the configuration rather than to the market having moved.
    Paper only: replay cannot activate a rulebook or place an order.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    symbol = normalize_symbol(request.symbol) if request.symbol else None
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.id, s.symbol, s.features,
                       o.signed_return_pct, o.forward_return_pct
                FROM signals s
                JOIN opportunities opp ON opp.signal_id = s.id
                JOIN opportunity_outcomes o
                  ON o.opportunity_id = opp.id AND o.horizon_minutes = $1
                WHERE s.agent = 'regime_paper_scorer'
                  AND s.created_at > now() - ($2 || ' hours')::interval
                  AND o.status = 'measured'
                  AND ($3::text IS NULL OR s.symbol = $3)
                ORDER BY s.created_at
                """,
                request.horizon_minutes,
                str(request.hours),
                symbol,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    cases = []
    skipped = 0
    for row in rows:
        stored = row["features"]
        if isinstance(stored, str):
            stored = json.loads(stored)
        try:
            cases.append(
                case_from_stored_evidence(
                    str(row["id"]),
                    row["symbol"],
                    stored,
                    outcome_signed_return_pct=row["signed_return_pct"],
                    market_move_pct=row["forward_return_pct"],
                )
            )
        except ReplayError:
            # Evidence recorded before the current schema cannot be replayed
            # faithfully, so it is counted and excluded rather than guessed at.
            skipped += 1

    if not cases:
        return {
            "schema_version": "regime_replay_v1",
            "window_cases": 0,
            "skipped_unreplayable": skipped,
            "note": (
                "No measured decision in this window carries replayable "
                "evidence. Outcomes need the horizon to have closed."
            ),
        }

    champion = regime_lab_engine.baseline
    challenger = champion
    if request.challenger_weights:
        try:
            data = json.loads(json.dumps(champion.data))
            for block, weight in request.challenger_weights.items():
                if block not in data["blocks"]:
                    raise HTTPException(
                        status_code=400, detail=f"unknown block '{block}'"
                    )
                data["blocks"][block]["weight"] = weight
            data["version"] = f"{champion.version}-challenger"
            challenger = validate_rulebook(data)
        except RulebookValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    result = compare_rulebooks(
        cases,
        champion,
        challenger,
        AdmissionPolicy(),
        {
            "catalog_id": regime_lab_engine.catalog.data["catalog_id"],
            "version": regime_lab_engine.catalog.version,
            "digest": regime_lab_engine.catalog.digest,
        },
    )
    result["horizon_minutes"] = request.horizon_minutes
    result["window_hours"] = request.hours
    result["skipped_unreplayable"] = skipped
    result["execution_authority"] = False
    return result


class QuarantineSubmission(BaseModel):
    """One external submission. Nothing here confers authority."""

    source: str
    payload: Dict[str, Any]
    observed_at_ms: Optional[int] = None


@app.post("/state/quarantine", tags=["quarantine"])
async def submit_to_quarantine(submission: QuarantineSubmission):
    """Accept external material for review. This is not admission to anything.

    Tier B connectors submit here. A stored row is untrusted material an
    operator can inspect; it carries no scoring, approval or execution
    authority and cannot become evidence without a deliberate promotion.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    received_ms = int(time.time() * 1000)
    try:
        async with state.pool.acquire() as conn:
            seen = await conn.fetch(
                "SELECT content_digest FROM quarantine_intake WHERE source = $1",
                submission.source,
            )
            verdict = evaluate_submission(
                submission.source,
                submission.payload,
                received_ms,
                observed_at_ms=submission.observed_at_ms,
                seen_digests=[r["content_digest"] for r in seen],
            )
            # Refusals are stored too: "what did that connector try to send"
            # is exactly the question an operator needs answered later.
            await conn.execute(
                """
                INSERT INTO quarantine_intake
                    (source, accepted, content_digest, payload, reasons, observed_at)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb,
                        CASE WHEN $6::bigint IS NULL THEN NULL
                             ELSE to_timestamp($6::bigint / 1000.0) END)
                ON CONFLICT (source, content_digest) DO NOTHING
                """,
                submission.source,
                verdict.accepted,
                verdict.content_digest,
                json.dumps(submission.payload),
                json.dumps(verdict.reasons),
                submission.observed_at_ms,
            )
    except QuarantineError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return verdict.to_dict()


@app.get("/state/quarantine", tags=["quarantine"])
async def list_quarantine(
    source: Optional[str] = None,
    pending_only: bool = False,
    limit: int = Query(50, le=200),
):
    """What connectors have sent, accepted or not, newest first."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT q.id, q.source, q.accepted, q.content_digest, q.payload, q.reasons,
                       q.observed_at, q.received_at, q.reviewed_by, q.reviewed_at, q.promoted_to,
                       x.claims AS rule_claims, x.reason AS rule_reason,
                       h.claims AS harness_claims, h.reason AS harness_reason
                FROM quarantine_intake q
                LEFT JOIN quarantine_extractions x ON x.quarantine_id = q.id
                LEFT JOIN quarantine_harness_extractions h ON h.quarantine_id = q.id
                WHERE ($1::text IS NULL OR q.source = $1)
                  AND ($2::boolean IS FALSE OR q.reviewed_at IS NULL)
                ORDER BY q.received_at DESC
                LIMIT $3
                """,
                source,
                pending_only,
                limit,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "schema_version": "quarantine_v1",
        "authority": "none",
        "items": [
            {
                "id": str(r["id"]),
                "source": r["source"],
                "accepted": r["accepted"],
                "content_digest": r["content_digest"],
                "payload": json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"],
                "reasons": json.loads(r["reasons"]) if isinstance(r["reasons"], str) else r["reasons"],
                "observed_at": r["observed_at"].isoformat() if r["observed_at"] else None,
                "received_at": r["received_at"].isoformat(),
                "reviewed_by": r["reviewed_by"],
                "promoted_to": r["promoted_to"],
                # What extraction made of it: rule pass first, harness pass if asked.
                "extraction": {
                    "rule": None if r["rule_claims"] is None else {"claims": int(r["rule_claims"]), "reason": r["rule_reason"] or ""},
                    "harness": None if r["harness_claims"] is None else {"claims": int(r["harness_claims"]), "reason": r["harness_reason"] or ""},
                },
            }
            for r in rows
        ],
        "note": (
            "Quarantined material is untrusted and confers no authority. "
            "Promotion to admitted evidence is a separate operator act."
        ),
    }


class QuarantineReview(BaseModel):
    """An operator decision on one quarantined item."""

    reviewed_by: str
    promote: bool = False
    target_provenance: str = "context_only"
    note: str = ""


class GateApproval(BaseModel):
    """One authenticated ChaseOS decision, presented by the operator."""

    quarantine_id: str
    approval_id: str
    approval_digest: str
    approval_decision_id: str
    approved_at_utc: str
    validity_hours: int = 4


@app.get("/state/execution/reconciliation", tags=["execution"])
async def get_execution_reconciliation(hours: int = Query(24, ge=1, le=720)):
    """Where the recorded intent and the recorded action disagree.

    Reads two of this system's own tables and reports divergence. It cannot
    place, amend or cancel anything, and it behaves identically in paper mode —
    which is the only mode this system runs in.

    A system that cannot tell you when its own records have drifted apart is
    less safe, and the day that matters is the day something did execute and the
    ledger disagrees. A clean result is reported as a result, not as silence.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    async with state.pool.acquire() as conn:
        decisions = await conn.fetch(
            """
            SELECT id::text AS id, requested
            FROM decisions
            WHERE created_at > now() - make_interval(hours => $1)
            ORDER BY created_at DESC
            """,
            hours,
        )
        orders = await conn.fetch(
            """
            SELECT id::text AS id, decision_id::text AS decision_id, request, dry_run
            FROM exec_orders
            WHERE created_at > now() - make_interval(hours => $1)
            ORDER BY created_at DESC
            """,
            hours,
        )

    result = reconcile(
        [{"id": r["id"], "requested": _as_json(r["requested"])} for r in decisions],
        [
            {
                "id": r["id"],
                "decision_id": r["decision_id"],
                "request": _as_json(r["request"]),
            }
            for r in orders
        ],
    )

    return {
        "window_hours": hours,
        **result,
        "paper_mode": paper_mode_enabled(),
        "execution_gate_open": execution_gate_enabled(),
        "note": (
            "Read-only comparison of recorded decisions against recorded orders. "
            "Nothing here can place, amend or cancel an order."
        ),
    }


@app.get("/state/execution/wallet-preview", tags=["execution"])
async def get_wallet_preview(address: Optional[str] = None):
    """Account state for the configured address, read-only.

    An address is public: it is in every transaction the account has ever made.
    Reading state for one requires no key and grants nothing, which is why this
    can exist while the signer stays separate.

    What it answers is the question you want answered *before* an order, not
    after: what is actually in the account, what is already open, and how much
    margin is already committed. A preview computed from this system's own
    records would tell you what TradeSync believes; this tells you what the
    venue believes, and the difference between those is the interesting part.
    """
    preview_address = address.strip() if address is not None else WALLET_ADDRESS
    if address is not None and not re.fullmatch(r"0x[0-9a-fA-F]{40}", preview_address):
        raise HTTPException(status_code=422, detail="Expected a public EVM address: 0x followed by 40 hexadecimal characters. Never enter a private key.")
    if not preview_address:
        return {
            "configured": False,
            "address": None,
            "status": "not_configured",
            "detail": "WALLET_ADDRESS is unset; no account is being previewed",
            "authority": "read_only",
        }

    try:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            response = await client.post(
                HYPERLIQUID_INFO_URL,
                json={"type": "clearinghouseState", "user": preview_address},
            )
            response.raise_for_status()
            state_payload = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"venue did not answer: {type(exc).__name__}"
                + (f": {exc}" if str(exc) else "")
            ),
        )

    if not isinstance(state_payload, dict) or not isinstance(state_payload.get("marginSummary"), dict) or not isinstance(state_payload.get("assetPositions"), list):
        raise HTTPException(status_code=503, detail="Venue account response is incomplete; no balance is inferred")
    margin = state_payload["marginSummary"]
    positions = []
    for entry in state_payload.get("assetPositions") or []:
        position = entry.get("position") or {}
        if not position.get("szi"):
            continue
        size = float(position.get("szi") or 0)
        positions.append({
            "symbol": f"{position.get('coin')}-PERP",
            "size": size,
            # szi is signed; the sign is the side. Reporting it separately means
            # nobody downstream has to rediscover that convention.
            "side": "LONG" if size > 0 else "SHORT",
            "entry_price": _as_float(position.get("entryPx")),
            "unrealized_pnl": _as_float(position.get("unrealizedPnl")),
            "position_value": _as_float(position.get("positionValue")),
            "leverage": (position.get("leverage") or {}).get("value"),
            "liquidation_price": _as_float(position.get("liquidationPx")),
        })

    account_value = _as_float(margin.get("accountValue"))
    total_margin_used = _as_float(margin.get("totalMarginUsed"))
    if account_value is None or total_margin_used is None or not math.isfinite(account_value) or not math.isfinite(total_margin_used):
        raise HTTPException(status_code=503, detail="Venue balance fields are unavailable; no balance is inferred")

    return {
        "configured": True,
        "address": preview_address,
        "lookup_mode": "session_watch_only" if address is not None else "configured_watch_only",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "network": "testnet" if "testnet" in HYPERLIQUID_INFO_URL else "mainnet",
        "account_value_usd": account_value,
        "withdrawable_usd": _as_float(state_payload.get("withdrawable")),
        "total_margin_used_usd": total_margin_used,
        # The number that matters when deciding whether another position is
        # sane. Reported rather than left for a reader to divide.
        "margin_utilization": round(total_margin_used / account_value, 4)
        if account_value > 0
        else None,
        "open_positions": positions,
        "position_count": len(positions),
        "source": "hyperliquid clearinghouseState",
        "authority": "read_only",
        "note": (
            "Read from a public address. No key is involved and nothing here "
            "authorises anything; the signer is a separate process."
        ),
    }


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@app.get("/state/execution/signer-status", tags=["execution"])
async def get_signer_status():
    """What the isolated signer reports about itself.

    Proxied rather than inlined, because the signer is deliberately a separate
    process and state-api must not grow the ability to answer for it.
    """
    try:
        async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
            response = await client.get(f"{SIGNER_URL}/signer/status")
            response.raise_for_status()
            return {**response.json(), "reachable": True}
    except Exception as exc:
        # Offline is the expected state: the signer is not in the bounded
        # profile and running one is a deliberate act.
        return {
            "reachable": False,
            "available": False,
            "status": "offline",
            "detail": type(exc).__name__ + (f": {exc}" if str(exc) else ""),
        }


@app.get("/state/execution/preflight", tags=["execution"])
async def get_execution_preflight():
    """Everything that would have to be true before any order could be placed.

    This makes the closed gate **legible**. It opens nothing: every field is a
    read, and the endpoint has no counterpart that flips any of them.

    The reason it is worth having while execution is disabled is that "why can I
    not trade" currently has its answer spread across an environment variable, a
    service that may not be running, a roadmap gate, and a risk policy. One
    place that lists them, with the current value of each, is the difference
    between a deliberate closed gate and one nobody can account for.
    """
    blockers: list[dict[str, Any]] = []

    if not execution_gate_enabled():
        blockers.append({
            "check": "execution_gate",
            "state": "closed",
            "detail": "EXECUTION_ENABLED is false. This is the global killswitch "
                      "and it is checked before any per-symbol rule.",
        })
    if paper_mode_enabled():
        blockers.append({
            "check": "paper_mode",
            "state": "on",
            "detail": "DRY_RUN is true. Orders are simulated at the execution "
                      "boundary and never reach a venue.",
        })

    # The measurement gate. This is the one that matters most and is the least
    # visible, because it lives in a document rather than in a variable.
    blockers.append({
        "check": "skill_gate_1_2",
        "state": "negative",
        "detail": "Gate 1.2 measured no demonstrated skill in any regime at any "
                  "horizon. Nothing in the current measurements argues for "
                  "moving toward execution.",
    })

    # The venue boundary's own view. Offline is an ordinary answer: exec-hl-svc
    # is outside the bounded profile and not running one is the normal state.
    venue: dict[str, Any] = {"status": "offline"}
    try:
        async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
            resp = await client.get(f"{EXEC_HL_URL}/exec/hl/preflight")
        venue = (
            resp.json()
            if resp.status_code == 200
            else {"status": "error", "http_status": resp.status_code}
        )
    except Exception as exc:
        # The type, and the message only when there is one. httpx timeouts
        # stringify to empty, and "ConnectTimeout: " with nothing after the
        # colon reads like a truncated message rather than a complete answer.
        venue = {
            "status": "offline",
            "detail": type(exc).__name__ + (f": {exc}" if str(exc) else ""),
        }

    return {
        "can_execute": False if blockers else None,
        "blockers": blockers,
        "venue_preflight": venue,
        "authority": "read_only",
        "note": (
            "An inventory of what is closed and why. This endpoint opens "
            "nothing and has no counterpart that does. Opening the gate is an "
            "operator act requiring explicit approval and a passing skill gate."
        ),
    }


@app.get("/state/knowledge/gate/status", tags=["knowledge"])
async def get_gate_status():
    """What the ChaseOS Gate can and cannot authorise.

    The Gate is an approval mechanism, not a knowledge one. It is deliberately
    narrow: an approval binds to exactly one candidate and authorises exactly
    one paper evaluation. There is no approval this system will accept that
    authorises an order, a wallet, a credential, a signature, or a live
    dispatch, and the ceiling below is the one actually enforced rather than a
    description of it.
    """
    unconsumed = consumed = 0
    if state.pool:
        async with state.pool.acquire() as conn:
            unconsumed = await conn.fetchval(
                "SELECT count(*) FROM control_envelopes WHERE consumed_at IS NULL"
            )
            consumed = await conn.fetchval(
                "SELECT count(*) FROM control_envelopes WHERE consumed_at IS NOT NULL"
            )

    return {
        "control_plane": "chaseos",
        "mode": "paper_only",
        # Verbatim from the library, not restated here. A copy would drift.
        "authority_ceiling": CLOSED_AUTHORITY,
        "scope": "once",
        "envelopes": {"unconsumed": unconsumed, "consumed": consumed},
        "execution_gate_open": execution_gate_enabled(),
        "paper_mode": paper_mode_enabled(),
        "note": (
            "An approval authorises one paper evaluation of one candidate. "
            "Single use is enforced by a unique constraint on approval_id, not "
            "by convention. TradeSync remains usable when the Gate is offline; "
            "what stops is approval, not observation."
        ),
    }


@app.post("/state/knowledge/gate/authorize-paper-evaluation", tags=["knowledge"])
async def authorize_paper_evaluation(approval: GateApproval):
    """Bind a ChaseOS approval to one extracted candidate. Fails closed.

    The candidate is re-extracted from its quarantined receipt rather than
    accepted from the caller, so an approval cannot be attached to a candidate
    that was edited after the operator looked at it. The envelope carries a hash
    of exactly what was approved.

    Replaying an approval is refused by a unique constraint, not by a check that
    could race. Single use is a fact about history, so it is enforced where
    history lives.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    # Re-extract rather than trust: the caller supplies an approval, never a
    # candidate.
    extracted = await extract_trade_candidate(
        approval.quarantine_id, validity_hours=approval.validity_hours
    )
    candidate = extracted["candidate"]

    try:
        envelope = build_paper_control_envelope(
            candidate,
            approval_id=approval.approval_id,
            approval_digest=approval.approval_digest,
            approval_decision_id=approval.approval_decision_id,
            approved_at_utc=approval.approved_at_utc,
        )
    except ControlEnvelopeError as exc:
        raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}")

    try:
        async with state.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO control_envelopes (
                    envelope_id, approval_id, approval_decision_id, approval_digest,
                    approved_at, candidate_id, candidate_hash, candidate,
                    authority, source_quarantine_id
                ) VALUES ($1,$2,$3,$4,$5::timestamptz,$6,$7,$8::jsonb,$9::jsonb,$10::uuid)
                """,
                envelope["envelope_id"],
                envelope["approval"]["approval_id"],
                envelope["approval"]["approval_decision_id"],
                envelope["approval"]["approval_digest"],
                parse_utc(envelope["approval"]["approved_at_utc"], "approved_at_utc"),
                candidate["candidate_id"],
                envelope["candidate_hash"],
                json.dumps(candidate),
                json.dumps(envelope["authority"]),
                approval.quarantine_id,
            )
    except asyncpg.UniqueViolationError:
        # Scope is "once". A replay is refused rather than authorising a second
        # evaluation on the same decision.
        raise HTTPException(
            status_code=409,
            detail=(
                f"approval {approval.approval_id} has already been bound; its "
                "scope is 'once' and it cannot authorise a second evaluation"
            ),
        )

    return {
        "envelope_id": envelope["envelope_id"],
        "candidate_id": candidate["candidate_id"],
        "candidate_hash": envelope["candidate_hash"],
        "authority": envelope["authority"],
        "authorizes": envelope["approval"]["authorizes"],
        "scope": envelope["approval"]["scope"],
        "consumed": False,
        "note": (
            "Authorises one paper evaluation of this exact candidate. Not an "
            "order, wallet, credential, signature or live dispatch."
        ),
    }


@app.post("/state/quarantine/{item_id}/extract-candidate", tags=["quarantine"])
async def extract_trade_candidate(item_id: str, validity_hours: int = Query(4, ge=1, le=72)):
    """Turn a quarantined Strike Zone / Pine alert into a proposed candidate.

    This is the **extraction** step of quarantine -> extraction -> proposed
    delta -> approved promotion. It reads stored material and returns a
    `trade_candidate_v1` proposal. Nothing is promoted here and no authority is
    granted: the candidate is `review_only` at `level_0_observation_only` with
    execution disabled, and those fields are written by the adapter rather than
    read from the alert.

    A receipt that tried to set its own authority is refused with the field
    named. A Pine script is a text file on a third party's server and anyone
    holding the alert URL can aim it here; if it could set
    `live_execution_allowed` this endpoint would be a remote execution
    primitive.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    async with state.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, source, accepted, payload, received_at, observed_at
            FROM quarantine_intake WHERE id = $1::uuid
            """,
            item_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="quarantine item not found")
    if row["source"] not in {"tradingview", "strike_zone"}:
        raise HTTPException(
            status_code=400,
            detail=(
                f"source {row['source']!r} does not carry Pine receipts; "
                "candidates are extracted from tradingview or strike_zone items"
            ),
        )
    if not row["accepted"]:
        # A refused submission is stored so the operator can see what was tried.
        # Building a candidate from one would launder it into research material.
        raise HTTPException(
            status_code=409,
            detail="this item was refused at intake; a candidate cannot be built from it",
        )

    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    # The webhook stores the alert body under "alert"; a direct submission may
    # carry the receipt at the top level.
    receipt_body = payload.get("alert") if isinstance(payload.get("alert"), dict) else payload

    try:
        receipt = validate_receipt(receipt_body)
        candidate = to_trade_candidate(
            receipt,
            canonical_symbol=normalize_symbol(receipt["ticker"]),
            asset=receipt["ticker"].split("USD")[0] or receipt["ticker"],
            observed_at=(row["observed_at"] or row["received_at"]),
            validity=timedelta(hours=validity_hours),
            source_item_id=str(row["id"]),
        )
    except ReceiptError as exc:
        raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}")

    return {
        "quarantine_id": str(row["id"]),
        "candidate": candidate,
        "status": "proposed",
        "authority": "none",
        "note": (
            "A proposal, not a promotion. The candidate is review_only at "
            "level_0_observation_only with execution disabled; the paper ledger "
            "re-checks those invariants independently before evaluating it."
        ),
    }


@app.post("/state/quarantine/{item_id}/review", tags=["quarantine"])
async def review_quarantine_item(item_id: str, review: QuarantineReview):
    """Record an operator decision on quarantined material.

    Promotion is an operator act and stays one. This endpoint records the
    decision and the blockers that applied; it does not itself grant a
    quarantined item any scoring or execution authority.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    if not review.reviewed_by.strip():
        raise HTTPException(status_code=400, detail="reviewed_by is required")

    try:
        async with state.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, accepted, promoted_to FROM quarantine_intake WHERE id = $1::uuid",
                item_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="quarantine item not found")

            blockers = promotion_blockers(
                row["accepted"], review.reviewed_by, review.target_provenance
            )
            promoted = review.promote and not blockers
            await conn.execute(
                """
                UPDATE quarantine_intake
                SET reviewed_by = $2, reviewed_at = now(),
                    promoted_to = CASE WHEN $3 THEN $4 ELSE promoted_to END
                WHERE id = $1::uuid
                """,
                item_id,
                review.reviewed_by,
                promoted,
                review.target_provenance if promoted else None,
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "schema_version": "quarantine_v1",
        "id": item_id,
        "reviewed_by": review.reviewed_by,
        "promoted": promoted,
        "blockers": blockers,
        "authority": "none",
        "note": (
            "Review is recorded. Promotion marks an item as admitted context; "
            "it never grants scoring, approval or execution authority."
        ),
    }


TRADINGVIEW_WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "").strip()


@app.post("/webhook/tradingview", tags=["quarantine"])
async def tradingview_webhook(request: Request):
    """Receive a TradingView (including Strike Zone Pine) alert.

    The alert lands in quarantine as untrusted material. It is never a signal,
    and nothing here can approve or execute.

    Disabled unless TRADINGVIEW_WEBHOOK_SECRET is set: an unauthenticated public
    endpoint into a trading system is not an acceptable default. TradingView
    cannot send custom headers, so the secret travels in the alert body.
    """
    if not TRADINGVIEW_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "webhook disabled: set TRADINGVIEW_WEBHOOK_SECRET before "
                "exposing this endpoint"
            ),
        )
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    body = await request.body()
    alert = parse_alert(body, TRADINGVIEW_WEBHOOK_SECRET)

    # An unauthenticated alert is refused without touching the database, so a
    # flood of bad secrets cannot fill the intake table.
    if not alert.authenticated:
        logger.warning(
            f"tradingview alert refused: {[r['code'] for r in alert.reasons]}",
            extra={"trace_id": "webhook"},
        )
        return JSONResponse(
            status_code=401,
            content={
                "accepted": False,
                "reasons": alert.reasons,
                "authority": "none",
            },
        )

    submission = alert.to_submission()
    received_ms = int(time.time() * 1000)
    try:
        async with state.pool.acquire() as conn:
            seen = await conn.fetch(
                "SELECT content_digest FROM quarantine_intake WHERE source = 'tradingview'"
            )
            verdict = evaluate_submission(
                "tradingview",
                submission,
                received_ms,
                seen_digests=[r["content_digest"] for r in seen],
            )
            await conn.execute(
                """
                INSERT INTO quarantine_intake
                    (source, accepted, content_digest, payload, reasons)
                VALUES ('tradingview', $1, $2, $3::jsonb, $4::jsonb)
                ON CONFLICT (source, content_digest) DO NOTHING
                """,
                verdict.accepted,
                verdict.content_digest,
                json.dumps(submission),
                json.dumps(verdict.reasons),
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return verdict.to_dict()


@app.get("/state/outcomes/by-regime", tags=["outcomes"])
async def get_outcomes_by_regime(horizon_minutes: int = 60, symbol: Optional[str] = None):
    """Skill measured separately in rising and falling markets.

    Pooling regimes is actively misleading. A caller with a fixed directional
    bias, measured across windows with very different base rates, shows an
    apparent effect that vanishes once each regime is scored against its own
    baseline. On 2026-09-08 the pooled figure read -10.2 points (-2.4 SE) while
    the same data split by regime read -2.9 and -5.6 points, both inside one
    standard error.

    Regime is assigned from the hour's own aggregate move, not from the
    individual outcome being scored.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    if symbol:
        symbol = normalize_symbol(symbol)

    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH hourly AS (
                  SELECT date_trunc('hour', opened_at) hr, avg(forward_return_pct) hr_move
                  FROM opportunity_outcomes
                  WHERE status = 'measured' AND horizon_minutes = $1
                    AND ($2::text IS NULL OR symbol = $2)
                  GROUP BY 1
                ),
                tagged AS (
                  SELECT o.*, CASE WHEN h.hr_move > 0 THEN 'rising' ELSE 'falling' END regime
                  FROM opportunity_outcomes o
                  JOIN hourly h ON h.hr = date_trunc('hour', o.opened_at)
                  WHERE o.status = 'measured' AND o.horizon_minutes = $1
                    AND ($2::text IS NULL OR o.symbol = $2)
                )
                SELECT regime, count(*) n,
                       count(*) FILTER (WHERE signed_return_pct > 0) wins,
                       count(*) FILTER (WHERE forward_return_pct > 0) ups,
                       count(*) FILTER (WHERE direction = 'LONG') longs,
                       avg(signed_return_pct) mean_signed,
                       count(DISTINCT symbol) symbols,
                       EXTRACT(EPOCH FROM (max(opened_at) - min(opened_at)))/60 span_minutes
                FROM tagged GROUP BY regime ORDER BY regime
                """,
                horizon_minutes,
                symbol,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    regimes = []
    for r in rows:
        n = r["n"]
        if not n:
            continue
        hit = r["wins"] / n
        up = r["ups"] / n
        long_share = r["longs"] / n
        baseline = long_share * up + (1 - long_share) * (1 - up)
        skill = hit - baseline

        # Independent windows, not observations.
        #
        # A verdict is recorded every 60 seconds and a 240-minute horizon covers
        # 240 minutes of price. Two observations four minutes apart share 98% of
        # their window: they are very nearly the same trade counted twice.
        # Treating them as independent understates the error by the square root
        # of the overcounting, and that is exactly how a 74-observation sample
        # spanning 5.6 hours reported a "significant" result off roughly four
        # genuinely independent windows.
        #
        # The effective sample is how many non-overlapping windows of this
        # horizon fit in the span, times the number of symbols. Symbols are
        # counted as independent, which is generous — BTC, ETH and SOL move
        # together — so this remains a floor on the uncertainty rather than an
        # estimate of it.
        span_minutes = float(r["span_minutes"] or 0)
        symbols = int(r["symbols"] or 1)
        windows = span_minutes / horizon_minutes if horizon_minutes else 0
        effective_n = max(min(n, symbols * windows), 1.0)

        se = math.sqrt(0.25 / effective_n)
        naive_se = math.sqrt(0.25 / n)

        regimes.append({
            "regime": r["regime"],
            "measured": n,
            # What the sample is actually worth.
            "effective_observations": round(effective_n, 1),
            "independent_windows_per_symbol": round(windows, 1),
            "symbols": symbols,
            "span_minutes": round(span_minutes),
            "hit_rate": round(hit, 4),
            "market_up_rate": round(up, 4),
            "long_share": round(long_share, 4),
            "expected_hit_rate": round(baseline, 4),
            "skill_vs_baseline": round(skill, 4),
            "standard_error": round(se, 4),
            "naive_standard_error": round(naive_se, 4),
            "overlap_inflation": round(se / naive_se, 1) if naive_se else None,
            "skill_in_standard_errors": round(skill / se, 2) if se else None,
            # Judged against the overlap-adjusted error. The old flag said True
            # for a result its own note disclaimed in prose.
            "significant": abs(skill) > 2 * se,
            "mean_signed_return_pct": round(r["mean_signed"], 6) if r["mean_signed"] is not None else None,
        })

    return {
        "schema_version": "opportunity_outcome_v1",
        "horizon_minutes": horizon_minutes,
        "symbol": symbol,
        "regimes": regimes,
        "note": (
            "Regimes are scored separately because pooling them is misleading: "
            "a fixed directional bias across windows with different base rates "
            "produces an apparent effect that is an artefact of aggregation. "
            "standard_error is adjusted for overlap: a verdict every 60 "
            "seconds over a 240-minute horizon produces observations that are "
            "very nearly the same trade counted many times, so the sample is "
            "worth effective_observations, not measured. Symbols are treated "
            "as independent, which is generous, so this is still a floor on "
            "the uncertainty rather than an estimate of it."
        ),
    }


class DrawingPayload(BaseModel):
    """One operator drawing. Annotation only; confers no authority."""

    symbol: str
    interval: str
    kind: str
    points: List[Dict[str, Any]]
    label: str = ""
    colour: str = ""


@app.get("/state/canvas/drawings", tags=["canvas"])
async def list_drawings(symbol: str, interval: str):
    """Current drawings for one chart: each drawing at its live version."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    resolved = normalize_symbol(symbol)
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT drawing_id, version, kind, points, label, colour, created_at
                FROM canvas_drawings
                WHERE symbol = $1 AND interval = $2
                  AND superseded_at IS NULL AND deleted = false
                ORDER BY created_at
                """,
                resolved,
                interval,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "schema_version": "canvas_drawing_v1",
        "symbol": resolved,
        "interval": interval,
        "authority": "none",
        "drawings": [
            {
                "drawing_id": str(r["drawing_id"]),
                "version": r["version"],
                "kind": r["kind"],
                "points": json.loads(r["points"]) if isinstance(r["points"], str) else r["points"],
                "label": r["label"],
                "colour": r["colour"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
    }


async def _insert_drawing_version(conn, drawing, drawing_id, version, deleted=False):
    """Insert one version. Callers supersede the previous row first."""
    await conn.execute(
        """
        INSERT INTO canvas_drawings
            (drawing_id, version, symbol, interval, kind, points, label, colour, deleted)
        VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
        """,
        str(drawing_id),
        version,
        drawing.symbol,
        drawing.interval,
        drawing.kind,
        json.dumps([p.to_dict() for p in drawing.points]),
        drawing.label,
        drawing.colour,
        deleted,
    )


@app.post("/state/canvas/drawings", tags=["canvas"])
async def create_drawing(payload: DrawingPayload):
    """Record a new drawing at version 1."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    body = payload.model_dump()
    body["symbol"] = normalize_symbol(body["symbol"])
    try:
        drawing = validate_drawing(body)
    except DrawingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    drawing_id = uuid.uuid4()
    try:
        async with state.pool.acquire() as conn:
            await _insert_drawing_version(conn, drawing, drawing_id, next_version(None))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {**drawing.to_dict(), "drawing_id": str(drawing_id), "version": 1}


@app.put("/state/canvas/drawings/{drawing_id}", tags=["canvas"])
async def update_drawing(drawing_id: str, payload: DrawingPayload):
    """Supersede a drawing with a new version. The old version is kept."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    body = payload.model_dump()
    body["symbol"] = normalize_symbol(body["symbol"])
    try:
        drawing = validate_drawing(body)
    except DrawingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        async with state.pool.acquire() as conn:
            async with conn.transaction():
                current = await conn.fetchrow(
                    """
                    SELECT version FROM canvas_drawings
                    WHERE drawing_id = $1::uuid AND superseded_at IS NULL
                    ORDER BY version DESC LIMIT 1
                    """,
                    drawing_id,
                )
                if not current:
                    raise HTTPException(status_code=404, detail="drawing not found")
                await conn.execute(
                    """
                    UPDATE canvas_drawings SET superseded_at = now()
                    WHERE drawing_id = $1::uuid AND superseded_at IS NULL
                    """,
                    drawing_id,
                )
                version = next_version(current["version"])
                await _insert_drawing_version(conn, drawing, drawing_id, version)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {**drawing.to_dict(), "drawing_id": drawing_id, "version": version}


@app.delete("/state/canvas/drawings/{drawing_id}", tags=["canvas"])
async def delete_drawing(drawing_id: str):
    """Remove a drawing from the chart. Its history is retained."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    try:
        async with state.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE canvas_drawings SET superseded_at = now(), deleted = true
                WHERE drawing_id = $1::uuid AND superseded_at IS NULL
                """,
                drawing_id,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if result.endswith(" 0"):
        raise HTTPException(status_code=404, detail="drawing not found")
    return {"drawing_id": drawing_id, "deleted": True, "history_retained": True}


@app.get("/state/canvas/drawings/{drawing_id}/history", tags=["canvas"])
async def drawing_history(drawing_id: str):
    """Every version of one drawing, oldest first."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT version, kind, points, label, colour, created_at,
                       superseded_at, deleted
                FROM canvas_drawings WHERE drawing_id = $1::uuid
                ORDER BY version
                """,
                drawing_id,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not rows:
        raise HTTPException(status_code=404, detail="drawing not found")

    return {
        "schema_version": "canvas_drawing_v1",
        "drawing_id": drawing_id,
        "versions": [
            {
                "version": r["version"],
                "kind": r["kind"],
                "points": json.loads(r["points"]) if isinstance(r["points"], str) else r["points"],
                "label": r["label"],
                "colour": r["colour"],
                "created_at": r["created_at"].isoformat(),
                "superseded_at": r["superseded_at"].isoformat() if r["superseded_at"] else None,
                "deleted": r["deleted"],
            }
            for r in rows
        ],
    }


@app.get("/state/evidence/timeline", tags=["evidence"])
async def evidence_timeline(symbol: str, limit: int = Query(25, le=100)):
    """One row per paper opportunity, from observation through to outcome.

    This is the Phase 4 exit gate in endpoint form: everything needed to
    reconstruct a paper trade without screenshots or memory. Each entry carries
    the evidence that produced it, the configuration digests it was produced
    under, and what the market subsequently did.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    resolved = normalize_symbol(symbol)

    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT o.id, o.symbol, o.dir, o.bias, o.quality, o.snapshot_ts,
                       o.links, o.confluence,
                       s.id AS signal_id, s.created_at AS signal_at,
                       coalesce(
                         json_agg(
                           json_build_object(
                             'horizon_minutes', x.horizon_minutes,
                             'status', x.status,
                             'signed_return_pct', x.signed_return_pct,
                             'forward_return_pct', x.forward_return_pct,
                             'max_favourable_pct', x.max_favourable_pct,
                             'max_adverse_pct', x.max_adverse_pct
                           ) ORDER BY x.horizon_minutes
                         ) FILTER (WHERE x.id IS NOT NULL), '[]'
                       ) AS outcomes
                FROM opportunities o
                LEFT JOIN signals s ON s.id = o.signal_id
                LEFT JOIN opportunity_outcomes x ON x.opportunity_id = o.id
                WHERE o.symbol = $1
                GROUP BY o.id, s.id
                ORDER BY o.snapshot_ts DESC
                LIMIT $2
                """,
                resolved,
                limit,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    entries = []
    for r in rows:
        confluence = r["confluence"]
        if isinstance(confluence, str):
            confluence = json.loads(confluence)
        confluence = confluence or {}
        links = r["links"]
        if isinstance(links, str):
            links = json.loads(links)
        evidence = confluence.get("evidence") or {}
        outcomes = r["outcomes"]
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)

        entries.append({
            "opportunity_id": str(r["id"]),
            "signal_id": str(r["signal_id"]) if r["signal_id"] else None,
            "symbol": r["symbol"],
            "direction": r["dir"],
            "directional_score": r["bias"],
            "coverage_pct": r["quality"],
            "opened_at": r["snapshot_ts"].isoformat(),
            "signal_at": r["signal_at"].isoformat() if r["signal_at"] else None,
            # The configuration this decision was taken under, so a replay can
            # reproduce it exactly rather than approximately.
            "catalog_version": evidence.get("catalog_version"),
            "catalog_digest": evidence.get("catalog_digest"),
            "rulebook_version": evidence.get("rulebook_version"),
            "rulebook_digest": evidence.get("rulebook_digest"),
            "evidence_digest": (links or {}).get("evidence_digest"),
            "contributing_features": confluence.get("contributing_features") or [],
            "missing_blocks": evidence.get("missing_blocks") or [],
            "paper_risk_multiplier": confluence.get("paper_risk_multiplier"),
            "outcomes": outcomes or [],
        })

    return {
        "schema_version": "evidence_timeline_v1",
        "symbol": resolved,
        "entries": entries,
        "note": (
            "Each entry reconstructs one paper opportunity from the evidence "
            "that produced it to what the market did next. No order was placed "
            "and no position existed."
        ),
    }


@app.get("/state/outcomes/summary", tags=["outcomes"])
async def get_outcome_summary(symbol: Optional[str] = None):
    """Measured track record of recorded paper opportunities.

    Describes what the market did after each call. It is a record of this
    sample, not a probability that the next call wins, and no order was ever
    placed.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    if symbol:
        symbol = normalize_symbol(symbol)

    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT horizon_minutes,
                       count(*) FILTER (WHERE status = 'measured') AS measured,
                       count(*) FILTER (WHERE status = 'pending') AS pending,
                       count(*) FILTER (WHERE status = 'insufficient_candles') AS unmeasurable,
                       avg(signed_return_pct) FILTER (WHERE status = 'measured') AS mean_signed,
                       avg(max_favourable_pct) FILTER (WHERE status = 'measured') AS mean_favourable,
                       avg(max_adverse_pct) FILTER (WHERE status = 'measured') AS mean_adverse,
                       count(*) FILTER (WHERE status = 'measured' AND signed_return_pct > 0) AS wins,
                       -- The market's own behaviour over exactly these windows.
                       count(*) FILTER (WHERE status = 'measured' AND forward_return_pct > 0) AS market_up,
                       count(*) FILTER (WHERE status = 'measured' AND direction = 'LONG') AS longs,
                       avg(forward_return_pct) FILTER (WHERE status = 'measured') AS mean_market_move
                FROM opportunity_outcomes
                WHERE ($1::text IS NULL OR symbol = $1)
                GROUP BY horizon_minutes
                ORDER BY horizon_minutes
                """,
                symbol,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    horizons = []
    for r in rows:
        measured = r["measured"] or 0
        hit_rate = r["wins"] / measured if measured else None
        up_rate = r["market_up"] / measured if measured else None
        long_share = r["longs"] / measured if measured else None
        # What this direction mix scores by luck alone, given how the market
        # actually moved. Without it, a one-regime sample reports the trend as
        # if it were ability.
        baseline = (
            long_share * up_rate + (1 - long_share) * (1 - up_rate)
            if measured
            else None
        )
        horizons.append({
            "horizon_minutes": r["horizon_minutes"],
            "measured": measured,
            "pending": r["pending"] or 0,
            "unmeasurable": r["unmeasurable"] or 0,
            # None rather than 0 when nothing is measured: an empty sample has
            # no hit rate, and 0% would read as "always wrong".
            "hit_rate": round(hit_rate, 4) if measured else None,
            "market_up_rate": round(up_rate, 4) if measured else None,
            "long_share": round(long_share, 4) if measured else None,
            "expected_hit_rate": round(baseline, 4) if measured else None,
            "skill_vs_baseline": round(hit_rate - baseline, 4) if measured else None,
            "mean_signed_return_pct": round(r["mean_signed"], 6) if r["mean_signed"] is not None else None,
            "mean_market_move_pct": round(r["mean_market_move"], 6) if r["mean_market_move"] is not None else None,
            "mean_favourable_pct": round(r["mean_favourable"], 6) if r["mean_favourable"] is not None else None,
            "mean_adverse_pct": round(r["mean_adverse"], 6) if r["mean_adverse"] is not None else None,
        })

    return {
        "schema_version": "opportunity_outcome_v1",
        "symbol": symbol,
        "horizons": horizons,
        "note": (
            "hit_rate is not interpretable alone: compare it with "
            "expected_hit_rate, what this direction mix scores by luck given "
            "how the market moved. A single-regime sample cannot demonstrate "
            "skill. No order was placed."
        ),
    }


@app.get("/state/market/candles")
async def get_market_candles(
    venue: str = "hyperliquid",
    symbol: str = "BTC-PERP",
    interval: str = "15m",
    limit: int = Query(300, le=1000),
):
    """Proxy venue OHLCV candles for the Market Canvas.

    Display only. Candles are not catalog features and carry no scoring
    authority; the upstream response states that explicitly.
    """
    path = (
        f"/candles/{venue}/{symbol}"
        f"?interval={interval}&limit={limit}"
    )
    try:
        resp = await asyncio.to_thread(_market_data_get, path)
    except Exception as e:
        logger.error(f"Error fetching candles: {e}", extra={"trace_id": "market"})
        raise HTTPException(status_code=503, detail="Market data service unavailable")

    if resp.status_code == 400:
        raise HTTPException(status_code=400, detail=resp.json().get("detail", "invalid request"))
    if resp.status_code == 404:
        # Hyperliquid is the only venue this system carries. Asking for another
        # is a client error and says so; it is not a fault in market-data.
        raise HTTPException(
            status_code=404,
            detail=resp.json().get("error", "unsupported venue or symbol"),
        )
    if resp.status_code >= 500 or resp.status_code == 503:
        raise HTTPException(status_code=503, detail="Market data service unavailable")
    resp.raise_for_status()
    return resp.json()


@app.get("/state/signals/refusal-history")
async def get_refusal_history(
    days: int = Query(30, ge=1, le=365),
    symbol: Optional[str] = None,
):
    """Daily refusal counts by reason, from the permanent aggregate.

    Full refusal rows are kept for a recent window only — roughly 4,300 a day of
    evidence JSON is not a store worth growing forever, and nobody reconstructs
    an individual refusal from three weeks ago. What does keep mattering is the
    denominator: "the coverage floor blocked 61% of ETH verdicts last Tuesday"
    is only answerable if the refusals are counted somewhere after the rows are
    gone.

    ``reason`` is the primary code — the first gate the evidence failed — so the
    counts sum to the exact number of refusals. ``reason_codes`` additionally
    tallies every code seen, including secondary ones, and those may sum higher.
    """
    if state.pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    clauses = ["day >= (current_date - $1::int)"]
    args: list = [days]
    if symbol:
        args.append(normalize_symbol(symbol))
        clauses.append(f"symbol = ${len(args)}")

    async with state.pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT day, symbol, reason, refusals, reason_codes,
                   scored_rows, covered_rows,
                   mean_score, mean_coverage, min_coverage, max_coverage,
                   first_rolled_at, last_rolled_at
            FROM signal_refusal_daily
            WHERE {' AND '.join(clauses)}
            ORDER BY day DESC, symbol, refusals DESC
            """,
            *args,
        )

    entries = []
    for row in rows:
        entry = dict(row)
        entry["day"] = entry["day"].isoformat()
        codes = entry.get("reason_codes")
        entry["reason_codes"] = json.loads(codes) if isinstance(codes, str) else codes
        entry["first_rolled_at"] = entry["first_rolled_at"].isoformat()
        entry["last_rolled_at"] = entry["last_rolled_at"].isoformat()
        entries.append(entry)

    return {
        "days": days,
        "symbol": symbol,
        "entries": entries,
        "total_refusals": sum(int(e["refusals"]) for e in entries),
        "note": (
            "Summarised from full refusal rows before they were removed. "
            "Recent days may still have their full rows in /state/signals."
        ),
    }


def _as_json(value):
    """asyncpg returns jsonb as str on some paths and as a value on others."""
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


class HarnessAsk(BaseModel):
    intent: str
    prompt: str
    context: Optional[Dict[str, Any]] = None


async def _record_harness_refusal(request: "HarnessAsk", exc: HarnessError) -> None:
    """File a refused harness answer as a quarantine refusal row.

    The offending content is stored as an opaque string in the payload, which is
    what quarantine is for: untrusted material kept for review. Nothing reads it
    back as structure, and the row is marked not accepted.

    Best effort. A failure to record must not mask the refusal itself — the
    operator still needs the 422.
    """
    if not state.pool:
        return
    try:
        payload = {
            "refused": True,
            "reason_code": exc.code,
            "reason": str(exc),
            "intent": request.intent,
            "prompt": request.prompt,
        }
        async with state.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO quarantine_intake
                    (source, accepted, content_digest, payload, reasons, observed_at)
                VALUES ('agent_harness', false, $1, $2::jsonb, $3::jsonb, now())
                ON CONFLICT (source, content_digest) DO NOTHING
                """,
                content_digest(payload),
                json.dumps(payload),
                json.dumps([{"code": exc.code, "detail": str(exc)}]),
            )
    except Exception as record_exc:
        logger.error(
            f"Could not record harness refusal: {record_exc}",
            extra={"trace_id": "agents"},
        )


@app.get("/state/agents/harness/status", tags=["agents"])
async def get_harness_status():
    """Whether an advisory harness runtime is reachable.

    "not_configured" and "offline" are ordinary states, not errors. Harnesses
    are optional and TradeSync is required to work without them — and reporting
    a stopped runtime as broken would repeat the healthcheck mistake this
    project already made once.
    """
    result = await agent_connector.probe()
    return {
        **result,
        "boundary": {
            "may_explain": True,
            "may_compare": True,
            "may_draft_proposals": True,
            "may_score": False,
            "may_approve": False,
            "may_execute": False,
        },
        "note": (
            "Enforced in code, not documented: a response carrying a score, "
            "direction, approval or order field is refused by name, and every "
            "accepted answer is routed to quarantine rather than to evidence."
        ),
    }


@app.post("/state/agents/harness/ask", tags=["agents"])
async def ask_harness(request: HarnessAsk):
    """Ask an advisory question and file the answer in quarantine.

    The answer is **never** returned as evidence. It is checked against the
    advisory-only contract, stored as an untrusted quarantine row, and the row's
    digest is returned as a receipt. Promotion to anything the system scores on
    remains an operator act through the normal quarantine review path.

    A model that claims scoring or approval authority produces HTTP 422 naming
    the field. That is a finding, not a transport failure: it usually means the
    prompt, or something the model read, tried to escalate.
    """
    if not agent_connector.configured():
        raise HTTPException(
            status_code=503,
            detail="AGENT_HARNESS_URL is unset; the harness connector is offline",
        )
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    try:
        result = await agent_connector.ask(
            request.intent, request.prompt, request.context
        )
    except HarnessError as exc:
        # A model reaching for authority is a finding, and this system already
        # holds that refusals are stored: "what did that connector try to send"
        # is exactly the question an operator needs answered later. Discarding
        # it would leave no trace of an escalation attempt.
        if exc.code == "authority_claimed":
            await _record_harness_refusal(request, exc)
        # 422 for a contract breach, 502 for a runtime that did not answer.
        status = 502 if exc.code in {"not_configured"} else 422
        raise HTTPException(status_code=status, detail=f"{exc.code}: {exc}")
    except httpx.HTTPError as exc:
        # The type matters. httpx.ReadTimeout stringifies to an empty string,
        # so "unreachable: " with nothing after it is what an operator would
        # have seen — the same trap that made an earlier read-path regression
        # in this system report a blank reason.
        raise HTTPException(
            status_code=504 if isinstance(exc, httpx.TimeoutException) else 502,
            detail=(
                f"harness runtime {type(exc).__name__}"
                + (f": {exc}" if str(exc) else " (no detail from the client)")
                + f" after {agent_connector.AGENT_HARNESS_TIMEOUT_S:.0f}s"
            ),
        )

    submission = agent_connector.quarantine_submission(result)
    received_ms = int(time.time() * 1000)

    async with state.pool.acquire() as conn:
        seen = await conn.fetch(
            "SELECT content_digest FROM quarantine_intake WHERE source = $1",
            submission["source"],
        )
        verdict = evaluate_submission(
            submission["source"],
            submission["payload"],
            received_ms,
            seen_digests=[r["content_digest"] for r in seen],
        )
        await conn.execute(
            """
            INSERT INTO quarantine_intake
                (source, accepted, content_digest, payload, reasons, observed_at)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, now())
            ON CONFLICT (source, content_digest) DO NOTHING
            """,
            submission["source"],
            verdict.accepted,
            verdict.content_digest,
            json.dumps(submission["payload"]),
            json.dumps(verdict.reasons),
        )

    return {
        "intent": result["task"]["intent"],
        "task_digest": result["task"]["task_digest"],
        "content": result["accepted"]["content"],
        "model": result["accepted"]["model"],
        "elapsed_ms": result["accepted"]["elapsed_ms"],
        # The evidence writeback receipt: what was filed, and where.
        "receipt": {
            "quarantined": verdict.accepted,
            "content_digest": verdict.content_digest,
            "source": submission["source"],
            "reasons": verdict.reasons,
        },
        "authority": "advisory_only",
        "note": (
            "Filed in quarantine as untrusted material. It is not evidence and "
            "cannot reach the scoring path without an operator promotion."
        ),
    }


@app.get("/state/knowledge/graph/status")
async def get_graph_status():
    """Whether the ChaseOS graph projection is configured, and what is in force.

    An unset connector is a normal state, not a fault: TradeSync must remain
    fully usable with every optional connector disabled. The answer says
    "not_configured" rather than reporting an error the operator cannot act on.
    """
    directory = snapshot_directory()
    files = available_snapshots()

    projected = None
    if state.pool is not None:
        async with state.pool.acquire() as conn:
            projected = await current_snapshot(conn)
    if projected:
        projected = {
            **projected,
            "created_at": projected["created_at"].isoformat(),
            "ingested_at": projected["ingested_at"].isoformat(),
            "extraction_scope": _as_json(projected.get("extraction_scope")),
            "build_info": _as_json(projected.get("build_info")),
        }

    return {
        "configured": directory is not None,
        "snapshot_dir": str(directory) if directory else None,
        "available_snapshots": [p.name for p in files],
        "projected": projected,
        "status": (
            "not_configured"
            if directory is None
            else "projected"
            if projected
            else "configured_but_never_ingested"
        ),
        # Restated on every response. A projection of canonical knowledge is
        # still not canonical, and it grants nothing.
        "authority": "read_only_projection",
        "note": (
            "ChaseOS is canonical. This is a local projection of a snapshot "
            "artifact, rebuildable from it, and it confers no scoring, "
            "approval or execution authority."
        ),
    }


@app.post("/state/knowledge/graph/ingest")
async def ingest_graph_snapshot(filename: Optional[str] = None):
    """Project a snapshot from the configured directory into local adjacency.

    Reads the named file, or the newest when none is named. The vault is opened
    read-only; nothing is written back to ChaseOS, which is the exit-gate
    requirement for this phase.

    A snapshot that claims scoring, approval or execution authority is refused
    by name rather than cleaned up and accepted.
    """
    if state.pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    directory = snapshot_directory()
    if directory is None:
        raise HTTPException(
            status_code=503,
            detail="CHASEOS_GRAPH_DIR is unset; the knowledge connector is offline",
        )

    files = available_snapshots()
    if not files:
        raise HTTPException(
            status_code=404,
            detail=f"no snapshot files in {directory}",
        )

    if filename:
        chosen = next((p for p in files if p.name == filename), None)
        if chosen is None:
            raise HTTPException(status_code=404, detail=f"no snapshot named {filename}")
    else:
        chosen = files[0]

    try:
        snapshot = read_snapshot(chosen)
    except SnapshotRejected as exc:
        # 422, not 500: the file was read fine and is not acceptable. The
        # reason is returned so the operator can take it back to ChaseOS.
        raise HTTPException(status_code=422, detail=str(exc))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"unreadable snapshot: {exc}")

    async with state.pool.acquire() as conn:
        result = await project_snapshot(conn, snapshot)

    logger.info(
        f"Projected ChaseOS snapshot {result['snapshot_id']} "
        f"({result['nodes']} nodes, {result['edges']} edges)",
        extra={"trace_id": "knowledge"},
    )
    return {"source_file": chosen.name, **result}


@app.get("/state/knowledge/graph/nodes")
async def get_graph_nodes(
    q: Optional[str] = None,
    node_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    """Search the projected nodes by label substring and type."""
    if state.pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with state.pool.acquire() as conn:
        projected = await current_snapshot(conn)
        if not projected:
            return {"snapshot_id": None, "nodes": [], "status": "no_projection"}

        clauses = ["snapshot_id = $1"]
        args: list = [projected["snapshot_id"]]
        if q:
            args.append(f"%{q.lower()}%")
            clauses.append(f"lower(label) LIKE ${len(args)}")
        if node_type:
            args.append(node_type)
            clauses.append(f"node_type = ${len(args)}")
        args.append(limit)

        rows = await conn.fetch(
            f"""
            SELECT node_id, label, node_type, source_file, source_line,
                   domain, project, confidence, provenance, community_id
            FROM graph_nodes
            WHERE {' AND '.join(clauses)}
            ORDER BY label
            LIMIT ${len(args)}
            """,
            *args,
        )

    return {
        "snapshot_id": projected["snapshot_id"],
        "nodes": [dict(row) for row in rows],
        "authority": "read_only_projection",
    }


@app.get("/state/knowledge/graph/neighbours/{node_id}")
async def get_graph_neighbours(
    node_id: str,
    depth: int = Query(2, ge=1, le=4),
    limit: int = Query(100, ge=1, le=500),
):
    """Nodes within ``depth`` hops of ``node_id``, in either direction.

    Undirected, because lineage and evidence-path questions do not care which
    way the extractor oriented an edge. Depth is capped: an unbounded walk over
    a 27k-note graph is not a query, it is a table scan with extra steps.
    """
    if state.pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with state.pool.acquire() as conn:
        projected = await current_snapshot(conn)
        if not projected:
            raise HTTPException(status_code=404, detail="no graph projection in force")
        found = await conn.fetchval(
            "SELECT 1 FROM graph_nodes WHERE snapshot_id = $1 AND node_id = $2",
            projected["snapshot_id"],
            node_id,
        )
        if not found:
            raise HTTPException(
                status_code=404,
                detail=f"node {node_id} is not in snapshot {projected['snapshot_id']}",
            )
        found_nodes = await neighbours(
            conn, projected["snapshot_id"], node_id, depth, limit
        )

    # Which hops are actually represented, not just which were asked for.
    # Results are ordered nearest-first, so a hub node with 1,500 immediate
    # neighbours fills the whole limit at one hop and a depth=3 request returns
    # nothing from hops 2 or 3. "truncated" says something was cut; this says
    # what you are actually looking at.
    hops_returned = sorted({int(n["hops"]) for n in found_nodes})
    truncated = len(found_nodes) >= limit

    return {
        "snapshot_id": projected["snapshot_id"],
        "node_id": node_id,
        "depth": depth,
        "neighbours": found_nodes,
        "truncated": truncated,
        "hops_returned": hops_returned,
        "reached_requested_depth": (not truncated) or (depth in hops_returned),
        "authority": "read_only_projection",
    }


@app.get("/state/market/context")
async def get_market_context(
    venue: str = "hyperliquid",
    symbol: str = "BTC-PERP",
    interval: str = "15m",
    limit: int = Query(300, le=1000),
):
    """Funding and open interest bucketed onto the canvas candle boundaries.

    The two series have different reaches and the response keeps them apart
    rather than blending them: funding is the venue's own hourly record and
    covers the whole chart, open interest is our rolling 24-hour recording
    because Hyperliquid publishes only the current value. Each carries a
    coverage block so the pane can state where its data actually stops.

    Display only, like candles. Neither series gains scoring authority here.
    """
    path = f"/context/{venue}/{symbol}?interval={interval}&limit={limit}"
    try:
        resp = await asyncio.to_thread(_market_data_get, path)
    except Exception as e:
        logger.error(f"Error fetching canvas context: {e}", extra={"trace_id": "market"})
        raise HTTPException(status_code=503, detail="Market data service unavailable")

    if resp.status_code == 400:
        raise HTTPException(
            status_code=400, detail=resp.json().get("detail", "invalid request")
        )
    if resp.status_code == 404:
        # Hyperliquid is the only venue this system carries. Asking for another
        # is a client error and says so; it is not a fault in market-data.
        raise HTTPException(
            status_code=404,
            detail=resp.json().get("error", "unsupported venue or symbol"),
        )
    if resp.status_code >= 500 or resp.status_code == 503:
        raise HTTPException(status_code=503, detail="Market data service unavailable")
    resp.raise_for_status()
    return resp.json()


@app.get("/state/market/depth")
async def get_market_depth(
    venue: str = "hyperliquid",
    symbol: str = "BTC-PERP",
):
    """The current L2 book as a cumulative ladder.

    A single poll rather than a series: the book is replaced wholesale each
    time, so there is nothing to draw across past candles. A book the venue did
    not return is a 503, never an empty ladder that would render as a market
    with no resting size.
    """
    path = f"/depth/{venue}/{symbol}"
    try:
        resp = await asyncio.to_thread(_market_data_get, path)
    except Exception as e:
        logger.error(f"Error fetching depth: {e}", extra={"trace_id": "market"})
        raise HTTPException(status_code=503, detail="Market data service unavailable")

    if resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=resp.json().get("error", "unsupported venue or symbol"),
        )
    if resp.status_code >= 500 or resp.status_code == 503:
        raise HTTPException(status_code=503, detail="Order book unavailable")
    resp.raise_for_status()
    return resp.json()


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


async def _record_and_annotate_states(status: dict) -> dict:
    """Persist state changes and attach how long each stage has held its state.

    Failures here are logged and swallowed: state ageing is operator context,
    and losing it must never take down the pipeline view itself.
    """
    nodes = status.get("nodes") or []
    if not state.pool or not nodes:
        return status

    now_s = int(time.time())
    observed = {node["id"]: node["status"] for node in nodes}

    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (node_id) node_id, new_state, entered_at
                FROM node_state_history
                ORDER BY node_id, entered_at DESC
                """
            )
            last_known = {r["node_id"]: r["new_state"] for r in rows}
            entered = {
                r["node_id"]: int(r["entered_at"].timestamp()) for r in rows
            }

            transitions = detect_transitions(observed, last_known, now_s)
            for transition in transitions:
                await conn.execute(
                    """
                    INSERT INTO node_state_history (node_id, previous_state, new_state)
                    VALUES ($1, $2, $3)
                    """,
                    transition.node_id,
                    transition.previous_state,
                    transition.new_state,
                )
                entered[transition.node_id] = transition.at_epoch_s

            # Recent changes per node, for flap detection.
            recent = await conn.fetch(
                """
                SELECT node_id, entered_at FROM node_state_history
                WHERE entered_at > now() - interval '15 minutes'
                """
            )
    except Exception as exc:
        logger.warning(f"state history unavailable: {exc}", extra={"trace_id": "pipeline"})
        return status

    by_node: dict[str, list] = {}
    for row in recent:
        by_node.setdefault(row["node_id"], []).append(
            {"at_epoch_s": int(row["entered_at"].timestamp())}
        )

    status["nodes"] = [
        annotate_node(
            node,
            entered.get(node["id"]),
            now_s,
            by_node.get(node["id"], []),
        )
        for node in nodes
    ]
    return status


@app.get("/state/integration-pipeline", tags=["pipeline"])
async def get_integration_pipeline():
    """Return live Tier A probes and honest optional-connector boundaries."""

    status = await collect_integration_pipeline(
        pool=state.pool,
        redis_client=await get_redis(),
        market_data_url=MARKET_DATA_URL,
        catalog_feature_count=len(regime_lab_engine.catalog.features),
    )
    return await _record_and_annotate_states(status)


@app.get("/state/integration-pipeline/history", tags=["pipeline"])
async def get_pipeline_state_history(node_id: Optional[str] = None, limit: int = Query(50, le=200)):
    """Recent state transitions, newest first."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT node_id, previous_state, new_state, entered_at
                FROM node_state_history
                WHERE ($1::text IS NULL OR node_id = $1)
                ORDER BY entered_at DESC
                LIMIT $2
                """,
                node_id,
                limit,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "schema_version": "node_state_history_v1",
        "transitions": [
            {
                "node_id": r["node_id"],
                "previous_state": r["previous_state"],
                "new_state": r["new_state"],
                "entered_at": r["entered_at"].isoformat(),
            }
            for r in rows
        ],
    }

# --- Private paper-only Regime Lab ---

async def _regime_lab_evidence(venue: str, symbol: str):
    normalized_venue = normalize_venue(venue)
    normalized_symbol = normalize_symbol(symbol)
    return await collect_live_feature_results(
        regime_lab_engine,
        MARKET_DATA_URL,
        normalized_venue,
        normalized_symbol,
    )


@app.get("/state/regime-lab/overview", tags=["regime-lab"])
async def get_regime_lab_overview(
    venue: str = Query("hyperliquid"),
    symbol: str = Query("BTC-PERP"),
):
    """Return source evidence, baseline math, and the current learning gate."""
    feature_results, source_status = await _regime_lab_evidence(venue, symbol)
    return regime_lab_engine.build_overview(feature_results, source_status)


@app.post("/state/regime-lab/evaluate", tags=["regime-lab"])
async def evaluate_regime_lab_experiment(
    request: RegimeLabExperimentRequest,
    venue: str = Query("hyperliquid"),
    symbol: str = Query("BTC-PERP"),
):
    """Validate and compare a draft without writing or activating it."""
    feature_results, source_status = await _regime_lab_evidence(venue, symbol)
    try:
        evaluation = regime_lab_engine.evaluate_request(
            request.model_dump(), feature_results
        )
    except RegimeLabValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    evaluation["source_status"] = source_status
    return evaluation


@app.post("/state/regime-lab/experiments", tags=["regime-lab"])
async def save_regime_lab_experiment(
    request: RegimeLabExperimentRequest,
    venue: str = Query("hyperliquid"),
    symbol: str = Query("BTC-PERP"),
):
    """Persist a draft experiment after the deterministic learning gates pass."""
    feature_results, source_status = await _regime_lab_evidence(venue, symbol)
    try:
        evaluation = regime_lab_engine.evaluate_request(
            request.model_dump(), feature_results
        )
    except RegimeLabValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not evaluation["learning_gate"]["complete"]:
        raise HTTPException(
            status_code=422,
            detail=(
                "Complete the weight-sum answer and write at least 20 characters "
                "explaining coverage before saving."
            ),
        )
    if not state.pool:
        raise HTTPException(
            status_code=503,
            detail="PostgreSQL is unavailable; evaluation succeeded but was not saved",
        )
    try:
        async with state.pool.acquire() as conn:
            async with conn.transaction():
                experiment_id = await persist_experiment(
                    conn, regime_lab_engine, request.model_dump(), evaluation
                )
    except Exception as exc:
        logger.error(
            f"Regime Lab persistence failed: {exc}",
            extra={"trace_id": "regime-lab"},
        )
        raise HTTPException(
            status_code=503,
            detail="Regime Lab persistence is unavailable; verify migrations",
        ) from exc
    return {
        "saved": True,
        "experiment_id": experiment_id,
        "status": "draft",
        "source_status": source_status,
        "activation_available": False,
        "evaluation": evaluation,
    }


@app.get("/state/regime-lab/experiments", tags=["regime-lab"])
async def list_regime_lab_experiments(limit: int = Query(20, ge=1, le=100)):
    """List immutable draft experiment records; no activation action is exposed."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="PostgreSQL is unavailable")
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select e.id, e.name, e.status, e.horizon, e.hypothesis,
                       e.evaluation_plan, e.results, e.created_at,
                       champion.version as baseline_version,
                       challenger.version as challenger_version
                from regime_experiments e
                join regime_rulebooks champion on champion.id=e.champion_rulebook_id
                join regime_rulebooks challenger on challenger.id=e.challenger_rulebook_id
                order by e.created_at desc
                limit $1
                """,
                limit,
            )
        return {"experiments": [dict(row) for row in rows], "count": len(rows)}
    except Exception as exc:
        logger.error(
            f"Regime Lab history failed: {exc}",
            extra={"trace_id": "regime-lab"},
        )
        raise HTTPException(
            status_code=503,
            detail="Regime Lab history is unavailable; verify migrations",
        ) from exc

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


# --- Free contextual provider feeds (non-authoritative) ---

@app.get("/state/context/overview", tags=["context"])
async def get_context_overview(
    refresh: bool = Query(False, description="Force a refresh of enabled context feeds")
):
    """Return cached secondary context without granting scoring or execution authority."""
    return await context_feed.fetch_overview(force_refresh=refresh)


@app.get("/state/context/status", tags=["context"])
async def get_context_status():
    """Return configuration and cache policy for secondary context feeds."""
    return context_feed.get_status()

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


# Paper rehearsal: preview, refuse, journal, with the execution gate shut.
# Registered last so it sees the same pool the rest of the app uses. It has no
# path to an execution service; see app/rehearsal.py.
from app.rehearsal import register as register_rehearsal  # noqa: E402

register_rehearsal(app, state)

# The skill gate measured the corrected way; see app/skill_gate.py.
from app.skill_gate import register as register_skill_gate  # noqa: E402

register_skill_gate(app, state)

# Evidence cards: what each candidate feature has earned; see app/evidence_cards.py.
from app.evidence_cards import register as register_evidence_cards  # noqa: E402

register_evidence_cards(app, state)

# Source cards: what each external source has earned; see app/source_cards.py.
from app.source_cards import register as register_source_cards  # noqa: E402

register_source_cards(app, state)

# The Thesis page's read model: the SOP's minimum valid thesis from evidence.
from app.thesis import register as register_thesis  # noqa: E402

register_thesis(
    app,
    state,
    market_data_url=MARKET_DATA_URL,
    calendar=lambda: context_feed.fetch_overview(force_refresh=False),
    evidence=_regime_lab_evidence,
)

# The Hermes fleet read model and directives; fed by the host bridge. See app/fleet.py.
from app.fleet import register as register_fleet  # noqa: E402

register_fleet(app, state)

# Thesis editions: the thesis for every symbol, frozen on the StrikeZone cadence.
from app.editions import register as register_editions  # noqa: E402

register_editions(
    app,
    state,
    market_data_url=MARKET_DATA_URL,
    calendar=lambda: context_feed.fetch_overview(force_refresh=False),
    evidence=_regime_lab_evidence,
)
