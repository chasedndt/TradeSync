"""Exercise actual paper API with live quotes and isolated, rolled-back SQL rows.

The opportunity is explicitly a QA fixture, not a strategy recommendation.
Run inside state-api; never write into the public performance portfolio.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from types import SimpleNamespace
import uuid

import asyncpg
import httpx
from fastapi import FastAPI
from app.managed_paper import register


async def main():
    conn = await asyncpg.connect(os.environ['PG_DSN'])
    outer = conn.transaction()
    await outer.start()
    try:
        # Same-session temporary relations shadow the public tables only here.
        await conn.execute('CREATE TEMP TABLE opportunities (id uuid PRIMARY KEY, symbol text, dir text, snapshot_ts timestamptz, quality double precision, links jsonb) ON COMMIT DROP')
        await conn.execute('CREATE TEMP TABLE managed_paper_positions (LIKE public.managed_paper_positions INCLUDING ALL) ON COMMIT DROP')
        await conn.execute('CREATE TEMP TABLE managed_paper_events (LIKE public.managed_paper_events INCLUDING ALL) ON COMMIT DROP')
        await conn.execute('CREATE TEMP TABLE managed_paper_control(singleton boolean PRIMARY KEY,entries_paused boolean) ON COMMIT DROP')
        await conn.execute('INSERT INTO managed_paper_control VALUES(true,true)')
        await conn.execute('CREATE TRIGGER qa_entry_protection BEFORE UPDATE ON managed_paper_positions FOR EACH ROW EXECUTE FUNCTION public.protect_managed_paper_entry()')

        @asynccontextmanager
        async def acquire():
            yield conn

        isolated = FastAPI()
        register(isolated, SimpleNamespace(pool=SimpleNamespace(acquire=acquire)), market_data_url=os.environ.get('MARKET_DATA_URL', 'http://market-data:8000'))
        # No lifespan/background loop is started for this isolated test app.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=isolated), base_url='http://qa') as client:
            source = uuid.uuid4()
            await conn.execute("INSERT INTO opportunities VALUES($1,'BTC-PERP','LONG',now(),0,'{\"classification\":\"QA fixture, not a strategy signal\"}')", source)
            result = await client.post('/state/paper-positions', json={'opportunity_id': str(source), 'style': 'intraday', 'notional': 250})
            assert result.status_code == 409 and 'paused' in result.text, result.text
            assert await conn.fetchval('SELECT count(*) FROM managed_paper_positions') == 0
            await conn.execute('UPDATE managed_paper_control SET entries_paused=false')
            result = await client.post('/state/paper-positions', json={'opportunity_id': str(source), 'style': 'intraday', 'notional': 250})
            assert result.status_code == 200, (result.status_code, result.text)
            opened = result.json()
            assert opened['duplicate'] is False and opened['execution_authority'] is False
            identity = opened['id']
            duplicate = await client.post('/state/paper-positions', json={'opportunity_id': str(source), 'style': 'intraday', 'notional': 250})
            assert duplicate.json() == {'id': identity, 'duplicate': True}
            before = (await client.get(f'/state/paper-positions/{identity}/evidence')).json()
            assert before['entry_evidence']['entry_book']
            assert before['entry_evidence']['atr_candles']['count'] >= 15
            assert before['initial_plan']['status'] == 'open'
            context = before['entry_evidence']['external_context']['bybit_liquidations']
            assert context['scoring_influence'] is False
            assert context['cutoff'] <= before['initial_plan']['entry_time']
            assert all(e['received_at'] <= context['cutoff'] for e in context['events'])
            liquidity = before['entry_evidence']['external_context']['hyperliquid_book_history']
            assert liquidity['cutoff'] <= before['initial_plan']['entry_time']
            assert liquidity['scoring_influence'] is False
            assert all(s['time'] <= liquidity['cutoff'] for s in liquidity['samples'])
            assert len(before['evidence_sha256']) == 64
            # Allow a strictly later quote. Bounded wait; no artificial price edits.
            await conn.execute('UPDATE managed_paper_control SET entries_paused=true')
            for attempt in range(5):
                await asyncio.sleep(3)
                closed = await client.post(f'/state/paper-positions/{identity}/close', json={})
                if closed.status_code != 409:
                    break
            assert closed.status_code == 200, (closed.status_code, closed.text)
            assert closed.json()['status'] == 'closed'
            after = (await client.get(f'/state/paper-positions/{identity}/evidence')).json()
            assert before == after
            events = await conn.fetch('SELECT kind FROM managed_paper_events ORDER BY created_at,id')
            assert sorted(r['kind'] for r in events) == ['closed', 'opened']
            portfolio = (await client.get('/state/paper-positions')).json()
            assert len(portfolio['positions']) == 1
            print(json.dumps({'result': 'PASS', 'classification': 'fixture opportunity plus live Hyperliquid market observations; no strategy performance claim', 'entry': opened['position']['entry_price'], 'exit': closed.json()['exit_price'], 'exit_reason': closed.json()['exit_reason'], 'evidence_unchanged': True, 'duplicate_prevented': True, 'events': len(events)}))
    finally:
        await outer.rollback()
        await conn.close()
        print('Temporary QA transaction rolled back; public portfolio untouched.')


asyncio.run(main())
