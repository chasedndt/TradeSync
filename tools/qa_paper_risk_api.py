#!/usr/bin/env python
"""Isolated real-SQL acceptance of the paper risk engine through its own API, rolled back.

Runs state-api's routes, stores and reconciliation runner against PostgreSQL in
one outer transaction on a throwaway schema (023, 026 and 031 applied there,
031 DOWN and UP again). Books, candles and the symbol list come from a mock
transport and are QA fixtures, not market observations; no strategy or
performance claim follows from them. A second connection checks the entry lock
while the outer transaction holds it. Everything rolls back at the end.

    PG_DSN=postgresql://user@host:port/db python tools/qa_paper_risk_api.py
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import asyncpg
import httpx
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services" / "state-api"), str(ROOT / "libs" / "tradesync_core")]

from app import paper_correlation_job, paper_reconciliation_runner as runner  # noqa: E402
from app.managed_paper import register as register_managed_paper  # noqa: E402
from app.paper_risk_routes import register as register_paper_risk  # noqa: E402
from ops.migrate import up_sql  # noqa: E402
from tradesync_core.managed_paper import open_position  # noqa: E402

MARKET = "http://market-data.qa-fixture"
PRICE = {"BTC-PERP": 100.0, "ETH-PERP": 50.0}
RealClient = httpx.AsyncClient


def fixture_book(symbol: str) -> dict:
    bid, ask = PRICE[symbol] - 0.01, PRICE[symbol] + 0.01
    return {"venue": "hyperliquid", "symbol": symbol, "poll_ts": int(time.time() * 1000), "best_bid": bid, "best_ask": ask,
            "bids": [{"price": bid, "size": 1000}], "asks": [{"price": ask, "size": 1000}], "authority": "qa_fixture"}


def fixture_candles(symbol: str, count: int = 170) -> list[dict]:
    last_open = int(time.time()) // 3600 * 3600 - 3600
    bars = []
    for i in range(count):
        close = PRICE[symbol] * (1 + 0.01 * math.sin(i * 0.9) + (0.0005 * math.cos(i * 3.1) if symbol == "ETH-PERP" else 0))
        bars.append({"time": last_open - (count - 1 - i) * 3600, "open": close, "high": close + 0.5, "low": close - 0.5, "close": close})
    return bars


def market(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/snapshots":
        return httpx.Response(200, json={"snapshots": [{"venue": "hyperliquid", "symbol": s} for s in PRICE]})
    if path.startswith("/depth/hyperliquid/"):
        return httpx.Response(200, json=fixture_book(path.rsplit("/", 1)[1]))
    if path.startswith("/candles/hyperliquid/"):
        return httpx.Response(200, json={"candles": fixture_candles(path.rsplit("/", 1)[1]), "authority": "qa_fixture"})
    return httpx.Response(404, json={"error": "not part of the QA fixture"})


def fixture_client(*args, **kwargs):
    return RealClient(transport=httpx.MockTransport(market), timeout=kwargs.get("timeout", 8))


def passed(message: str) -> None:
    print("PASS " + message, flush=True)


async def refused_sql(conn, statement: str) -> None:
    try:
        async with conn.transaction():
            await conn.execute(statement)
    except asyncpg.PostgresError:
        return
    raise AssertionError(f"not refused: {statement}")


async def opportunity(conn, symbol: str) -> str:
    identity = uuid.uuid4()
    await conn.execute("INSERT INTO opportunities (id, symbol, dir, snapshot_ts, quality, links) VALUES ($1, $2, 'LONG', $3, 0, '{}')",
                       identity, symbol, datetime.now(timezone.utc))
    return str(identity)


async def main() -> None:
    dsn = os.environ["PG_DSN"]
    conn = await asyncpg.connect(dsn)
    outer = conn.transaction(isolation="repeatable_read")
    await outer.start()
    schema = "qa_paper_risk_api_" + uuid.uuid4().hex[:12]
    try:
        await conn.execute(f"CREATE SCHEMA {schema}")
        await conn.execute(f"SET LOCAL search_path TO {schema}")
        await conn.execute("CREATE TABLE opportunities (id uuid PRIMARY KEY, symbol text, dir text, snapshot_ts timestamptz, quality double precision, links jsonb)")
        texts = {n: (ROOT / "ops" / "migrations" / n).read_text(encoding="utf-8-sig") for n in ("023_managed_paper_positions.sql", "026_paper_control.sql", "031_paper_risk_engine.sql")}
        for text in texts.values():
            await conn.execute(up_sql(text))
        await conn.execute(texts["031_paper_risk_engine.sql"].split("-- DOWN", 1)[1])
        await conn.execute(up_sql(texts["031_paper_risk_engine.sql"]))
        passed("migrations 023, 026, 031 UP, 031 DOWN, 031 UP in an isolated schema")

        @asynccontextmanager
        async def acquire():
            yield conn

        state = SimpleNamespace(pool=SimpleNamespace(acquire=acquire))
        app = FastAPI()
        register_managed_paper(app, state, market_data_url=MARKET)
        register_paper_risk(app, state, market_data_url=MARKET)
        with patch.object(httpx, "AsyncClient", fixture_client):
            async with RealClient(transport=httpx.ASGITransport(app=app), base_url="http://qa") as api:
                run = await runner.run_once(state.pool, "startup")
                assert run["status"] == "clean", run
                account = (await api.get("/state/paper-account")).json()
                assert account["starting_capital_usdc"] == 10000 and account["cash_usdc"] == 10000 and account["ledger"]["last_sequence"] >= 1, account
                passed("startup reconciliation created the account with its capital entry and ran clean")

                await paper_correlation_job.measure_once(state.pool, MARKET)
                risk = (await api.get("/state/paper-risk")).json()
                assert [b["code"] for b in risk["blocking"]] == ["ENTRIES_PAUSED"], risk["blocking"]
                assert risk["correlation"]["buckets"] == [["BTC-PERP", "ETH-PERP"]], risk["correlation"]
                passed("correlation stored from fixture candles; only the default pause blocks entries")

                response = await api.post("/state/paper-pause", json={"entries_paused": False, "operator": "qa", "reason": "Isolated acceptance resume"})
                assert response.status_code == 200, response.text
                assert await conn.fetchval("SELECT operator FROM managed_paper_control_events ORDER BY created_at DESC LIMIT 1") == "qa"
                opened = await api.post("/state/paper-positions", json={"opportunity_id": await opportunity(conn, "BTC-PERP"), "style": "intraday", "notional": 250})
                assert opened.status_code == 200, opened.text
                passed("resume audited with the operator; a paper entry passed every risk check through the real route")

                changed = await api.post("/state/paper-limits", json={"operator": "qa", "reason": "Isolated acceptance: one position", "max_concurrent_positions": 1})
                assert changed.status_code == 200, changed.text
                refused = await api.post("/state/paper-positions", json={"opportunity_id": await opportunity(conn, "ETH-PERP"), "style": "intraday", "notional": 250})
                assert refused.status_code == 409 and "[MAX_POSITIONS_LIMIT]" in refused.json()["detail"], refused.text
                assert await conn.fetchval("SELECT count(*) FROM managed_paper_positions") == 1
                assert await conn.fetchval("SELECT count(*) FROM paper_risk_limit_events") == 1
                passed("limit change audited; the next entry refused with MAX_POSITIONS_LIMIT and nothing inserted")

                contender = await asyncpg.connect(dsn)
                try:
                    assert await contender.fetchval("SELECT pg_try_advisory_xact_lock(230914)") is False
                    await contender.execute("SET lock_timeout = '300ms'")
                    try:
                        await contender.execute("SELECT pg_advisory_xact_lock(230914)")
                        raise AssertionError("second connection took the entry lock")
                    except asyncpg.exceptions.LockNotAvailableError:
                        pass
                finally:
                    await contender.close()
                passed("a second connection cannot take entry lock 230914 while the API's transaction holds it")

                await asyncio.sleep(0.05)
                killed = await api.post("/state/paper-kill", json={"operator": "qa", "reason": "Isolated acceptance kill switch", "confirm": True})
                assert killed.status_code == 200, killed.text
                assert [c["exit_reason"] for c in killed.json()["closed"]] == ["kill_switch"] and killed.json()["pending"] == []
                ledger = await conn.fetch("SELECT kind, balance_after_usdc FROM paper_account_ledger ORDER BY sequence")
                row = await conn.fetchrow("SELECT cash_usdc, closed_positions FROM paper_account")
                assert [r["kind"] for r in ledger] == ["capital", "realised"] and row["cash_usdc"] == ledger[-1]["balance_after_usdc"] and row["closed_positions"] == 1
                assert [r["action"] for r in await conn.fetch("SELECT action FROM paper_kill_switch_events ORDER BY created_at")] == ["kill", "close"]
                assert await conn.fetchval("SELECT entries_paused FROM managed_paper_control") is True
                blocked = await api.post("/state/paper-pause", json={"entries_paused": False, "operator": "qa", "reason": "Try to resume while killed"})
                assert blocked.status_code == 409 and "[KILL_SWITCH_ACTIVE]" in blocked.json()["detail"], blocked.text
                passed("kill switch closed the open position with reason kill_switch, booked it, audited it, paused entries and refuses resuming them")

                run = await runner.run_once(state.pool, "periodic")
                assert run["status"] == "clean", run["mismatches"]
                await refused_sql(conn, "UPDATE paper_account_ledger SET amount_usdc = 0")
                passed("reconciliation after the kill: ledger and balances equal the closing events; ledger refuses UPDATE")

                resumed = await api.post("/state/paper-kill/resume", json={"operator": "qa", "reason": "Isolated acceptance resume after kill", "confirm": True})
                assert resumed.status_code == 200 and resumed.json()["entries_paused"] is True, resumed.text
                passed("resume after kill cleared the kill switch and left entries paused")

                plan = open_position("long", "intraday", 250, 1.0, fixture_book("ETH-PERP"), time.time())
                identity = uuid.uuid4()
                await conn.execute(
                    "INSERT INTO managed_paper_positions (id, opportunity_id, symbol, entry_evidence, evidence_sha256, initial_plan, position_state) "
                    "VALUES ($1, $2, 'ETH-PERP', '{}', 'qa fixture', $3::jsonb, $3::jsonb)", identity, uuid.UUID(await opportunity(conn, "ETH-PERP")), __import__("json").dumps(plan))
                await conn.execute("INSERT INTO managed_paper_events (id, position_id, kind, payload, created_at) VALUES ($1, $2, 'opened', $3::jsonb, clock_timestamp() - interval '700 seconds')",
                                   uuid.uuid4(), identity, __import__("json").dumps(plan))
                run = await runner.run_once(state.pool, "periodic")
                assert run["status"] == "clean" and [g["ongoing"] for g in run["gaps"]] == [True], run
                assert await conn.fetchval("SELECT count(*) FROM paper_observation_gaps WHERE position_id = $1 AND ended_at IS NULL", identity) == 1
                published = (await api.get("/state/paper-reconciliation")).json()["last_run"]
                assert published["positions_checked"] == 2 and published["gaps"][0]["position_id"] == str(identity)
                passed("an open position unobserved for 700 seconds is published as an ongoing gap with its start, not filled")
    finally:
        await outer.rollback()
        await conn.close()
    check = await asyncpg.connect(dsn)
    try:
        assert await check.fetchval("SELECT count(*) FROM pg_namespace WHERE nspname = $1", schema) == 0
    finally:
        await check.close()
    passed("outer transaction rolled back; throwaway schema gone")


if __name__ == "__main__":
    asyncio.run(main())
