"""The skill gate groups by entry regime and assesses every cell together."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import skill_gate as module
from app.main import app, state
from app.skill_gate import COSTS, rows_to_observations
from tradesync_core.edge_evidence import assess_cells

client = TestClient(app)
T0 = datetime(2026, 9, 12, tzinfo=timezone.utc)


def row(h, regime, minute, direction="LONG", fwd=0.1, symbol="BTC-PERP"):
    return {
        "horizon_minutes": h, "symbol": symbol, "direction": direction,
        "opened_at": T0 + timedelta(minutes=minute), "forward_return_pct": fwd,
        "signed_return_pct": fwd if direction == "LONG" else -fwd, "regime": regime,
    }


def test_rows_group_by_horizon_and_entry_regime_with_unknown_kept() -> None:
    cells = rows_to_observations([row(15, "rising", 0), row(15, "falling", 5), row(60, None, 10)])
    assert set(cells) == {(15, "rising"), (15, "falling"), (60, "unknown")}
    obs = cells[(15, "rising")][0]
    assert obs.opened_at_s == int(T0.timestamp()) and obs.hit is True


def test_costs_name_their_source_and_use_the_published_fee() -> None:
    assert abs(COSTS.round_trip_fee_pct - 0.09) < 1e-9  # 2 x 0.045%
    assert "hyperliquid.gitbook.io" in COSTS.source
    assert COSTS.total_pct > COSTS.round_trip_fee_pct


def test_cells_are_holm_adjusted_together_not_one_at_a_time() -> None:
    """One marginal cell among several nulls does not become 'positive skill'."""
    def cell(label, seed_bias):
        return [row(15, label, i * 300, "LONG" if i % 2 else "SHORT",
                    (0.1 if i % 2 else -0.1) if (i % 10) < seed_bias else (-0.1 if i % 2 else 0.1))
                for i in range(120)]
    rows = cell("a", 6) + cell("b", 5) + cell("c", 5) + cell("d", 5) + cell("e", 5) + cell("f", 5)
    cells = rows_to_observations(rows)
    assessed = assess_cells([(k[1], k[0], v) for k, v in sorted(cells.items())], costs=COSTS, draws=100)
    assert not any(c.positive_skill for c in assessed)


def _pool(rows, unlabelled):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    conn.fetchval = AsyncMock(return_value=unlabelled)
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire)
    return pool


def test_endpoint_serves_the_measured_gate_with_computed_at() -> None:
    pool = _pool([row(15, "rising", i * 20) for i in range(12)], 3)
    module.CACHE.clear()
    try:
        asyncio.run(module.CACHE.refresh(pool, None))
        with patch.object(state, "pool", pool):
            r = client.get("/state/outcomes/skill-gate")
    finally:
        module.CACHE.clear()
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready" and body["computed_at"] and body["cache"]["stale"] is False
    assert body["verdict"]["gate"] == "CLOSED" and body["entry_regimes_pending"] == 3
    assert [c["regime"] for c in body["cells"]] == ["rising"]


def test_a_cold_gate_answers_computing_and_starts_one_measurement() -> None:
    module.CACHE.clear()
    try:
        with patch.object(state, "pool", MagicMock()), patch.object(module.CACHE, "ensure_measuring") as start:
            first = client.get("/state/outcomes/skill-gate?symbol=BTC-PERP")
    finally:
        module.CACHE.clear()
    assert first.status_code == 202 and first.json()["status"] == "computing"
    start.assert_called_once()


def test_compute_runs_the_bootstrap_off_the_event_loop() -> None:
    pool = _pool([row(60, "falling", i * 70) for i in range(8)], 0)
    with patch.object(module.asyncio, "to_thread", wraps=module.asyncio.to_thread) as offload:
        body = asyncio.run(module.compute_skill_gate(pool, "BTC-PERP"))
    offload.assert_called_once()
    assert body["symbol"] == "BTC-PERP" and body["cells_assessed_together"] == 1
