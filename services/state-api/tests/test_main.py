import json
import uuid
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime
from app.main import app, state

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

MOCK_EVENT = {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "ts": datetime.now(),
    "source": "drift",
    "kind": "market_snapshot",
    "symbol": "BTC-PERP",
    "timeframe": "1m",
    "payload": {"price": 100000.0},
}

MOCK_SIGNAL = {
    "id": "123e4567-e89b-12d3-a456-426614174001",
    "created_at": datetime.now(),
    "agent": "core_scorer",
    "symbol": "BTC-PERP",
    "timeframe": "1m",
    "kind": "funding_oi_squeeze",
    "confidence": 0.85,
    "dir": "long",
    "features": {"funding_rate": 0.0001},
}

MOCK_OPP = {
    "id": "123e4567-e89b-12d3-a456-426614174002",
    "symbol": "BTC-PERP",
    "timeframe": "1m",
    "bias": 2.5,
    "quality": 25.0,
    "dir": "long",
    "status": "new",
    "snapshot_ts": datetime.now(),
    "expires_at": None,
    "links": {"signal_ids": ["sig1"], "event_ids": ["evt1"]},
    "confluence": {},
}

# Full opportunity row as returned by the DB (all columns preview endpoint needs)
MOCK_OPP_ROW = {
    "id": "opp-btc-001",
    "symbol": "BTC-PERP",
    "status": "new",
    "quality": 75.0,
    "bias": 1.2,
    "dir": "long",
    "timeframe": "1m",
    "confluence": {},
    "links": {},
    "snapshot_ts": datetime.now(),
    "expires_at": None,
}

# Mock snapshot from market-data for one venue
def make_venue_snapshot(venue: str, oi_usd: float = 5_000_000.0, funding_now: float = 0.0001):
    return {
        "venue": venue,
        "symbol": "BTC-PERP",
        "ts": 1700000000000,
        "data_age_ms": 500,
        "available_metrics": [],
        "regimes": {},
        "sources": [],
        "oi": {"current_usd": oi_usd, "regime": "build", "horizons": {}},
        "funding": {
            "horizons": {"now": funding_now, "h8": 0.0001, "h24": 0.00009},
            "annualized_24h": 0.0,
            "regime": "neutral",
            "source": {"provider": venue, "endpoint": "/funding", "raw_rate": funding_now},
        },
        "microstructure": None,
        "orderbook": None,
        "liquidations": None,
        "volume": None,
    }


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()

    cm = AsyncMock()
    cm.__aenter__.return_value = conn
    cm.__aexit__.return_value = None

    pool.acquire.return_value = cm

    return pool, conn


# ===========================================================================
# Liveness / Health
# ===========================================================================

def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@patch("app.main.state")
def test_state_health_healthy(mock_state, mock_pool):
    pool, conn = mock_pool
    conn.fetchrow.return_value = {
        "last_evt": datetime(2025, 1, 1, 12, 0, 0),
        "last_sig": datetime(2025, 1, 1, 12, 0, 5),
    }
    mock_state.pool = pool
    state.pool = pool

    response = client.get("/state/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["postgres"] is True
    assert "last_event_ts" in data


# ===========================================================================
# Events / Signals
# ===========================================================================

@patch("app.main.state")
def test_get_events_latest(mock_state, mock_pool):
    pool, conn = mock_pool
    conn.fetch.return_value = [MOCK_EVENT]
    mock_state.pool = pool
    state.pool = pool

    response = client.get("/state/events/latest?symbol=BTC-PERP&tf=1m")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "BTC-PERP"
    assert data[0]["kind"] == "market_snapshot"


@patch("app.main.state")
def test_get_signals_latest(mock_state, mock_pool):
    pool, conn = mock_pool
    conn.fetch.return_value = [MOCK_SIGNAL]
    mock_state.pool = pool
    state.pool = pool

    response = client.get("/state/signals/latest?symbol=BTC-PERP&tf=1m")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "BTC-PERP"
    assert data[0]["dir"] == "long"


# ===========================================================================
# Opportunities
# ===========================================================================

@patch("app.main.state")
def test_get_opportunities(mock_state, mock_pool):
    pool, conn = mock_pool
    conn.fetch.return_value = [MOCK_OPP]
    mock_state.pool = pool
    state.pool = pool

    response = client.get("/state/opportunities?symbol=BTC-PERP")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "BTC-PERP"
    assert data[0]["bias"] == 2.5
    assert data[0]["links"]["signal_ids"] == ["sig1"]


@patch("app.main.state")
def test_get_opportunities_includes_expires_at(mock_state, mock_pool):
    """Opportunities must include server-side expires_at field (even if None)."""
    pool, conn = mock_pool
    conn.fetch.return_value = [MOCK_OPP]
    mock_state.pool = pool
    state.pool = pool

    response = client.get("/state/opportunities?symbol=BTC-PERP")
    assert response.status_code == 200
    data = response.json()
    assert "expires_at" in data[0]


# ===========================================================================
# Preview Action
# — Fixed: uses side_effect so each fetchrow call returns the right mock row
# ===========================================================================

@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true", "MIN_QUALITY": "1.0"})
def test_preview_action(mock_state, mock_http_cls, mock_pool):
    """Preview with valid BTC-PERP opportunity should be allowed by risk engine."""
    pool, conn = mock_pool
    # fetchrow call order: (1) opportunity, (2) existing decision, (3) latest signal
    conn.fetchrow.side_effect = [MOCK_OPP_ROW, None, None]
    # fetchval call order: (1) recent_decisions count, (2) daily_notional, (3) INSERT decision id
    conn.fetchval.side_effect = [0, 0.0, str(uuid.uuid4())]
    conn.execute.return_value = None
    mock_state.pool = pool
    state.pool = pool
    _make_preview_mock_no_positions(mock_http_cls)

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 5000.0}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["plan"]["symbol"] == "BTC-PERP"
    assert "risk_verdict" in data
    assert "allowed" in data["risk_verdict"]
    assert data["risk_verdict"]["allowed"] is True


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true"})
def test_preview_action_blocked(mock_state, mock_http_cls, mock_pool):
    """LUNA-PERP is on the DNT list — allowed=False with reason_code=DNT, status written to blocked."""
    pool, conn = mock_pool
    luna_row = {**MOCK_OPP_ROW, "id": "opp-luna-001", "symbol": "LUNA-PERP", "status": "new"}
    conn.fetchrow.side_effect = [luna_row, None, None]
    conn.fetchval.side_effect = [0, 0.0]  # recent_decisions, daily_notional; no decision insert for blocked path
    mock_state.pool = pool
    state.pool = pool

    # All HTTP calls fail — exposure=0, microstructure=None (DNT fires before exposure checks)
    mock_http_instance = AsyncMock()
    mock_http_instance.get.side_effect = Exception("connection refused")
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance

    payload = {"opportunity_id": "opp-luna-001", "size_usd": 100.0}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is False
    assert data["risk_verdict"]["reason_code"] == "DNT"
    assert "Do Not Trade" in data["risk_verdict"]["reason"] or "DNT" in data["risk_verdict"]["reason"]
    assert data["decision_id"] is None

    # DNT is non-transient → opportunity must be written to blocked status
    conn.execute.assert_called_once()
    call_sql = conn.execute.call_args.args[0]
    assert "blocked" in call_sql
    assert conn.execute.call_args.args[1] == "opp-luna-001"


@patch("app.main.state")
def test_preview_action_returns_cached_when_decision_exists(mock_state, mock_pool):
    """If a decision already exists for this opp+venue, preview returns the cached plan."""
    pool, conn = mock_pool
    existing_decision = {
        "id": str(uuid.uuid4()),
        "requested": json.dumps({"symbol": "BTC-PERP", "size_usd": 1000.0, "venue": "drift"}),
        "risk": json.dumps({"allowed": True, "reason": "ok"}),
    }
    # fetchrow call order: (1) opportunity, (2) existing decision → returns cached row
    conn.fetchrow.side_effect = [MOCK_OPP_ROW, existing_decision]
    mock_state.pool = pool
    state.pool = pool

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 1000.0}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["plan"]["symbol"] == "BTC-PERP"
    assert data["risk_verdict"]["allowed"] is True


# ===========================================================================
# Execute Action
# — Fixed: removed stale "placed_dry_run" / "execution_id" assertions
# — Added: contract shape test and decision-not-found test
# ===========================================================================

@patch("app.main.state")
def test_execute_action_decision_not_found(mock_state, mock_pool):
    """Execute must return 404 when the decision_id doesn't exist."""
    pool, conn = mock_pool
    # (1) idempotency check → no existing order, (2) decision lookup → not found
    conn.fetchrow.side_effect = [None, None]
    mock_state.pool = pool
    state.pool = pool

    payload = {"decision_id": "nonexistent-decision-id", "confirm": True}
    response = client.post("/actions/execute", json=payload)
    assert response.status_code == 404


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
def test_execute_action_result_contract(mock_state, mock_http_cls, mock_pool):
    """ExecutionResult contract: correct fields present, no legacy 'execution_id' field."""
    pool, conn = mock_pool
    decision_id = str(uuid.uuid4())

    mock_decision = {
        "id": decision_id,
        "opportunity_id": "opp-btc-001",
        "venue": "drift",
        "symbol": "BTC-PERP",
        "opp_status": "previewed",
        "quality": 75.0,
        "expires_at": None,
        "requested": json.dumps({"symbol": "BTC-PERP", "size_usd": 1000.0, "venue": "drift"}),
        "risk": json.dumps({"allowed": True}),
    }
    # fetchrow: (1) no existing order, (2) decision row, (3) latest signal
    conn.fetchrow.side_effect = [None, mock_decision, None]
    conn.execute.return_value = "INSERT 0 1"
    mock_state.pool = pool
    state.pool = pool

    # Mock exec-drift-svc response
    exec_resp_body = {
        "ok": True,
        "venue": "drift",
        "dry_run": True,
        "execution_enabled": True,
        "status": "placed",
        "order_id": str(uuid.uuid4()),
        "idempotency_key": decision_id,
        "request_payload": {},
        "response_payload": {},
        "ts": datetime.utcnow().isoformat(),
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = exec_resp_body

    mock_http_instance = AsyncMock()
    mock_http_instance.post.return_value = mock_resp
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance

    payload = {"decision_id": decision_id, "confirm": True}
    response = client.post("/actions/execute", json=payload)

    assert response.status_code == 200
    data = response.json()

    # Contract fields that must be present
    for field in ("ok", "status", "venue", "dry_run", "execution_enabled",
                  "idempotency_key", "request_payload", "response_payload", "ts"):
        assert field in data, f"Missing required field: {field}"

    # Legacy field that must NOT exist
    assert "execution_id" not in data

    # Status must be one of the valid contract values
    assert data["status"] in ("placed", "rejected", "error")


# ===========================================================================
# Snapshot Resilience Tests
# ===========================================================================

@patch("app.main.get_redis")
@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
def test_snapshot_returns_200_when_all_upstreams_down(mock_state, mock_http_cls, mock_get_redis, mock_pool):
    """Snapshot must return 200 with degraded=True when all optional upstreams are unavailable."""
    pool, conn = mock_pool
    conn.fetchrow.return_value = {
        "last_evt": datetime(2025, 1, 1, 12, 0, 0),
        "last_sig": datetime(2025, 1, 1, 12, 0, 5),
        "last_opp": datetime(2025, 1, 1, 12, 0, 10),
    }
    mock_state.pool = pool
    state.pool = pool

    mock_http_instance = AsyncMock()
    mock_http_instance.get.side_effect = Exception("Connection refused")
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance

    mock_get_redis.side_effect = Exception("Redis unavailable")

    response = client.get("/state/snapshot")
    assert response.status_code == 200
    data = response.json()
    assert data["degraded"] is True
    assert len(data["errors"]) > 0


@patch("app.main.get_redis")
@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
def test_snapshot_includes_per_service_health_map(mock_state, mock_http_cls, mock_get_redis, mock_pool):
    """Snapshot must include a service_health dict with per-service ok flags."""
    pool, conn = mock_pool
    conn.fetchrow.return_value = {"last_evt": None, "last_sig": None, "last_opp": None}
    mock_state.pool = pool
    state.pool = pool

    mock_http_instance = AsyncMock()
    mock_http_instance.get.side_effect = Exception("Connection refused")
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance

    mock_redis = AsyncMock()
    mock_redis.xlen.return_value = 0
    mock_get_redis.return_value = mock_redis

    response = client.get("/state/snapshot")
    assert response.status_code == 200
    data = response.json()
    assert "service_health" in data
    assert isinstance(data["service_health"], dict)
    assert "postgres" in data["service_health"]
    assert data["service_health"]["postgres"]["ok"] is True


@patch("app.main.get_redis")
@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
def test_snapshot_ingest_gateway_failure_does_not_crash(mock_state, mock_http_cls, mock_get_redis, mock_pool):
    """Ingest-gateway failure must not crash the snapshot — ingest_sources returns empty list."""
    pool, conn = mock_pool
    conn.fetchrow.return_value = {
        "last_evt": datetime(2025, 1, 1, 12, 0, 0),
        "last_sig": None,
        "last_opp": None,
    }
    mock_state.pool = pool
    state.pool = pool

    async def side_effect(url, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        if "ingest" in url:
            raise Exception("ingest-gateway down")
        resp.json.return_value = {}
        return resp

    mock_http_instance = AsyncMock()
    mock_http_instance.get.side_effect = side_effect
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance

    mock_redis = AsyncMock()
    mock_redis.xlen.return_value = 10
    mock_get_redis.return_value = mock_redis

    response = client.get("/state/snapshot")
    assert response.status_code == 200
    data = response.json()
    assert data["ingest_sources"] == []
    assert "ingest-gateway" in data["errors"]
    assert data["service_health"]["ingest-gateway"]["ok"] is False


@patch("app.main.get_redis")
@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
def test_snapshot_includes_snapshot_ts(mock_state, mock_http_cls, mock_get_redis, mock_pool):
    """Snapshot response must include a snapshot_ts timestamp."""
    pool, conn = mock_pool
    conn.fetchrow.return_value = {"last_evt": None, "last_sig": None, "last_opp": None}
    mock_state.pool = pool
    state.pool = pool

    mock_http_instance = AsyncMock()
    mock_http_instance.get.side_effect = Exception("down")
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance

    mock_redis = AsyncMock()
    mock_redis.xlen.return_value = 0
    mock_get_redis.return_value = mock_redis

    response = client.get("/state/snapshot")
    assert response.status_code == 200
    data = response.json()
    assert "snapshot_ts" in data
    assert data["snapshot_ts"] is not None


@patch("app.main.get_redis")
@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
def test_snapshot_not_degraded_when_all_ok(mock_state, mock_http_cls, mock_get_redis, mock_pool):
    """Snapshot degraded=False when all services succeed."""
    pool, conn = mock_pool
    conn.fetchrow.return_value = {
        "last_evt": datetime(2025, 1, 1, 12, 0, 0),
        "last_sig": datetime(2025, 1, 1, 12, 0, 5),
        "last_opp": datetime(2025, 1, 1, 12, 0, 10),
    }
    mock_state.pool = pool
    state.pool = pool

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}

    mock_http_instance = AsyncMock()
    mock_http_instance.get.return_value = mock_resp
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance

    mock_redis = AsyncMock()
    mock_redis.xlen.return_value = 5
    mock_get_redis.return_value = mock_redis

    response = client.get("/state/snapshot")
    assert response.status_code == 200
    data = response.json()
    assert data["degraded"] is False
    assert data["errors"] == {}


# ===========================================================================
# TTL / Opportunity Expiry Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_expire_stale_opportunities_updates_db():
    """expire_stale_opportunities must call UPDATE with correct status transitions."""
    from app.main import expire_stale_opportunities

    pool = MagicMock()
    conn = AsyncMock()
    conn.execute.return_value = "UPDATE 3"

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire.return_value = cm

    with patch("app.main.state") as mock_state:
        mock_state.pool = pool
        state.pool = pool

        _sleep_calls = 0

        async def _one_shot_sleep(t):
            nonlocal _sleep_calls
            _sleep_calls += 1
            if _sleep_calls >= 2:
                raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=_one_shot_sleep):
            try:
                await expire_stale_opportunities()
            except asyncio.CancelledError:
                pass

        assert conn.execute.called
        sql = conn.execute.call_args[0][0]
        assert "UPDATE opportunities" in sql
        assert "expired" in sql
        assert "'new'" in sql or "new" in sql


@patch("app.main.state")
def test_opportunities_endpoint_does_not_return_expired_by_default(mock_state, mock_pool):
    """Default status='new' query must not return expired records."""
    pool, conn = mock_pool
    conn.fetch.return_value = []
    mock_state.pool = pool
    state.pool = pool

    response = client.get("/state/opportunities")
    assert response.status_code == 200
    assert response.json() == []


@patch("app.main.state")
def test_opportunities_endpoint_can_query_expired_status(mock_state, mock_pool):
    """Clients can explicitly request status=expired to see what was expired server-side."""
    expired_opp = {**MOCK_OPP, "status": "expired"}
    pool, conn = mock_pool
    conn.fetch.return_value = [expired_opp]
    mock_state.pool = pool
    state.pool = pool

    response = client.get("/state/opportunities?status=expired")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "expired"


# ===========================================================================
# Market Snapshot — scope field
# ===========================================================================

@patch("app.main.httpx.AsyncClient")
def test_single_venue_snapshot_has_scope_single_venue(mock_http_cls):
    """Single-venue snapshot must declare scope='single_venue'."""
    snap = make_venue_snapshot("drift")
    # inject scope into upstream mock to verify state-api adds default if absent
    snap_without_scope = {k: v for k, v in snap.items() if k != "scope"}

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = snap_without_scope

    mock_http_instance = AsyncMock()
    mock_http_instance.get.return_value = mock_resp
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance

    response = client.get("/state/market/snapshot?venue=drift&symbol=BTC-PERP")
    assert response.status_code == 200
    data = response.json()
    assert data.get("scope") == "single_venue"


# ===========================================================================
# Market Aggregate Tests
# ===========================================================================

def _make_aggregate_http_mock(mock_http_cls, venue_responses: dict):
    """
    venue_responses: {venue: snapshot_dict or Exception or int(status_code)}
    Returns a configured mock for httpx.AsyncClient.
    """
    async def side_effect(url, timeout=None):
        for venue, result in venue_responses.items():
            if venue in url:
                if isinstance(result, Exception):
                    raise result
                resp = MagicMock()
                if isinstance(result, int):
                    resp.status_code = result
                    resp.json.return_value = {}
                else:
                    resp.status_code = 200
                    resp.json.return_value = result
                return resp
        resp = MagicMock()
        resp.status_code = 404
        resp.json.return_value = {}
        return resp

    mock_http_instance = AsyncMock()
    mock_http_instance.get.side_effect = side_effect
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance


@patch("app.main.httpx.AsyncClient")
def test_market_aggregate_scope_is_all_venues(mock_http_cls):
    """Aggregate response must always declare scope='all_venues'."""
    _make_aggregate_http_mock(mock_http_cls, {
        "drift": make_venue_snapshot("drift"),
        "hyperliquid": make_venue_snapshot("hyperliquid"),
    })

    response = client.get("/state/market/aggregate/BTC-PERP")
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "all_venues"


@patch("app.main.httpx.AsyncClient")
def test_market_aggregate_all_venues_available(mock_http_cls):
    """With both venues up: partial=False, OI total sums both, spread computed."""
    _make_aggregate_http_mock(mock_http_cls, {
        "drift": make_venue_snapshot("drift", oi_usd=3_000_000.0, funding_now=0.0001),
        "hyperliquid": make_venue_snapshot("hyperliquid", oi_usd=2_000_000.0, funding_now=0.00015),
    })

    response = client.get("/state/market/aggregate/BTC-PERP")
    assert response.status_code == 200
    data = response.json()

    assert data["partial"] is False
    assert data["oi"]["total_usd"] == pytest.approx(5_000_000.0)
    assert set(data["oi"]["contributing_venues"]) == {"drift", "hyperliquid"}
    assert data["oi"]["missing_venues"] == []
    assert data["funding"]["spread"] is not None
    assert data["funding"]["spread"] == pytest.approx(0.5)  # |0.0001 - 0.00015| * 10000 = 0.5 bps


@patch("app.main.httpx.AsyncClient")
def test_market_aggregate_one_venue_down(mock_http_cls):
    """When one venue is unavailable: partial=True, OI only counts available venue."""
    _make_aggregate_http_mock(mock_http_cls, {
        "drift": make_venue_snapshot("drift", oi_usd=3_000_000.0, funding_now=0.0001),
        "hyperliquid": Exception("connection refused"),
    })

    response = client.get("/state/market/aggregate/BTC-PERP")
    assert response.status_code == 200
    data = response.json()

    assert data["partial"] is True
    assert data["oi"]["total_usd"] == pytest.approx(3_000_000.0)
    assert data["oi"]["contributing_venues"] == ["drift"]
    assert "hyperliquid" in data["oi"]["missing_venues"]
    # Spread must be None — only 1 funding venue
    assert data["funding"]["spread"] is None


@patch("app.main.httpx.AsyncClient")
def test_market_aggregate_both_venues_down(mock_http_cls):
    """Both venues down: partial=True, OI total=0, empty contributing list."""
    _make_aggregate_http_mock(mock_http_cls, {
        "drift": Exception("down"),
        "hyperliquid": Exception("down"),
    })

    response = client.get("/state/market/aggregate/BTC-PERP")
    assert response.status_code == 200
    data = response.json()

    assert data["partial"] is True
    assert data["oi"]["total_usd"] == 0.0
    assert data["oi"]["contributing_venues"] == []
    assert set(data["oi"]["missing_venues"]) == {"drift", "hyperliquid"}
    assert data["funding"]["spread"] is None


@patch("app.main.httpx.AsyncClient")
def test_market_aggregate_per_venue_always_present(mock_http_cls):
    """per_venue must always contain an entry for every known venue — None if unavailable."""
    _make_aggregate_http_mock(mock_http_cls, {
        "drift": make_venue_snapshot("drift"),
        "hyperliquid": Exception("down"),
    })

    response = client.get("/state/market/aggregate/BTC-PERP")
    assert response.status_code == 200
    data = response.json()

    # Both keys must be present
    assert "drift" in data["per_venue"]
    assert "hyperliquid" in data["per_venue"]
    # Available venue has real data
    assert data["per_venue"]["drift"] is not None
    # Unavailable venue is None — not missing from dict
    assert data["per_venue"]["hyperliquid"] is None


@patch("app.main.httpx.AsyncClient")
def test_market_aggregate_venue_availability_flags(mock_http_cls):
    """venue_availability must correctly label each venue as available or not."""
    _make_aggregate_http_mock(mock_http_cls, {
        "drift": make_venue_snapshot("drift"),
        "hyperliquid": 404,
    })

    response = client.get("/state/market/aggregate/BTC-PERP")
    assert response.status_code == 200
    data = response.json()

    avail_map = {va["venue"]: va for va in data["venue_availability"]}
    assert avail_map["drift"]["available"] is True
    assert avail_map["hyperliquid"]["available"] is False
    assert avail_map["hyperliquid"]["error"] == "no_snapshot"


@patch("app.main.httpx.AsyncClient")
def test_market_aggregate_funding_spread_none_when_one_venue(mock_http_cls):
    """Funding spread must be None when fewer than 2 venues have live rate data."""
    drift_snap = make_venue_snapshot("drift", funding_now=0.0001)
    # Hyperliquid: no funding data at all
    hl_snap = make_venue_snapshot("hyperliquid")
    hl_snap["funding"] = None

    _make_aggregate_http_mock(mock_http_cls, {
        "drift": drift_snap,
        "hyperliquid": hl_snap,
    })

    response = client.get("/state/market/aggregate/BTC-PERP")
    assert response.status_code == 200
    data = response.json()
    assert data["funding"]["spread"] is None
    assert "drift" in data["funding"]["available_venues"]
    assert "hyperliquid" in data["funding"]["missing_venues"]


@patch("app.main.httpx.AsyncClient")
def test_market_aggregate_oi_regime_per_venue(mock_http_cls):
    """OI regime per venue must be populated when data is available."""
    _make_aggregate_http_mock(mock_http_cls, {
        "drift": make_venue_snapshot("drift"),
        "hyperliquid": make_venue_snapshot("hyperliquid"),
    })

    response = client.get("/state/market/aggregate/BTC-PERP")
    assert response.status_code == 200
    data = response.json()

    assert data["oi"]["regime_per_venue"]["drift"] is not None
    assert data["oi"]["regime_per_venue"]["hyperliquid"] is not None


# ===========================================================================
# Preview Action — Exposure Data Fix (Phase 3F-2)
# Tests that preview_action uses size_usd (not notional) and correct exec URLs
# ===========================================================================

def _make_preview_http_mock(mock_http_cls, positions: list, venue: str = "hyperliquid"):
    """
    Build an httpx mock for preview_action that returns positions from the
    correct exec service URL and a market snapshot (no microstructure).
    The URL match uses the canonical exec service hostname so tests validate
    the URL fix as well.
    """
    hl_url_fragment = "exec-hl-svc"
    drift_url_fragment = "exec-drift-svc"
    market_url_fragment = "market-data"

    async def side_effect(url, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        if market_url_fragment in url:
            resp.json.return_value = {}
            return resp
        if (venue == "hyperliquid" and hl_url_fragment in url) or \
           (venue == "drift" and drift_url_fragment in url):
            resp.json.return_value = positions
            return resp
        # Any unknown URL → 404 (catches old broken URLs)
        resp.status_code = 404
        resp.json.return_value = {}
        return resp

    mock_http_instance = AsyncMock()
    mock_http_instance.get.side_effect = side_effect
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true"})
def test_preview_action_exposure_uses_size_usd(mock_state, mock_http_cls, mock_pool):
    """
    Phase 3F-2: preview_action must read size_usd from positions, not notional.

    Position has size_usd=5000 and notional=0 (old wrong field).
    Expected: allowed=True (5000 + 5000 request = $10k < $25k limit).

    With old broken code: notional=0 → symbol_exposure_usd=0 → allowed=True (same outcome).
    With new code:        size_usd=5000 → symbol_exposure_usd=5000 → allowed=True (same outcome).

    This test confirms no crash and correct field parsing at low exposure.
    The veto test below (exposure_too_high) is the decisive proof that size_usd is
    actually being read: at $30k notional=0 would pass, but size_usd=$30k must veto.
    """
    pool, conn = mock_pool
    high_quality_row = {**MOCK_OPP_ROW, "quality": 90.0, "bias": 3.5}
    conn.fetchrow.side_effect = [high_quality_row, None, None]
    conn.fetchval.side_effect = [0, 0.0, str(uuid.uuid4())]
    conn.execute.return_value = None
    mock_state.pool = pool
    state.pool = pool

    positions = [{
        "symbol": "BTC-PERP",
        "size_usd": 5000.0,  # $5k + $5k request = $10k < $25k limit → should pass
        "notional": 0,        # old wrong field — confirmed not used
        "venue": "hyperliquid",
    }]
    _make_preview_http_mock(mock_http_cls, positions, venue="hyperliquid")

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 5000.0, "venue": "hyperliquid"}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is True
    assert data["risk_verdict"]["reason_code"] == "OK"


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true"})
def test_preview_action_exposure_too_high_vetoes(mock_state, mock_http_cls, mock_pool):
    """
    Phase 3F-2: When BTC-PERP exposure is $30,000 (> $25k limit), RiskGuardian
    must fire EXPOSURE_TOO_HIGH. This only reaches the check because size_usd is
    read correctly (with notional it would be 0 and the check would pass).
    """
    pool, conn = mock_pool
    # High-quality opportunity so MIN_QUALITY does not veto first
    high_quality_row = {**MOCK_OPP_ROW, "quality": 90.0, "bias": 3.5}
    conn.fetchrow.side_effect = [high_quality_row, None, None]
    conn.fetchval.side_effect = [0, 0.0]
    conn.execute.return_value = None
    mock_state.pool = pool
    state.pool = pool

    positions = [{"symbol": "BTC-PERP", "size_usd": 30000.0, "venue": "hyperliquid"}]
    _make_preview_http_mock(mock_http_cls, positions, venue="hyperliquid")

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 5000.0, "venue": "hyperliquid"}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is False
    assert "EXPOSURE" in data["risk_verdict"]["reason"].upper()


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true"})
def test_preview_action_positions_unavailable_does_not_block(mock_state, mock_http_cls, mock_pool):
    """
    Phase 3F-2: When the exec service is unreachable, preview_action must still
    return a valid response (exposure defaults to 0 — no veto from exposure check).
    """
    pool, conn = mock_pool
    # Use high_quality_row so MIN_QUALITY does not veto before reaching exposure checks
    high_quality_row = {**MOCK_OPP_ROW, "quality": 90.0, "bias": 3.5}
    conn.fetchrow.side_effect = [high_quality_row, None, None]
    conn.fetchval.side_effect = [0, 0.0, str(uuid.uuid4())]
    conn.execute.return_value = None
    mock_state.pool = pool
    state.pool = pool

    # All HTTP calls fail — exec service and market-data both down
    mock_http_instance = AsyncMock()
    mock_http_instance.get.side_effect = Exception("connection refused")
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 5000.0}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    # With no exposure data, the check passes (exposure_penalty = 0)
    assert data["risk_verdict"]["allowed"] is True


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
def test_preview_uses_canonical_urls_for_both_venues(mock_state, mock_http_cls, mock_pool):
    """
    Phase 3F-3: preview_action now calls _fetch_aggregated_positions which queries
    ALL known exec services (drift + hyperliquid). Verify both canonical URLs are hit
    and neither old broken pattern (exec-hyperliquid-svc, /exec/hy/, /exec/dr/) appears.
    """
    pool, conn = mock_pool
    conn.fetchrow.side_effect = [MOCK_OPP_ROW, None, None]
    conn.fetchval.side_effect = [0, 0.0, str(uuid.uuid4())]
    conn.execute.return_value = None
    mock_state.pool = pool
    state.pool = pool

    called_urls = []

    async def tracking_get(url, timeout=None):
        called_urls.append(url)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = []
        return resp

    mock_http_instance = AsyncMock()
    mock_http_instance.get.side_effect = tracking_get
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 5000.0, "venue": "hyperliquid"}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200

    exec_urls = [u for u in called_urls if "exec" in u and "market" not in u]
    # Both venues must be queried (cross-venue aggregation)
    assert len(exec_urls) == 2, f"Expected 2 exec service calls (both venues), got: {exec_urls}"
    exec_url_str = " ".join(exec_urls)
    assert "exec-hl-svc" in exec_url_str
    assert "/exec/hl/positions" in exec_url_str
    assert "exec-drift-svc" in exec_url_str
    assert "/exec/drift/positions" in exec_url_str
    # Old broken patterns must be absent
    assert "exec-hyperliquid-svc" not in exec_url_str
    assert "/exec/hy/" not in exec_url_str
    assert "/exec/dr/" not in exec_url_str


# ===========================================================================
# Phase 3F-3: Blocked Lifecycle Tests
# ===========================================================================

def _make_preview_mock_no_positions(mock_http_cls):
    """HTTP mock for preview tests where positions are irrelevant (all fail)."""
    mock_http_instance = AsyncMock()
    mock_http_instance.get.side_effect = Exception("connection refused")
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true"})
def test_preview_non_transient_min_quality_writes_blocked(mock_state, mock_http_cls, mock_pool):
    """
    Phase 3F-3: MIN_QUALITY is a non-transient rejection.
    Opportunity quality is a fixed snapshot property — it won't improve with time.
    Must write status='blocked' and return decision_id=None.
    """
    pool, conn = mock_pool
    low_quality_row = {**MOCK_OPP_ROW, "quality": 20.0, "status": "new"}  # below MIN_QUALITY=50
    conn.fetchrow.side_effect = [low_quality_row, None, None]
    conn.fetchval.side_effect = [0, 0.0]
    mock_state.pool = pool
    state.pool = pool
    _make_preview_mock_no_positions(mock_http_cls)

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 1000.0}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is False
    assert data["risk_verdict"]["reason_code"] == "MIN_QUALITY"
    assert data["decision_id"] is None

    # MIN_QUALITY is non-transient → blocked write must happen
    conn.execute.assert_called_once()
    assert "blocked" in conn.execute.call_args.args[0]


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
def test_preview_transient_exec_disabled_does_not_write_blocked(mock_state, mock_http_cls, mock_pool):
    """
    Phase 3F-3: EXEC_DISABLED is transient — the global kill-switch can be re-enabled.
    Must NOT write 'blocked' status; opportunity stays in 'new' for retry when gate opens.
    """
    pool, conn = mock_pool
    conn.fetchrow.side_effect = [MOCK_OPP_ROW, None, None]
    conn.fetchval.side_effect = [0, 0.0]
    mock_state.pool = pool
    state.pool = pool
    _make_preview_mock_no_positions(mock_http_cls)

    # EXECUTION_ENABLED not set → defaults to false → EXEC_DISABLED fires
    payload = {"opportunity_id": "opp-btc-001", "size_usd": 1000.0}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is False
    assert data["risk_verdict"]["reason_code"] == "EXEC_DISABLED"
    # Transient rejection — must NOT write blocked
    conn.execute.assert_not_called()


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true"})
def test_preview_transient_cooldown_does_not_write_blocked(mock_state, mock_http_cls, mock_pool):
    """
    Phase 3F-3: COOLDOWN is transient — rate limit clears over time.
    Must NOT write 'blocked'; opportunity can be retried after cooldown expires.
    """
    pool, conn = mock_pool
    # Use high_quality_row so MIN_QUALITY does not veto before reaching COOLDOWN check
    high_quality_row = {**MOCK_OPP_ROW, "quality": 90.0, "bias": 3.5}
    conn.fetchrow.side_effect = [high_quality_row, None, None]
    conn.fetchval.side_effect = [3, 0.0]  # recent_decisions=3, daily_notional=0 → COOLDOWN fires
    mock_state.pool = pool
    state.pool = pool
    _make_preview_mock_no_positions(mock_http_cls)

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 1000.0}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is False
    assert data["risk_verdict"]["reason_code"] == "COOLDOWN"
    conn.execute.assert_not_called()


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true"})
def test_preview_blocked_does_not_downgrade_previewed_status(mock_state, mock_http_cls, mock_pool):
    """
    Phase 3F-3: DUPLICATE fires when opportunity status is already 'previewed'.
    Even though this IS a non-transient-ish veto, DUPLICATE is excluded from _NON_TRANSIENT_CODES
    because writing 'blocked' over a higher-lifecycle status would be a downgrade.
    The guard 'WHERE status = new' in the SQL also prevents it, but the reason_code
    classification is the primary defense.
    """
    pool, conn = mock_pool
    previewed_row = {**MOCK_OPP_ROW, "status": "previewed"}
    conn.fetchrow.side_effect = [previewed_row, None, None]
    conn.fetchval.side_effect = [0, 0.0]
    mock_state.pool = pool
    state.pool = pool
    _make_preview_mock_no_positions(mock_http_cls)

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 1000.0}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is False
    assert data["risk_verdict"]["reason_code"] == "DUPLICATE"
    # Must NOT write blocked — would downgrade a correctly-previewed opportunity
    conn.execute.assert_not_called()


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true"})
def test_preview_allowed_writes_previewed_not_blocked(mock_state, mock_http_cls, mock_pool):
    """
    Phase 3F-3: Regression guard — normal allowed preview must still write 'previewed',
    not 'blocked'. The blocked path must not interfere with the happy path.
    """
    pool, conn = mock_pool
    high_quality_row = {**MOCK_OPP_ROW, "quality": 90.0, "bias": 3.5}
    conn.fetchrow.side_effect = [high_quality_row, None, None]
    conn.fetchval.side_effect = [0, 0.0, str(uuid.uuid4())]
    conn.execute.return_value = None
    mock_state.pool = pool
    state.pool = pool
    _make_preview_mock_no_positions(mock_http_cls)

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 1000.0}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is True
    assert data["decision_id"] is not None

    # The SQL written must be the 'previewed' update, not 'blocked'
    conn.execute.assert_called_once()
    call_sql = conn.execute.call_args.args[0]
    assert "previewed" in call_sql
    assert "blocked" not in call_sql


# ===========================================================================
# Phase 3F-3: TTL / Expiry Interaction with Blocked Status
# ===========================================================================

@pytest.mark.asyncio
async def test_expire_stale_does_not_touch_blocked():
    """
    Phase 3F-3: The TTL expiry SQL must only target 'new' and 'previewed' statuses.
    'blocked' rows must never be swept to 'expired' by the background task.
    """
    from app.main import expire_stale_opportunities

    pool = MagicMock()
    conn = AsyncMock()
    conn.execute.return_value = "UPDATE 0"

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire.return_value = cm

    with patch("app.main.state") as mock_state:
        mock_state.pool = pool
        state.pool = pool

        _sleep_calls = 0

        async def _one_shot_sleep(t):
            nonlocal _sleep_calls
            _sleep_calls += 1
            if _sleep_calls >= 2:
                raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=_one_shot_sleep):
            try:
                await expire_stale_opportunities()
            except asyncio.CancelledError:
                pass

    assert conn.execute.called
    sql = conn.execute.call_args[0][0]
    # Only 'new' and 'previewed' should be in the WHERE clause
    assert "new" in sql
    assert "previewed" in sql
    # 'blocked' must NOT appear — blocked rows are permanently excluded from TTL sweep
    assert "blocked" not in sql.lower()


# ===========================================================================
# Phase 3F-3: Cross-Venue Exposure / Account Risk Load Tests
# ===========================================================================

def _make_cross_venue_http_mock(mock_http_cls, hl_positions, drift_positions):
    """
    Build an httpx mock that returns venue-specific positions from the correct URLs.
    Market-data returns empty (no microstructure needed for these tests).
    """
    async def side_effect(url, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        if "market-data" in url:
            resp.json.return_value = {}
            return resp
        if "exec-hl-svc" in url:
            resp.json.return_value = hl_positions
            return resp
        if "exec-drift-svc" in url:
            resp.json.return_value = drift_positions
            return resp
        resp.status_code = 404
        resp.json.return_value = {}
        return resp

    mock_http_instance = AsyncMock()
    mock_http_instance.get.side_effect = side_effect
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true"})
def test_preview_exposure_sums_same_symbol_across_venues(mock_state, mock_http_cls, mock_pool):
    """
    Phase 3F-3: Symbol exposure must SUM positions from all venues, not take last-write.
    $15k on hyperliquid + $10k on drift = $25k total. Adding $5k request = $30k > $25k limit.
    With old overwrite logic: drift ($10k) wins → $10k + $5k = $15k → passes (wrong).
    With correct sum: $25k + $5k = $30k → EXPOSURE_TOO_HIGH fires (correct).
    """
    pool, conn = mock_pool
    high_quality_row = {**MOCK_OPP_ROW, "quality": 90.0, "bias": 3.5}
    conn.fetchrow.side_effect = [high_quality_row, None, None]
    conn.fetchval.side_effect = [0, 0.0]
    mock_state.pool = pool
    state.pool = pool

    hl_positions = [{"symbol": "BTC-PERP", "size_usd": 15000.0, "venue": "hyperliquid"}]
    drift_positions = [{"symbol": "BTC-PERP", "size_usd": 10000.0, "venue": "drift"}]
    _make_cross_venue_http_mock(mock_http_cls, hl_positions, drift_positions)

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 5000.0, "venue": "hyperliquid"}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is False
    assert data["risk_verdict"]["reason_code"] == "EXPOSURE_TOO_HIGH"


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true"})
def test_preview_cross_venue_position_included_in_exposure(mock_state, mock_http_cls, mock_pool):
    """
    Phase 3F-3: A position held only on the non-requested venue must still count toward
    symbol exposure. If $20k is on drift and we're previewing a hyperliquid trade for $6k:
    $20k + $6k = $26k > $25k → EXPOSURE_TOO_HIGH. Without cross-venue aggregation, hl
    positions = [] → $0 + $6k = $6k → passes (wrong).
    """
    pool, conn = mock_pool
    high_quality_row = {**MOCK_OPP_ROW, "quality": 90.0, "bias": 3.5}
    conn.fetchrow.side_effect = [high_quality_row, None, None]
    conn.fetchval.side_effect = [0, 0.0]
    mock_state.pool = pool
    state.pool = pool

    # Position on drift only, requesting on hyperliquid
    hl_positions = []
    drift_positions = [{"symbol": "BTC-PERP", "size_usd": 20000.0, "venue": "drift"}]
    _make_cross_venue_http_mock(mock_http_cls, hl_positions, drift_positions)

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 6000.0, "venue": "hyperliquid"}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is False
    assert data["risk_verdict"]["reason_code"] == "EXPOSURE_TOO_HIGH"


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true"})
def test_preview_account_risk_load_uses_account_equity_usd_env(mock_state, mock_http_cls, mock_pool):
    """
    Phase 3F-3: Account risk load calculation uses ACCOUNT_EQUITY_USD module constant.
    With $40k total positions and default $50k equity: ratio = 0.80 which equals the
    MARGIN_STRESS_THRESHOLD (0.80) — not > threshold so MARGIN_STRESS does not fire.
    With $40,001 total (just over): ratio > 0.80 → MARGIN_STRESS fires.
    This test verifies the $50k denominator is being used (not a different magic number).
    """
    pool, conn = mock_pool
    high_quality_row = {**MOCK_OPP_ROW, "quality": 90.0, "bias": 3.5}
    conn.fetchrow.side_effect = [high_quality_row, None, None]
    conn.fetchval.side_effect = [0, 0.0]
    mock_state.pool = pool
    state.pool = pool

    # $41k total = 41000/50000 = 0.82 > 0.80 threshold → MARGIN_STRESS fires
    hl_positions = [{"symbol": "ETH-PERP", "size_usd": 21000.0, "venue": "hyperliquid"}]
    drift_positions = [{"symbol": "SOL-PERP", "size_usd": 20000.0, "venue": "drift"}]
    _make_cross_venue_http_mock(mock_http_cls, hl_positions, drift_positions)

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 1000.0, "venue": "hyperliquid"}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is False
    assert data["risk_verdict"]["reason_code"] == "MARGIN_STRESS"


def test_risk_limits_endpoint_includes_account_equity_usd():
    """
    Phase 3F-3: /state/risk/limits must include account_equity_usd so the capital base
    assumption is discoverable from the system, not buried as a magic number.
    """
    response = client.get("/state/risk/limits")
    assert response.status_code == 200
    data = response.json()
    assert "account_equity_usd" in data
    assert isinstance(data["account_equity_usd"], float)
    assert data["account_equity_usd"] > 0


@pytest.mark.asyncio
async def test_fetch_aggregated_positions_helper_calls_both_venues():
    """
    Phase 3F-3: _fetch_aggregated_positions must call all entries in _EXEC_POSITIONS_URLS,
    combining results from available venues and silently excluding failures.
    """
    from app.main import _fetch_aggregated_positions

    hl_data = [{"symbol": "BTC-PERP", "size_usd": 15000.0, "venue": "hyperliquid"}]
    drift_data = [{"symbol": "ETH-PERP", "size_usd": 5000.0, "venue": "drift"}]

    called_urls = []

    async def mock_get(url, timeout=None):
        called_urls.append(url)
        resp = MagicMock()
        resp.status_code = 200
        if "exec-hl-svc" in url:
            resp.json.return_value = hl_data
        elif "exec-drift-svc" in url:
            resp.json.return_value = drift_data
        else:
            resp.status_code = 404
            resp.json.return_value = []
        return resp

    mock_client = AsyncMock()
    mock_client.get.side_effect = mock_get

    result = await _fetch_aggregated_positions(mock_client)

    # Both venues called
    assert any("exec-hl-svc" in u for u in called_urls)
    assert any("exec-drift-svc" in u for u in called_urls)

    # Results combined
    assert len(result) == 2
    symbols = {p["symbol"] for p in result}
    assert "BTC-PERP" in symbols
    assert "ETH-PERP" in symbols


@pytest.mark.asyncio
async def test_fetch_aggregated_positions_helper_partial_on_failure():
    """
    Phase 3F-3: If one venue fails, _fetch_aggregated_positions returns partial results
    from the remaining venues rather than failing the entire call.
    """
    from app.main import _fetch_aggregated_positions

    hl_data = [{"symbol": "BTC-PERP", "size_usd": 15000.0}]

    async def mock_get(url, timeout=None):
        if "exec-hl-svc" in url:
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = hl_data
            return resp
        raise Exception("exec-drift-svc connection refused")

    mock_client = AsyncMock()
    mock_client.get.side_effect = mock_get

    result = await _fetch_aggregated_positions(mock_client)

    # Partial result — only HL positions returned, no error raised
    assert len(result) == 1
    assert result[0]["symbol"] == "BTC-PERP"


# ===========================================================================
# Phase 1: Daily Notional Enforcement
# ===========================================================================

@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true", "DAILY_NOTIONAL_LIMIT": "50000"})
def test_preview_daily_notional_blocks_when_limit_exceeded(mock_state, mock_http_cls, mock_pool):
    """
    Phase 1: When daily notional used ($48k) + request size ($3k) > limit ($50k),
    RiskGuardian must fire LIMIT_DAILY and reject the preview.
    This test proves the enforcement is wired end-to-end, not just displayed.
    """
    pool, conn = mock_pool
    high_quality_row = {**MOCK_OPP_ROW, "quality": 90.0, "bias": 3.5}
    conn.fetchrow.side_effect = [high_quality_row, None, None]
    # recent_decisions=0, daily_notional_usd=$48k (near limit)
    conn.fetchval.side_effect = [0, 48000.0]
    mock_state.pool = pool
    state.pool = pool
    _make_preview_mock_no_positions(mock_http_cls)

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 3000.0}  # $48k + $3k = $51k > $50k
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is False
    assert data["risk_verdict"]["reason_code"] == "LIMIT_DAILY"
    assert "daily" in data["risk_verdict"]["reason"].lower()
    assert data["decision_id"] is None


@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true", "DAILY_NOTIONAL_LIMIT": "50000"})
def test_preview_daily_notional_passes_when_below_limit(mock_state, mock_http_cls, mock_pool):
    """
    Phase 1: When daily notional used ($45k) + request size ($4k) = $49k < limit ($50k),
    LIMIT_DAILY must NOT fire — preview proceeds through remaining checks.
    """
    pool, conn = mock_pool
    high_quality_row = {**MOCK_OPP_ROW, "quality": 90.0, "bias": 3.5}
    conn.fetchrow.side_effect = [high_quality_row, None, None]
    # recent_decisions=0, daily_notional_usd=$45k (under limit)
    conn.fetchval.side_effect = [0, 45000.0, str(uuid.uuid4())]
    conn.execute.return_value = None
    mock_state.pool = pool
    state.pool = pool
    _make_preview_mock_no_positions(mock_http_cls)

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 4000.0}  # $45k + $4k = $49k < $50k
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is True
    assert data["risk_verdict"]["reason_code"] == "OK"


@patch("app.main.DAILY_NOTIONAL_LIMIT", 0.0)
@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true", "DAILY_NOTIONAL_LIMIT": "0"})
def test_preview_daily_notional_zero_limit_disables_check(mock_state, mock_http_cls, mock_pool):
    """
    Phase 1: DAILY_NOTIONAL_LIMIT=0 means no daily cap. Even with $999k in daily notional,
    LIMIT_DAILY must not fire (limit=0 means disabled/unconfigured).
    """
    pool, conn = mock_pool
    high_quality_row = {**MOCK_OPP_ROW, "quality": 90.0, "bias": 3.5}
    conn.fetchrow.side_effect = [high_quality_row, None, None]
    conn.fetchval.side_effect = [0, 999000.0, str(uuid.uuid4())]
    conn.execute.return_value = None
    mock_state.pool = pool
    state.pool = pool
    _make_preview_mock_no_positions(mock_http_cls)

    payload = {"opportunity_id": "opp-btc-001", "size_usd": 1000.0}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["reason_code"] != "LIMIT_DAILY"


# ===========================================================================
# Phase 2: Blocked Rejection Stored in links
# ===========================================================================

@patch("app.main.httpx.AsyncClient")
@patch("app.main.state")
@patch.dict("os.environ", {"EXECUTION_ENABLED": "true"})
def test_blocked_rejection_stores_reason_in_links(mock_state, mock_http_cls, mock_pool):
    """
    Phase 2: When a non-transient rejection writes 'blocked', the reason_code and human
    reason must be stored in links.rejection so the cockpit can surface why the
    opportunity was blocked without a separate DB query.
    """
    pool, conn = mock_pool
    luna_row = {**MOCK_OPP_ROW, "id": "opp-luna-002", "symbol": "LUNA-PERP", "status": "new"}
    conn.fetchrow.side_effect = [luna_row, None, None]
    conn.fetchval.side_effect = [0, 0.0]
    mock_state.pool = pool
    state.pool = pool

    mock_http_instance = AsyncMock()
    mock_http_instance.get.side_effect = Exception("connection refused")
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = mock_http_instance

    payload = {"opportunity_id": "opp-luna-002", "size_usd": 100.0}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["reason_code"] == "DNT"

    # Verify execute was called with rejection data stored in links
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args.args
    assert "blocked" in call_args[0]
    assert "rejection" in call_args[0]
    assert "jsonb_set" in call_args[0]
    # Third arg is the JSON rejection payload
    import json as json_module
    rejection = json_module.loads(call_args[2])
    assert rejection["reason_code"] == "DNT"
    assert "Do Not Trade" in rejection["reason"] or "DNT" in rejection["reason"]


# ===========================================================================
# Phase 3: Cleanup Endpoint
# ===========================================================================

@patch("app.main.state")
def test_cleanup_endpoint_dry_run_returns_count(mock_state, mock_pool):
    """
    Phase 3: GET /admin/cleanup?dry_run=true must return the count of rows
    that WOULD be deleted without actually deleting anything.
    """
    pool, conn = mock_pool
    conn.fetchrow.return_value = {"count": 7}
    mock_state.pool = pool
    state.pool = pool

    response = client.post("/admin/cleanup?dry_run=true&days=30")

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is True
    assert data["would_delete"] == 7
    assert data["older_than_days"] == 30
    # No actual DELETE executed in dry_run mode
    conn.execute.assert_not_called()


@patch("app.main.state")
def test_cleanup_endpoint_deletes_when_dry_run_false(mock_state, mock_pool):
    """
    Phase 3: POST /admin/cleanup?dry_run=false must DELETE old blocked/expired rows
    and return the count deleted. Confirms wiring: only blocked+expired, only old rows.
    """
    pool, conn = mock_pool
    conn.execute.return_value = "DELETE 5"
    mock_state.pool = pool
    state.pool = pool

    response = client.post("/admin/cleanup?dry_run=false&days=30")

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["deleted"] == 5
    assert data["older_than_days"] == 30

    conn.execute.assert_called_once()
    sql = conn.execute.call_args.args[0]
    assert "DELETE" in sql
    assert "blocked" in sql
    assert "expired" in sql
    assert "snapshot_ts" in sql
