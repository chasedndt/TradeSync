"""Isolated real SQL/API control test; public entry control is never modified."""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import uuid
import asyncpg
import httpx
from fastapi import FastAPI
from app.managed_paper import register


async def main():
    conn = await asyncpg.connect(os.environ['PG_DSN'])
    transaction = conn.transaction()
    await transaction.start()
    try:
        schema = 'qa_paper_control_'+uuid.uuid4().hex
        await conn.execute(f'CREATE SCHEMA {schema}')
        await conn.execute(f'SET LOCAL search_path TO {schema}')
        up, down = Path(sys.argv[1]).read_text().split('-- DOWN')
        await conn.execute(up); await conn.execute(down); await conn.execute(up)
        @asynccontextmanager
        async def acquire(): yield conn
        app = FastAPI()
        register(app, SimpleNamespace(pool=SimpleNamespace(acquire=acquire)), market_data_url='http://unused.invalid')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://qa') as client:
            initial = (await client.get('/state/paper-control')).json()
            assert initial['entries_paused'] is True
            for paused in (False, True):
                result = await client.post('/state/paper-pause',json={'entries_paused':paused,'reason':'Isolated QA control check','operator':'isolated-qa'})
                assert result.status_code == 200, result.text
                assert (await client.get('/state/paper-control')).json()['entries_paused'] is paused
            # API changes acquired the production admission lock in this outer
            # transaction. A second connection must not acquire it concurrently.
            contender = await asyncpg.connect(os.environ['PG_DSN'])
            try:
                async with contender.transaction():
                    assert await contender.fetchval('SELECT pg_try_advisory_xact_lock(230914)') is False
            finally:
                await contender.close()
            assert await conn.fetchval('SELECT count(*) FROM managed_paper_control_events') == 2
            await conn.execute('DELETE FROM managed_paper_control')
            assert (await client.get('/state/paper-control')).status_code == 503
            assert (await client.post('/state/paper-pause',json={'entries_paused':False,'reason':'Isolated QA missing state','operator':'isolated-qa'})).status_code == 503
        print('PASS: migration UP/DOWN/UP, default paused, API pause/resume readback, audit rows, shared admission lock excludes second connection, missing-state refusal; no provider calls.')
    finally:
        await transaction.rollback()
        await conn.close()
        print('Isolated schema rolled back; public control untouched.')


asyncio.run(main())
