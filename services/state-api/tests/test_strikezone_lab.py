"""The quant lab routes store normalised ledger rows, refuse unknown documents, and serve only named charts."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import strikezone_lab
from app.main import app, state

client = TestClient(app)
SIGNAL = {
    "signal_id": "sig_1", "asset": "btc", "timeframe": "15m", "direction": "long", "signal_at_utc": "2026-09-13T07:00:00Z",
    "expiry_utc": "2026-09-13T11:00:00Z", "entry_reference_price": "100", "invalidation_price": "99", "target_price": "102",
    "confidence": "0.6", "regime": {"1h": "down"}, "methodology_version": "v1_3",
}


class FakeConn:
    def __init__(self) -> None:
        self.executemany = AsyncMock()
        self.execute = AsyncMock()
        self.fetch = AsyncMock(return_value=[])
        self.fetchrow = AsyncMock(return_value=None)

    def transaction(self):
        tx = MagicMock()
        tx.__aenter__ = AsyncMock(return_value=None)
        tx.__aexit__ = AsyncMock(return_value=False)
        return tx


def fake_pool(conn: FakeConn) -> MagicMock:
    pool = MagicMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool.acquire = acquire
    return pool


def test_ingest_normalises_rows_and_drops_malformed_ones() -> None:
    conn = FakeConn()
    body = {"signals": [SIGNAL, {"signal_id": "bad"}],
            "documents": {"health": {"payload": {"ok": False}, "source_updated_at": "2026-09-13T14:02:08Z"}}}
    with patch.object(state, "pool", fake_pool(conn)):
        resp = client.post("/state/strikezone/ingest", json=body)
    assert resp.status_code == 200
    assert resp.json()["signals"] == {"received": 2, "valid": 1} and resp.json()["documents"] == ["health"]
    stored = conn.executemany.await_args.args[1][0]
    assert stored[0] == "sig_1" and stored[1] == "BTC" and stored[14] == '{"1h": "down"}'
    assert conn.execute.await_args.args[1] == "health"


def test_ingest_refuses_unknown_documents() -> None:
    with patch.object(state, "pool", fake_pool(FakeConn())):
        resp = client.post("/state/strikezone/ingest", json={"documents": {"wallet": {"payload": {}}}})
    assert resp.status_code == 400


def test_charts_are_served_by_exact_name_only(tmp_path) -> None:
    name = "sig_" + "a" * 24 + ".png"
    (tmp_path / "signals").mkdir()
    (tmp_path / "signals" / name).write_bytes(b"\x89PNG")
    with patch.object(strikezone_lab, "CHARTS_DIR", tmp_path):
        ok = client.get(f"/state/strikezone/charts/signals/{name}")
        missing = client.get("/state/strikezone/charts/outcomes/pout_" + "b" * 24 + ".png")
        wrong_kind = client.get(f"/state/strikezone/charts/proposals/{name}")
        odd_name = client.get("/state/strikezone/charts/signals/secret.png")
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/png"
    assert missing.status_code == 404 and wrong_kind.status_code == 400 and odd_name.status_code == 400


def test_ledger_rows_carry_status_reward_risk_and_chart_links(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    signal_id = "sig_" + "c" * 24
    row = {
        "signal_id": signal_id, "asset": "BTC", "timeframe": "15m", "direction": "long", "signal_at": now - timedelta(hours=5),
        "expiry_at": now - timedelta(hours=3), "confidence": 0.6, "entry_price": 100.0, "invalidation_price": 99.0,
        "target_price": 102.0, "regime": '{"15m": "range"}', "outcome_id": None, "exit_reason": None, "exit_at": None,
        "holding_minutes": None, "net_pnl_usdc": None, "gross_pnl_usdc": None, "fees_usdc": None, "slippage_usdc": None,
        "funding_usdc": None, "entry_fill_price": None, "exit_fill_price": None,
    }
    (tmp_path / "signals").mkdir()
    (tmp_path / "signals" / f"{signal_id}.png").write_bytes(b"x")
    conn = FakeConn()
    conn.fetchrow = AsyncMock(return_value={"payload": '{"active_methodology_version": "v1_3"}', "snapshot_at": now})
    conn.fetch = AsyncMock(return_value=[row])
    with patch.object(strikezone_lab, "CHARTS_DIR", tmp_path), patch.object(strikezone_lab, "_chart_lists", {}), \
            patch.object(state, "pool", fake_pool(conn)):
        resp = client.get("/state/strikezone/ledger?view=trades")
    assert resp.status_code == 200
    body = resp.json()
    first = body["rows"][0]
    assert body["methodology_version"] == "v1_3"
    assert first["status"] == "overdue" and first["planned_reward_risk"] == 2.0 and first["outcome"] is None
    assert first["chart_url"] == f"/state/strikezone/charts/signals/{signal_id}.png" and first["regime"] == {"15m": "range"}
