"""Real PostgreSQL registry protections in a unique rolled-back schema."""
import asyncio
import os
from pathlib import Path
import sys
import uuid
import asyncpg


async def main():
    conn = await asyncpg.connect(os.environ['PG_DSN'])
    transaction = conn.transaction()
    await transaction.start()
    try:
        schema = 'qa_trial_'+uuid.uuid4().hex
        await conn.execute(f'CREATE SCHEMA {schema}')
        await conn.execute(f'SET LOCAL search_path TO {schema}')
        up, down = Path(sys.argv[1]).read_text().split('-- DOWN')
        await conn.execute(up)
        await conn.execute(down)
        await conn.execute(up)
        identity, digest = uuid.uuid4(), 'a'*64
        before = await conn.fetchval('SELECT clock_timestamp()')
        registered = await conn.fetchval('INSERT INTO research_trials(id,specification,specification_sha256) VALUES($1,$2::jsonb,$3) RETURNING registered_at', identity, '{"fixture":true}', digest)
        assert registered >= before
        retry = await conn.fetchval('INSERT INTO research_trials(id,specification,specification_sha256) VALUES($1,$2::jsonb,$3) ON CONFLICT(specification_sha256) DO NOTHING RETURNING id', uuid.uuid4(), '{"fixture":true}', digest)
        assert retry is None
        for statement in ("UPDATE research_trials SET specification='{}'", 'UPDATE research_trials SET registered_at=now()', 'DELETE FROM research_trials'):
            savepoint = conn.transaction()
            await savepoint.start()
            try:
                await conn.execute(statement)
                raise AssertionError('Immutable registration was changed')
            except asyncpg.RaiseError:
                await savepoint.rollback()
        assert await conn.fetchval('SELECT count(*) FROM research_trials') == 1
        assert await conn.fetchval('SELECT registered_at FROM research_trials') == registered
        print('PASS: migration UP/DOWN/UP; server timestamp; duplicate conflict preserves registration; updates/deletes rejected. QA schema only.')
    finally:
        await transaction.rollback()
        await conn.close()
        print('QA schema and records rolled back; no public trial registered.')


asyncio.run(main())
