#!/usr/bin/env python
"""Isolated real-SQL acceptance of the paper risk engine with managed paper positions, rolled back.

Runs state-api's own code against PostgreSQL in one outer transaction on a throwaway
schema: migrations 023, 026, 032 and 031 (DOWN and UP again), the observer
(``managed_paper.update``), the paper risk routes, the admission gate and the
reconciliation runner. Books, candles, funding rates, the symbol list and recorded
oracle prices are QA fixtures (a mock transport and seeded rows), not market
observations; no strategy or performance claim follows from them. Positions are seeded
directly: the entry route and the risk gate's place in it are covered by the unit suites.

On real SQL it checks:
- account creation and audited pause and limit changes;
- a gate refusal, and the entry lock against a second connection;
- an operator close whose last funding hour is published after the close, booked as a
  realised entry at the close and then a funding adjustment of exactly the change;
- the kill switch closing a position through the managed close with its settled funding;
- a clean reconciliation after each step, resuming after the kill, and an ongoing gap.

Everything rolls back.

    PG_DSN=postgresql://user@host:port/db python tools/qa_paper_risk_api.py
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services" / "state-api"), str(ROOT / "libs" / "tradesync_core")]

from app import paper_correlation_job, paper_risk_gate  # noqa: E402
from app import paper_reconciliation_runner as runner  # noqa: E402
from app.managed_paper import register as register_managed_paper  # noqa: E402
from app.paper_risk_routes import register as register_paper_risk  # noqa: E402
from ops.migrate import up_sql  # noqa: E402
from tradesync_core.managed_paper import open_position  # noqa: E402
from tradesync_core.paper_account_ledger import money  # noqa: E402

H = 3600
MARKET = "http://market-data.qa-fixture"
PRICE = {"BTC-PERP": 100.0, "ETH-PERP": 50.0, "SOL-PERP": 20.0}
RATE = 1e-4
MIGRATIONS = ("023_managed_paper_positions.sql", "026_paper_control.sql", "032_managed_paper_funding.sql", "031_paper_risk_engine.sql")
RealClient = httpx.AsyncClient
UNPUBLISHED: set[int] = set()


def fixture_book(symbol: str, at: float | None = None) -> dict:
    bid, ask = PRICE[symbol] - 0.01, PRICE[symbol] + 0.01
    return {"venue": "hyperliquid", "symbol": symbol, "poll_ts": int((time.time() if at is None else at) * 1000), "best_bid": bid,
            "best_ask": ask, "bids": [{"price": bid, "size": 1000}], "asks": [{"price": ask, "size": 1000}], "authority": "qa_fixture"}


def fixture_candles(symbol: str, count: int = 170) -> list[dict]:
    last_open = int(time.time()) // H * H - H
    wobble = 0.0005 if symbol == "ETH-PERP" else 0.0
    closes = [PRICE[symbol] * (1 + 0.01 * math.sin(i * 0.9) + wobble * math.cos(i * 3.1)) for i in range(count)]
    return [{"time": last_open - (count - 1 - i) * H, "open": c, "high": c + 0.5, "low": c - 0.5, "close": c} for i, c in enumerate(closes)]


def market(request: httpx.Request) -> httpx.Response:
    path, symbol = request.url.path, request.url.path.rsplit("/", 1)[-1]
    if path == "/snapshots":
        return httpx.Response(200, json={"snapshots": [{"venue": "hyperliquid", "symbol": s} for s in PRICE]})
    if path.startswith("/depth/hyperliquid/"):
        return httpx.Response(200, json=fixture_book(symbol))
    if path.startswith("/candles/hyperliquid/"):
        return httpx.Response(200, json={"candles": fixture_candles(symbol), "authority": "qa_fixture"})
    if path.startswith("/funding-history/hyperliquid/"):
        start, end = int(request.url.params["start_ms"]) // 1000, int(request.url.params["end_ms"]) // 1000
        hours = [h for h in range(start // H * H, end + 1, H) if start <= h <= end and h not in UNPUBLISHED]
        return httpx.Response(200, json={"rows": [[h, RATE, 0.0] for h in hours]})
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


async def seed(conn, symbol: str, opened_at: float) -> uuid.UUID:
    """A paper position opened at ``opened_at`` from a fixture book, with its opened event."""
    plan = json.dumps(open_position("long", "intraday", 250, 1.0, fixture_book(symbol, opened_at), opened_at))
    identity, opportunity = uuid.uuid4(), uuid.uuid4()
    await conn.execute("INSERT INTO opportunities (id) VALUES ($1)", opportunity)
    await conn.execute("INSERT INTO managed_paper_positions (id, opportunity_id, symbol, created_at, entry_evidence, evidence_sha256, initial_plan, "
                       "position_state) VALUES ($1, $2, $3, to_timestamp($4::float8), '{}', 'qa fixture', $5::jsonb, $5::jsonb)",
                       identity, opportunity, symbol, opened_at, plan)
    await conn.execute("INSERT INTO managed_paper_events (id, position_id, kind, payload, created_at) VALUES ($1, $2, 'opened', $3::jsonb, "
                       "to_timestamp($4::float8))", uuid.uuid4(), identity, plan, opened_at)
    return identity


async def state_of(conn, identity: uuid.UUID) -> dict:
    return json.loads(await conn.fetchval("SELECT position_state FROM managed_paper_positions WHERE id = $1", identity))


async def schema_with_migrations(conn, schema: str) -> None:
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.execute(f"SET LOCAL search_path TO {schema}")
    await conn.execute("CREATE TABLE opportunities (id uuid PRIMARY KEY)")
    await conn.execute("CREATE TABLE market_open_interest (symbol text, observed_at timestamptz, oracle_price double precision, mark_price double precision)")
    texts = {name: (ROOT / "ops" / "migrations" / name).read_text(encoding="utf-8-sig") for name in MIGRATIONS}
    for text in texts.values():
        await conn.execute(up_sql(text))
    await conn.execute(texts["031_paper_risk_engine.sql"].split("-- DOWN", 1)[1])
    await conn.execute(up_sql(texts["031_paper_risk_engine.sql"]))
    last_hour = int(time.time()) // H * H
    for symbol, price in PRICE.items():
        for hour in range(last_hour - 4 * H, last_hour + H, H):
            await conn.execute("INSERT INTO market_open_interest VALUES ($1, to_timestamp($2::float8), $3, $3)", symbol, hour - 20, price)


async def main() -> None:
    dsn = os.environ["PG_DSN"]
    conn = await asyncpg.connect(dsn)
    outer = conn.transaction(isolation="repeatable_read")
    await outer.start()
    schema = "qa_paper_risk_api_" + uuid.uuid4().hex[:12]
    try:
        await schema_with_migrations(conn, schema)
        passed("migrations 023, 026, 032, 031 UP, 031 DOWN, 031 UP in an isolated schema")

        @asynccontextmanager
        async def acquire():
            yield conn

        state = SimpleNamespace(pool=SimpleNamespace(acquire=acquire))
        app = FastAPI()
        handles = register_managed_paper(app, state, market_data_url=MARKET)
        register_paper_risk(app, state, market_data_url=MARKET)
        last_hour = int(time.time()) // H * H
        opened_at = last_hour - H - 600  # the settlements at last_hour - H and last_hour follow the entry
        btc, eth = await seed(conn, "BTC-PERP", opened_at), await seed(conn, "ETH-PERP", opened_at)
        with patch.object(httpx, "AsyncClient", fixture_client):
            async with RealClient(transport=httpx.ASGITransport(app=app), base_url="http://qa") as api:
                assert (await runner.run_once(state.pool, "startup"))["status"] == "clean"
                account = (await api.get("/state/paper-account")).json()
                assert account["starting_capital_usdc"] == 10000 and account["cash_usdc"] == 10000, account
                await paper_correlation_job.measure_once(state.pool, MARKET)
                assert "ENTRIES_PAUSED" in [b["code"] for b in (await api.get("/state/paper-risk")).json()["blocking"]]
                resumed = await api.post("/state/paper-pause", json={"entries_paused": False, "operator": "qa", "reason": "Isolated acceptance resume"})
                assert resumed.status_code == 200, resumed.text
                assert await conn.fetchval("SELECT operator FROM managed_paper_control_events ORDER BY created_at DESC LIMIT 1") == "qa"
                passed("startup reconciliation created the account; correlation stored; resume audited with the operator")

                UNPUBLISHED.add(last_hour)
                at_close = await handles.update(eth, manual=True)
                assert at_close["status"] == "closed" and at_close["funding"]["missing_hours"] == [last_hour], at_close["funding"]
                UNPUBLISHED.clear()
                settled = await handles.update(eth)
                assert settled["funding"]["status"] == "complete" and await handles.update(eth) == settled
                kinds = sorted(r["kind"] for r in await conn.fetch("SELECT kind FROM managed_paper_events WHERE position_id = $1", eth))
                assert kinds == ["closed", "funding_settled", "opened"], kinds
                booked = await conn.fetch("SELECT kind, amount_usdc, funding_usdc FROM paper_account_ledger WHERE position_id = $1 ORDER BY sequence", eth)
                change = money(settled["funding_usdc"]) - money(at_close["funding_usdc"])
                assert [r["kind"] for r in booked] == ["realised", "funding_adjustment"] and change != 0
                assert booked[0]["funding_usdc"] == money(at_close["funding_usdc"]) and booked[1]["funding_usdc"] == change and booked[1]["amount_usdc"] == -change
                row = await conn.fetchrow("SELECT cash_usdc, funding_usdc FROM paper_account")
                assert row["cash_usdc"] == money(10000) + booked[0]["amount_usdc"] - change and row["funding_usdc"] == money(settled["funding_usdc"])
                assert (await runner.run_once(state.pool, "periodic"))["status"] == "clean"
                passed("late funding: realised entry at the close, then an adjustment of exactly the change; cash and funding moved by it, "
                       "a repeated observation booked nothing, reconciliation clean")

                changed = await api.post("/state/paper-limits", json={"operator": "qa", "reason": "Isolated acceptance: one position", "max_concurrent_positions": 1})
                assert changed.status_code == 200, changed.text
                try:
                    async with conn.transaction():
                        await paper_risk_gate.admit(conn, symbol="SOL-PERP", plan=open_position("long", "intraday", 250, 1.0, fixture_book("SOL-PERP"), time.time()))
                    raise AssertionError("admitted past the concurrent position limit")
                except HTTPException as exc:
                    assert exc.status_code == 409 and exc.detail.startswith("Paper entry refused [MAX_POSITIONS_LIMIT]"), exc.detail
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
                passed("limit change audited; the gate refused MAX_POSITIONS_LIMIT on real SQL; a second connection cannot take lock 230914 meanwhile")

                killed = await api.post("/state/paper-kill", json={"operator": "qa", "reason": "Isolated acceptance kill switch", "confirm": True})
                assert killed.status_code == 200 and [c["exit_reason"] for c in killed.json()["closed"]] == ["kill_switch"] and killed.json()["pending"] == [], killed.text
                closed = await state_of(conn, btc)
                assert closed["exit"]["rule"] == "kill_switch" and closed["slippage"]["exit"]["basis"] == "book_walk"
                assert closed["funding"]["status"] == "complete" and closed["funding"]["settled_hours"] == 2
                assert await conn.fetchval("SELECT count(*) FROM managed_paper_funding WHERE position_id = $1", btc) == 2
                assert await conn.fetchval("SELECT funding_usdc FROM paper_account_ledger WHERE position_id = $1 AND kind = 'realised'", btc) == money(closed["funding_usdc"])
                assert [r["action"] for r in await conn.fetch("SELECT action FROM paper_kill_switch_events ORDER BY created_at")] == ["kill", "close"]
                blocked = await api.post("/state/paper-pause", json={"entries_paused": False, "operator": "qa", "reason": "Try to resume while killed"})
                assert blocked.status_code == 409 and "[KILL_SWITCH_ACTIVE]" in blocked.json()["detail"], blocked.text
                assert (await runner.run_once(state.pool, "periodic"))["status"] == "clean"
                await refused_sql(conn, "UPDATE paper_account_ledger SET amount_usdc = 0")
                passed("kill switch closed through the managed close (book walk, two settled funding hours stored and netted), booked, audited; "
                       "resuming entries refused while killed; reconciliation clean; ledger refuses UPDATE")

                cleared = await api.post("/state/paper-kill/resume", json={"operator": "qa", "reason": "Isolated acceptance resume after kill", "confirm": True})
                assert cleared.status_code == 200 and cleared.json()["entries_paused"] is True, cleared.text
                quiet = await seed(conn, "SOL-PERP", time.time() - 700)
                run = await runner.run_once(state.pool, "periodic")
                assert run["status"] == "clean" and any(g["ongoing"] and g["position_id"] == str(quiet) for g in run["gaps"]), run
                assert await conn.fetchval("SELECT count(*) FROM paper_observation_gaps WHERE position_id = $1 AND ended_at IS NULL", quiet) == 1
                assert (await api.get("/state/paper-reconciliation")).json()["last_run"]["positions_checked"] == 3
                passed("resume after kill left entries paused; a position unobserved for 700 seconds is published as an ongoing gap, not filled")
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
