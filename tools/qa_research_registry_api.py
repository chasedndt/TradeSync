"""Actual trial routes in an isolated schema; rollback, no public registration."""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import uuid
import json
from datetime import datetime
import asyncpg
import httpx
from fastapi import FastAPI
from app.managed_paper import register


async def main():
    conn = await asyncpg.connect(os.environ['PG_DSN'])
    transaction = conn.transaction()
    await transaction.start()
    try:
        schema = 'qa_trial_api_'+uuid.uuid4().hex
        await conn.execute(f'CREATE SCHEMA {schema}')
        await conn.execute(f'SET LOCAL search_path TO {schema}')
        await conn.execute(Path(sys.argv[1]).read_text().split('-- DOWN')[0])
        await conn.execute('CREATE TABLE managed_paper_positions(id uuid,symbol text,created_at timestamptz,entry_evidence jsonb,position_state jsonb)')
        @asynccontextmanager
        async def acquire(): yield conn
        app = FastAPI()
        register(app, SimpleNamespace(pool=SimpleNamespace(acquire=acquire)), market_data_url='http://unused.invalid')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://qa') as client:
            assert (await client.post('/state/research-trials', json={'style':'live'})).status_code == 422
            created = await client.post('/state/research-trials', json={'style':'scalp'})
            assert created.status_code == 200, created.text
            first = created.json()
            assert first['duplicate'] is False and first['authority'] == 'research_only'
            retry = (await client.post('/state/research-trials', json={'style':'scalp'})).json()
            assert retry['duplicate'] is True
            assert retry['id'] == first['id'] and retry['registered_at'] == first['registered_at']
            listed = (await client.get('/state/research-trials')).json()
            assert len(listed['trials']) == 1
            assert listed['trials'][0]['specification'] == first['specification']
            result = await client.get('/state/research-trials/'+first['id']+'/evaluation')
            assert result.status_code == 200, result.text
            assert result.json()['state'] == 'collecting'
            assert result.json()['comparison']['eligible'] == 0
            assert result.json()['promotion_allowed'] is False
            at = datetime.fromisoformat(first['registered_at']).timestamp()
            # Synthetic outcomes in the isolated schema, never performance data.
            for entry_time, status, net in ((at-1,'closed',500), (at+.001,'closed',1), (at+.002,'open',0)):
                position = {'style':'scalp','side':'long','entry_time':entry_time,'exit_time':at+.003,
                            'status':status,'observation_gap':False,'notional':100,'net_estimate_usdc':net}
                await conn.execute('INSERT INTO managed_paper_positions VALUES($1,$2,clock_timestamp(),$3::jsonb,$4::jsonb)',
                                   uuid.uuid4(),'BTC-PERP','{}',json.dumps(position))
            await asyncio.sleep(.02)
            populated = (await client.get('/state/research-trials/'+first['id']+'/evaluation')).json()
            assert populated['comparison']['eligible'] == 1
            assert populated['outside_population'] == 1
            assert populated['pending_outcomes'] == 1
            assert populated['comparison']['baseline_mean_bps_per_opportunity'] == 100
            assert populated['comparison']['context_available'] == 0
            assert populated['comparison']['filter_mean_bps_per_opportunity'] == 0
            assert populated['state'] == 'collecting' and populated['promotion_allowed'] is False
            assert (await client.get(f'/state/research-trials/{uuid.uuid4()}/evaluation')).status_code == 404
            print('PASS: actual API invalid style, registration, duplicate timestamp preservation, parsed listing, empty forward evaluation, missing trial; no network or trading actions.')
            print('PASS: populated fixture evaluation excludes pre-registration entry, keeps open outcome pending, computes clean return and missing-context abstention without promotion.')
    finally:
        await transaction.rollback()
        await conn.close()
        print('Isolated schema rolled back; no public trial or position created.')


asyncio.run(main())
