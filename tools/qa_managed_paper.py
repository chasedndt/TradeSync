"""Real DB immutability/lifecycle checks in temporary tables; no live positions."""
import asyncio
import json
import os
import uuid
import asyncpg
from tradesync_core.managed_paper import open_position, advance

async def main():
    conn = await asyncpg.connect(os.environ['PG_DSN'])
    outer = conn.transaction()
    await outer.start()
    try:
        await conn.execute('CREATE TEMP TABLE managed_paper_positions (LIKE public.managed_paper_positions INCLUDING ALL) ON COMMIT DROP')
        await conn.execute('CREATE TRIGGER qa_entry_protection BEFORE UPDATE ON managed_paper_positions FOR EACH ROW EXECUTE FUNCTION public.protect_managed_paper_entry()')
        identity = uuid.uuid4()
        book = {'poll_ts':1000000,'best_bid':99.99,'best_ask':100.01,'bids':[{'price':99.99,'size':100}], 'asks':[{'price':100.01,'size':100}]}
        plan = open_position('long','scalp',250,1,book,1000)
        await conn.execute('INSERT INTO managed_paper_positions(id,opportunity_id,symbol,entry_evidence,evidence_sha256,initial_plan,position_state) VALUES($1,$2,$3,$4::jsonb,$5,$6::jsonb,$6::jsonb)', identity,uuid.uuid4(),'BTC-PERP',json.dumps({'fixture':True}), 'fixture-digest',json.dumps(plan))
        for column, value in [('entry_evidence', '{"changed":true}'), ('initial_plan', '{}')]:
            inner = conn.transaction()
            await inner.start()
            try:
                await conn.execute(f'UPDATE managed_paper_positions SET {column}=$2::jsonb WHERE id=$1',identity,value)
                raise AssertionError('Entry mutation incorrectly allowed')
            except asyncpg.RaiseError:
                await inner.rollback()
        book.update(poll_ts=1010000,best_bid=104,best_ask=104.01,bids=[{'price':104,'size':100}],asks=[{'price':104.01,'size':100}])
        closed = advance(plan,book,1010)
        await conn.execute('UPDATE managed_paper_positions SET position_state=$2::jsonb WHERE id=$1',identity,json.dumps(closed))
        row = await conn.fetchrow('SELECT initial_plan,position_state,entry_evidence FROM managed_paper_positions WHERE id=$1',identity)
        assert json.loads(row['initial_plan'])['status']=='open'
        assert json.loads(row['position_state'])['status']=='closed'
        assert json.loads(row['entry_evidence']) == {'fixture':True}
        print('PASS: frozen entry/plan rejected mutations; position lifecycle updated separately; fixture-only temporary tables rolled back')
    finally:
        await outer.rollback()
        await conn.close()

asyncio.run(main())
