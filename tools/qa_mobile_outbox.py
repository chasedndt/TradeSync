"""Real PostgreSQL outbox acceptance, transaction rolled back; HTTP is forbidden.

Run in the State API container after migration 022. Only fake delivery is used.
"""
import asyncio
from contextlib import asynccontextmanager
import os
import uuid
import asyncpg
from app import mobile_alerts as mobile


async def main():
    conn = await asyncpg.connect(os.environ['PG_DSN'])
    transaction = conn.transaction()
    await transaction.start()
    await conn.execute('CREATE TEMP TABLE mobile_alert_devices (LIKE public.mobile_alert_devices INCLUDING ALL) ON COMMIT DROP')
    await conn.execute('CREATE TEMP TABLE mobile_alert_outbox (LIKE public.mobile_alert_outbox INCLUDING ALL) ON COMMIT DROP')
    class Pool:
        @asynccontextmanager
        async def acquire(self):
            yield conn
    pool = Pool()
    sent = []
    async def fake_publish(topic, kind, event_id):
        sent.append(str(event_id))
        return 'fixture-provider-id'
    mobile.publish = fake_publish  # No external transport can run in this process.
    os.environ['MOBILE_ALERTS_CONTROL_KEY'] = 'fixture-only-not-a-real-control-key'
    try:
        device = uuid.uuid4()
        await conn.execute("INSERT INTO mobile_alert_devices(id,label,platform,topic) VALUES($1,'QA rollback','android',$2)", device, 'tradesync-'+uuid.uuid4().hex+uuid.uuid4().hex[:16])
        event = await mobile.enqueue(conn, device, 'test', 'fixture-one')
        assert await mobile.enqueue(conn, device, 'test', 'fixture-one') == event
        await mobile.dispatch_one(pool)
        row = await conn.fetchrow('SELECT * FROM mobile_alert_outbox WHERE id=$1', event)
        assert row['status'] == 'provider_accepted' and row['attempts'] == 1
        assert row['confirmed_at'] is None
        await mobile.dispatch_one(pool)
        assert sent == [str(event)]
        expired = await mobile.enqueue(conn, device, 'test', 'fixture-expired')
        await conn.execute("UPDATE mobile_alert_outbox SET expires_at=now()-interval '1 second' WHERE id=$1", expired)
        await mobile.dispatch_one(pool)
        assert await conn.fetchval('SELECT status FROM mobile_alert_outbox WHERE id=$1', expired) == 'expired'
        retry = await mobile.enqueue(conn, device, 'test', 'fixture-retry')
        async def fake_failure(*args):
            raise TimeoutError('fixture transient failure')
        mobile.publish = fake_failure
        for attempt in range(3):
            await conn.execute("UPDATE mobile_alert_outbox SET next_attempt_at=now()-interval '1 second' WHERE id=$1", retry)
            await mobile.dispatch_one(pool)
        row = await conn.fetchrow('SELECT status,attempts FROM mobile_alert_outbox WHERE id=$1', retry)
        assert dict(row) == {'status': 'failed', 'attempts': 3}
        print('PASS: real SQL enqueue dedupe, acceptance != receipt, no repeat accepted send, expiry, bounded retries; fake transport only; rollback follows')
    finally:
        await transaction.rollback()
        await conn.close()

asyncio.run(main())
