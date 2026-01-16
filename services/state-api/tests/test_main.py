import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime
from app.main import app, state

client = TestClient(app)

# Mock data
MOCK_EVENT = {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "ts": datetime.now(),
    "source": "drift",
    "kind": "market_snapshot",
    "symbol": "BTC-PERP",
    "timeframe": "1m",
    "payload": {"price": 100000.0}
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
    "features": {"funding_rate": 0.0001}
}

@pytest.fixture
def mock_pool():
    pool = MagicMock() # acquire is not async, it returns a CM
    conn = AsyncMock()
    
    # Create a mock context manager
    cm = AsyncMock()
    cm.__aenter__.return_value = conn
    cm.__aexit__.return_value = None
    
    # pool.acquire() returns the context manager
    pool.acquire.return_value = cm
    
    return pool, conn

def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

@patch("app.main.state")
def test_state_health_healthy(mock_state, mock_pool):
    pool, conn = mock_pool
    # Setup mock return for fetchrow
    conn.fetchrow.return_value = {
        "last_evt": datetime(2025, 1, 1, 12, 0, 0),
        "last_sig": datetime(2025, 1, 1, 12, 0, 5)
    }
    mock_state.pool = pool
    state.pool = pool # Update global state

    response = client.get("/state/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["postgres"] is True
    assert "last_event_ts" in data

@patch("app.main.state")
def test_get_events_latest(mock_state, mock_pool):
    pool, conn = mock_pool
    # Setup mock return for fetch
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

MOCK_OPP = {
    "id": "123e4567-e89b-12d3-a456-426614174002",
    "symbol": "BTC-PERP",
    "timeframe": "1m",
    "bias": 2.5,
    "quality": 25.0,
    "dir": "long",
    "status": "new",
    "snapshot_ts": datetime.now(),
    "links": {"signal_ids": ["sig1"], "event_ids": ["evt1"]}
}

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
def test_preview_action(mock_state, mock_pool):
    pool, conn = mock_pool
    # Mock finding opportunity
    conn.fetchrow.return_value = {"symbol": "BTC-PERP"}
    mock_state.pool = pool
    state.pool = pool
    
    payload = {"opportunity_id": "opp1", "size_usd": 5000.0}
    response = client.post("/actions/preview", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["plan"]["symbol"] == "BTC-PERP"
    assert data["risk_verdict"]["allowed"] is True

@patch("app.main.state")
def test_preview_action_blocked(mock_state, mock_pool):
    pool, conn = mock_pool
    conn.fetchrow.return_value = {"symbol": "LUNA-PERP"} # Blacklisted
    mock_state.pool = pool
    state.pool = pool
    
    payload = {"opportunity_id": "opp2", "size_usd": 100.0}
    response = client.post("/actions/preview", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["risk_verdict"]["allowed"] is False
    assert "blacklisted" in data["risk_verdict"]["reason"]

@patch("app.main.state")
def test_execute_action(mock_state, mock_pool):
    pool, conn = mock_pool
    # Mock insert execution
    conn.execute.return_value = "INSERT 0 1"
    mock_state.pool = pool
    state.pool = pool
    
    payload = {"decision_id": "dec1", "confirm": True}
    response = client.post("/actions/execute", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "placed_dry_run"
    assert "execution_id" in data
