"""The rehearsal path refuses honestly when it cannot price, and never fabricates."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import rehearsal as rehearsal_module
from app.main import app, state

client = TestClient(app)

OPP_ID = "11111111-1111-1111-1111-111111111111"


def _pool(fetchrow_results, fetch_results=None):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=fetchrow_results)
    conn.fetch = AsyncMock(return_value=fetch_results or [])
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire)
    return pool, conn


def _saved_row(**overrides):
    row = {
        "id": "22222222-2222-2222-2222-222222222222",
        "opportunity_id": OPP_ID,
        "symbol": "BTC-PERP",
        "direction": "LONG",
        "size_usd": 250.0,
        "status": "refused",
        "plan": "{}",
        "risk_verdict": "{}",
        "fill": None,
        "market": "{}",
        "created_at": datetime(2026, 9, 12, tzinfo=timezone.utc),
        "note": "Simulated.",
    }
    row.update(overrides)
    return row


@pytest.fixture(autouse=True)
def gate_closed(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENABLED", "false")


def test_market_data_unreachable_is_a_refusal_not_an_invented_fill():
    """Missing dependency: the rehearsal is journaled as refused with the reason."""
    opportunity = {"id": OPP_ID, "symbol": "BTC-PERP", "dir": "LONG", "status": "new", "quality": 60.0}
    pool, conn = _pool([None, opportunity, _saved_row()])
    state.pool = pool
    with patch.object(rehearsal_module, "_market", AsyncMock(return_value=(None, "market-data unreachable: ConnectError"))):
        resp = client.post("/actions/rehearse", json={"opportunity_id": OPP_ID, "size_usd": 250})
    assert resp.status_code == 200, resp.text
    # The INSERT's arguments are the truth of what was journaled.
    insert_args = conn.fetchrow.call_args_list[2].args
    status, verdict_json, fill_json = insert_args[5], insert_args[7], insert_args[8]
    assert status == "refused"
    assert '"MARKET_UNAVAILABLE"' in verdict_json
    assert fill_json is None
    assert resp.json()["duplicate"] is False


def test_a_duplicate_submission_returns_the_existing_row_without_a_second_fill():
    existing = _saved_row(status="rehearsed", fill='{"fill_price": 1.0}')
    pool, conn = _pool([existing])
    state.pool = pool
    resp = client.post("/actions/rehearse", json={"opportunity_id": OPP_ID, "size_usd": 999})
    assert resp.status_code == 200
    body = resp.json()
    assert body["duplicate"] is True
    assert body["rehearsal"]["size_usd"] == 250.0  # the original, not the new request
    assert conn.fetchrow.await_count == 1  # nothing else was read or written


def test_the_global_gate_stays_shut_for_preview_while_rehearsal_proceeds():
    """Regression guard: rehearsal must not have loosened the real gate."""
    from tradesync_core.risk import ReasonCode, RiskGuardian
    guard = RiskGuardian()
    opp = {"status": "new", "symbol": "BTC-PERP"}
    assert guard.check("BTC-PERP", 100.0, opp, phase="preview").reason_code == ReasonCode.EXEC_DISABLED
    assert guard.check("BTC-PERP", 100.0, opp, phase="execute").reason_code == ReasonCode.EXEC_DISABLED
    assert guard.check("BTC-PERP", 100.0, opp, phase="rehearsal").reason_code != ReasonCode.EXEC_DISABLED


def test_the_rehearsal_module_has_no_path_to_an_execution_service():
    """Structural: nothing in the module addresses the execution service or the signer.

    Prose may mention them ("no wallet or signer exists"); what must be absent is
    any way of *reaching* them — their hostnames, their routes, their clients.
    """
    import inspect
    source = inspect.getsource(rehearsal_module)
    for forbidden in ("exec-hl-svc", "/exec/hl/", "signer-svc", "/sign", "execute_action", "EXECUTION_ENABLED"):
        assert forbidden not in source, forbidden
