import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone
from app import main
from app.main import app, state

client = TestClient(app)

# Mock data
MOCK_EVENT = {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "ts": datetime.now(),
    "source": "hyperliquid",
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
    "links": {"signal_ids": ["sig1"], "event_ids": ["evt1"]},
    # Phase 3C added confluence to the query and the response builder; without
    # it here the handler raises KeyError and the endpoint answers 500.
    "confluence": {},
}

@patch("app.main.state")
def test_get_opportunities_treats_all_as_a_wildcard(mock_state, mock_pool):
    """The Cockpit asks for status "all"; it must not be matched literally.

    Comparing it against the stored status matched no row, so Mission Control
    reported "no scored opportunities available" while opportunities existed.
    """
    pool, conn = mock_pool
    conn.fetch.return_value = [MOCK_OPP]
    mock_state.pool = pool
    state.pool = pool

    response = client.get("/state/opportunities?status=all&limit=50")
    assert response.status_code == 200
    assert len(response.json()) == 1

    query = conn.fetch.call_args[0][0]
    assert "status =" not in query, "status must not be filtered when all is asked for"
    # Only the limit is bound when no filter applies.
    assert conn.fetch.call_args[0][1:] == (50,)


@patch("app.main.state")
def test_get_opportunities_still_filters_a_named_status(mock_state, mock_pool):
    pool, conn = mock_pool
    conn.fetch.return_value = [MOCK_OPP]
    mock_state.pool = pool
    state.pool = pool

    response = client.get("/state/opportunities?status=new&limit=10")
    assert response.status_code == 200
    query = conn.fetch.call_args[0][0]
    assert "status = $1" in query
    assert conn.fetch.call_args[0][1:] == ("new", 10)


@patch("app.main.state")
def test_get_opportunities_combines_symbol_and_wildcard_status(mock_state, mock_pool):
    pool, conn = mock_pool
    conn.fetch.return_value = [MOCK_OPP]
    mock_state.pool = pool
    state.pool = pool

    response = client.get("/state/opportunities?symbol=BTC-PERP&status=all")
    assert response.status_code == 200
    query = conn.fetch.call_args[0][0]
    assert "symbol = $1" in query
    assert "status =" not in query


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

def _preview_rows(symbol):
    """fetchrow results in the order the preview handler asks for them.

    A single return_value cannot express this: the second call decides whether
    an earlier decision already exists, and returning the opportunity row there
    sent the handler down the idempotent-replay branch and then read a key the
    opportunity does not have.
    """
    return [
        {"symbol": symbol},   # 1. the opportunity
        None,                 # 2. no existing decision for this venue
        None,                 # 3. no prior signal for the symbol
    ]



@patch("app.main.state")
def test_preview_action(mock_state, mock_pool):
    pool, conn = mock_pool
    conn.fetchrow.side_effect = _preview_rows("BTC-PERP")
    conn.fetchval.return_value = 0
    mock_state.pool = pool
    state.pool = pool

    payload = {"opportunity_id": "opp1", "size_usd": 5000.0}
    response = client.post("/actions/preview", json=payload)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["plan"]["symbol"] == "BTC-PERP"
    assert data["plan"]["size_usd"] == 5000.0


@patch("app.main.state")
def test_preview_is_refused_while_the_execution_gate_is_closed(mock_state, mock_pool):
    """Fail-closed: the gate refuses before any per-symbol rule is reached.

    This test previously asserted a blacklist reason for LUNA-PERP. It never
    gets that far — with EXECUTION_ENABLED false the global gate refuses first,
    which is the behaviour that actually matters. The blacklist rule is
    exercised directly against RiskGuardian below, where the gate is not in the
    way.
    """
    pool, conn = mock_pool
    conn.fetchrow.side_effect = _preview_rows("LUNA-PERP")
    conn.fetchval.return_value = 0
    mock_state.pool = pool
    state.pool = pool

    response = client.post(
        "/actions/preview", json={"opportunity_id": "opp2", "size_usd": 100.0}
    )

    assert response.status_code == 200, response.text
    verdict = response.json()["risk_verdict"]
    assert verdict["allowed"] is False
    # A refusal must say why, not merely refuse.
    assert "execution gate" in verdict["reason"].lower()


def test_the_execution_gate_is_checked_before_any_per_symbol_rule():
    """Fail-closed precedence, asserted at the engine.

    The gate is evaluated first, so a blacklisted symbol never reaches its own
    rule while execution is disabled. That ordering is the point: no per-symbol
    configuration can accidentally permit what the gate forbids.
    """
    from tradesync_core import RiskGuardian
    from tradesync_core.risk import ReasonCode

    verdict = RiskGuardian().check(
        symbol="LUNA-PERP",
        size_usd=100.0,
        opportunity={"status": "new", "quality": 90.0, "expires_at": None},
        latest_signal=None,
        phase="preview",
    )
    assert verdict.allowed is False
    assert verdict.reason_code is ReasonCode.EXEC_DISABLED


def test_a_rejection_reports_the_gate_as_it_actually_is():
    """execution_enabled must be read, not asserted.

    Three rejection paths hardcoded True while EXECUTION_ENABLED was false.
    """
    from app.main import execution_gate_enabled

    assert execution_gate_enabled() is False


@patch("app.main.state")
def test_execute_returns_the_standard_result_shape(mock_state, mock_pool):
    """Execution answers with an ExecutionResult whatever the verdict.

    The assertions here predated Phase 3C and expected a "placed_dry_run"
    status with an "execution_id". The contract is now a status of
    placed/rejected/error alongside an order_id.
    """
    pool, conn = mock_pool
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    conn.fetchrow.side_effect = [
        None,  # no existing order for this decision
        {
            "id": "dec1",
            "symbol": "BTC-PERP",
            "opp_status": "new",
            "quality": 80.0,
            "expires_at": expires,
            "dir": "LONG",
            "requested": {"size_usd": 100.0, "venue": "hyperliquid"},
            "risk": {"allowed": True},
            "opportunity_id": "opp1",
            "venue": "hyperliquid",
        },
        None,  # no prior signal
    ]
    conn.fetchval.return_value = 0
    conn.execute.return_value = "INSERT 0 1"
    mock_state.pool = pool
    state.pool = pool

    response = client.post(
        "/actions/execute", json={"decision_id": "dec1", "confirm": True}
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] in {"placed", "rejected", "error"}
    assert "order_id" in data
    # The invariant that matters: execution is disabled, so nothing was placed.
    # dry_run is False on a rejection because no order ran at all, dry or
    # otherwise; asserting True here would demand a lie about a path not taken.
    assert data["execution_enabled"] is False
    assert data["status"] != "placed"


@patch("app.main.state")
def test_execute_requires_confirmation(mock_state, mock_pool):
    """An unconfirmed execution is refused before any database work."""
    pool, _ = mock_pool
    mock_state.pool = pool
    state.pool = pool

    response = client.post(
        "/actions/execute", json={"decision_id": "dec1", "confirm": False}
    )
    assert response.status_code == 400


def test_paper_mode_is_reported_from_the_flag_not_a_literal():
    """Three rejection paths reported dry_run=False from a literal.

    Nothing had been sent to a venue on any of them, so `dry_run: false`
    asserted "this was a live action" about a request that never left the
    building — worse than the execution_enabled defect it sat next to, because
    a consumer reading it would conclude the system is live.

    The default is true, matching exec-hl-svc, so an unset variable fails safe.
    """
    import os
    from unittest.mock import patch as _patch

    with _patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DRY_RUN", None)
        assert main.paper_mode_enabled() is True

    for value, expected in (("true", True), ("TRUE", True), (" true ", True),
                            ("false", False), ("no", False), ("", False)):
        with _patch.dict(os.environ, {"DRY_RUN": value}):
            assert main.paper_mode_enabled() is expected, value


def test_the_two_gates_are_read_independently():
    """Paper mode and the execution gate answer different questions.

    DRY_RUN says orders are simulated; EXECUTION_ENABLED says the boundary will
    accept one at all. Conflating them would let one flag silently imply the
    other's state.
    """
    import os
    from unittest.mock import patch as _patch

    with _patch.dict(os.environ, {"DRY_RUN": "true", "EXECUTION_ENABLED": "true"}):
        assert main.paper_mode_enabled() is True
        assert main.execution_gate_enabled() is True
    with _patch.dict(os.environ, {"DRY_RUN": "false", "EXECUTION_ENABLED": "false"}):
        assert main.paper_mode_enabled() is False
        assert main.execution_gate_enabled() is False
