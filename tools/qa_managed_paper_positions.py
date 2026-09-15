"""Live-data acceptance for managed paper positions, in an isolated schema that is rolled back.

Run from the repository root. The launcher executes it inside the running state-api
container against this checkout's code and writes nothing into the container:

    python tools/run_in_state_api.py tools/qa_managed_paper_positions.py \
        --with tools/qa_paper_live.py --with tools/qa_paper_replay.py -- [live_minutes] [replay_hours]

A (``qa_paper_live``): a real current opportunity from the tracked universe opens a paper
position through the real route, the observer's own update advances it on live books, an
operator close ends it, and fees, slippage, settled funding rows and the frozen entry
evidence are verified.

B (``qa_paper_replay``): positions entered hours ago at real opportunities' times, priced
from the book recorded that minute, advanced on the real 1-minute candles since, with
settled funding for every hour crossed, verified the same way.

Every write lands in a fresh schema inside one transaction that is rolled back at the end;
public tables are only read. No order, wallet or signer is involved. Prints a JSON report.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import asyncpg
import httpx
from fastapi import FastAPI

import qa_paper_live
import qa_paper_replay
from app import managed_paper

MIGRATIONS = ("023_managed_paper_positions.sql", "026_paper_control.sql", "032_managed_paper_funding.sql")
MARKET = os.environ.get("MARKET_DATA_URL", "http://market-data:8005")


class Checks:
    def __init__(self):
        self.results = {}

    def __call__(self, name, passed, detail=None):
        self.results[name] = {"passed": bool(passed), **({"detail": detail} if detail is not None else {})}
        print(f"[{'PASS' if passed else 'FAIL'}] {name}{'' if passed or detail is None else f': {detail}'}", file=sys.stderr, flush=True)
        return bool(passed)

    @property
    def passed(self):
        return bool(self.results) and all(result["passed"] for result in self.results.values())


def sections(name):
    up, down = QA_FILES[f"ops/migrations/{name}"].split("-- DOWN")  # noqa: F821 - provided by the launcher
    return up.replace("-- UP", "", 1), down


async def schema_of(conn, relation):
    """The schema an unqualified relation name resolves to on this connection, or None."""
    return await conn.fetchval("SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                               "WHERE c.oid = to_regclass($1)", relation)


def app_on(conn):
    @asynccontextmanager
    async def acquire():
        yield conn

    pool = SimpleNamespace(acquire=acquire)
    app = FastAPI()
    handles = managed_paper.register(app, SimpleNamespace(pool=pool), market_data_url=MARKET)
    return app, pool, handles


async def main(live_minutes, replay_hours):
    checks = Checks()
    report = {"classification": ("Real opportunities, live Hyperliquid books and candles, recorded books and funding; isolated "
                                 "rolled-back schema. Engineering acceptance, not strategy performance."),
              "started_at": time.time(), "live_minutes": live_minutes, "replay_hours": replay_hours}
    conn = await asyncpg.connect(os.environ["PG_DSN"], statement_cache_size=0)
    reader = await asyncpg.connect(os.environ["PG_DSN"], statement_cache_size=0)
    schema = "qa_paper_positions_" + uuid.uuid4().hex[:12]
    outer = conn.transaction()
    await outer.start()
    try:
        await reader.execute("BEGIN READ ONLY")
        public_positions = await reader.fetchval("SELECT count(*) FROM managed_paper_positions")
        await conn.execute(f"CREATE SCHEMA {schema}")
        await conn.execute(f"SET LOCAL search_path TO {schema}, public")
        await conn.execute(f"CREATE TABLE {schema}.opportunities (LIKE public.opportunities INCLUDING ALL)")
        for name in MIGRATIONS:
            await conn.execute(sections(name)[0])
        await conn.execute("UPDATE managed_paper_control SET entries_paused=false, reason='Isolated acceptance schema only'")
        shadow = await schema_of(conn, "managed_paper_positions")
        checks("isolated tables shadow the public ones", shadow == schema and await schema_of(conn, "managed_paper_control") == schema, shadow)
        app, pool, handles = app_on(conn)
        public_app, _, _ = app_on(reader)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://qa", timeout=180) as client, \
                httpx.AsyncClient(transport=httpx.ASGITransport(app=public_app), base_url="http://public", timeout=60) as public:
            ctx = SimpleNamespace(conn=conn, pool=pool, client=client, public=public, handles=handles, market=MARKET, checks=checks)
            report["live"] = await qa_paper_live.run(ctx, live_minutes)
            report["replays"] = await qa_paper_replay.run(ctx, replay_hours)
        up, down = sections("032_managed_paper_funding.sql")
        async with conn.transaction():
            await conn.execute(down)
            dropped = await schema_of(conn, "managed_paper_funding") is None
            await conn.execute(up)
            restored = await schema_of(conn, "managed_paper_funding") == schema
        checks("migration 032 DOWN then UP again in the isolated schema", dropped and restored)
    except Exception as exc:
        checks("acceptance ran to completion", False, f"{type(exc).__name__}: {exc}")
        raise
    finally:
        await outer.rollback()
        await reader.execute("ROLLBACK")
        report["schema_after_rollback"] = await conn.fetchval("SELECT count(*) FROM pg_namespace WHERE nspname=$1", schema)
        report["public_positions_before_after"] = [public_positions, await conn.fetchval("SELECT count(*) FROM public.managed_paper_positions")]
        report["public_entries_paused_after"] = await conn.fetchval("SELECT entries_paused FROM public.managed_paper_control")
        checks("rolled back: schema gone, public portfolio and pause untouched",
               report["schema_after_rollback"] == 0 and report["public_positions_before_after"][0] == report["public_positions_before_after"][1]
               and report["public_entries_paused_after"] is True)
        await conn.close()
        await reader.close()
        report["finished_at"] = time.time()
        report["checks"] = checks.results
        report["result"] = "PASS" if checks.passed else "FAIL"
        print(json.dumps(report, default=str, indent=1))
    return 0 if checks.passed else 1


if __name__ == "__main__":
    arguments = [float(a) for a in sys.argv[1:]]
    raise SystemExit(asyncio.run(main(arguments[0] if arguments else 8.0, arguments[1] if len(arguments) > 1 else 6.0)))
