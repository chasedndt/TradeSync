"""Isolated SQL acceptance for migration 024 and lifecycle notification policy.

Run with --source pointing to a task-owned copy of app, never patch the running
service's modules. No HTTP transport is permitted; all rows roll back.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sys
import uuid
from types import SimpleNamespace

import asyncpg
import httpx
from fastapi import FastAPI

parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True)
parser.add_argument('--migration', required=True)
args = parser.parse_args()
sys.path.insert(0, args.source)
from app import mobile_alerts as mobile


async def main():
    conn = await asyncpg.connect(os.environ['PG_DSN'])
    outer = conn.transaction()
    await outer.start()
    try:
        await conn.execute('CREATE TEMP TABLE mobile_alert_devices (LIKE public.mobile_alert_devices INCLUDING ALL) ON COMMIT DROP')
        await conn.execute('CREATE TEMP TABLE mobile_alert_outbox (LIKE public.mobile_alert_outbox INCLUDING ALL) ON COMMIT DROP')
        await conn.execute('CREATE TEMP TABLE managed_paper_events (id uuid PRIMARY KEY,kind text,created_at timestamptz DEFAULT now()) ON COMMIT DROP')
        # Public schema may already be upgraded when re-running this QA.
        await conn.execute('ALTER TABLE mobile_alert_devices DROP COLUMN IF EXISTS notification_preferences, DROP COLUMN IF EXISTS paper_events_enabled_at')
        up, down = Path(args.migration).read_text().split('-- DOWN')
        await conn.execute(up)
        await conn.execute(down)
        await conn.execute(up)
        @asynccontextmanager
        async def acquire():
            yield conn
        class Pool:
            pass
        pool = Pool()
        pool.acquire = acquire
        sent = []
        async def fake_publish(topic, kind, identity):
            sent.append(str(identity))
            return 'QA-provider-acceptance-not-phone-receipt'
        mobile.publish = fake_publish
        os.environ['MOBILE_ALERTS_CONTROL_KEY'] = 'QA-fixture-only-control-key-not-used-outside-process'
        device = uuid.uuid4()
        await conn.execute("INSERT INTO mobile_alert_devices(id,label,platform,topic) VALUES($1,'QA isolated','ios',$2)", device, 'tradesync-'+'a'*48)
        await conn.execute("INSERT INTO managed_paper_events(id,kind) VALUES($1,'opened')", uuid.uuid4())
        await mobile.produce_paper_events(pool)
        assert await conn.fetchval('SELECT count(*) FROM mobile_alert_outbox') == 0
        prefs = {'paper_events':True,'quiet_enabled':False,'daily_budget':1}
        await conn.execute("UPDATE mobile_alert_devices SET notification_preferences=$2::jsonb,paper_events_enabled_at=now()-interval '1 second' WHERE id=$1", device, json.dumps(prefs))
        await conn.execute("INSERT INTO managed_paper_events(id,kind) VALUES($1,'closed')", uuid.uuid4())
        await mobile.produce_paper_events(pool)
        await mobile.produce_paper_events(pool)
        assert await conn.fetchval('SELECT count(*) FROM mobile_alert_outbox') == 2
        assert await conn.fetchval("SELECT count(*) FROM mobile_alert_outbox WHERE status='queued'") == 1
        assert await conn.fetchval("SELECT count(*) FROM mobile_alert_outbox WHERE last_error='BudgetSuppressed'") == 1
        # Opt-out after queue creation is enforced at dispatch, not only enqueue.
        await conn.execute("UPDATE mobile_alert_devices SET notification_preferences='{}'")
        await mobile.dispatch_one(pool)
        assert not sent
        assert await conn.fetchval("SELECT count(*) FROM mobile_alert_outbox WHERE last_error='PreferenceSuppressed'") == 1
        prefs.update(quiet_enabled=True, quiet_start=8, quiet_end=8, daily_budget=10)
        await conn.execute('UPDATE mobile_alert_devices SET notification_preferences=$1::jsonb', json.dumps(prefs))
        await conn.execute("INSERT INTO managed_paper_events(id,kind) VALUES($1,'closed')", uuid.uuid4())
        await mobile.produce_paper_events(pool)
        assert await conn.fetchval("SELECT count(*) FROM mobile_alert_outbox WHERE last_error='PreferenceSuppressed'") == 2
        # A manual test bypasses quiet hours; only the local fake sees it.
        await mobile.enqueue(conn, device, 'test', 'qa-manual-test')
        await mobile.dispatch_one(pool)
        assert len(sent) == 1
        assert await conn.fetchval("SELECT confirmed_at FROM mobile_alert_outbox WHERE dedupe_key='qa-manual-test'") is None
        # Events older than the opt-in boundary never replay.
        await conn.execute("UPDATE mobile_alert_devices SET paper_events_enabled_at=now()+interval '1 second'")
        await conn.execute("INSERT INTO managed_paper_events(id,kind) VALUES($1,'opened')", uuid.uuid4())
        count = await conn.fetchval('SELECT count(*) FROM mobile_alert_outbox')
        await mobile.produce_paper_events(pool)
        assert await conn.fetchval('SELECT count(*) FROM mobile_alert_outbox') == count
        # Exercise real authenticated handlers, not just direct SQL preference edits.
        app = FastAPI()
        mobile.register(app, SimpleNamespace(pool=pool))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://qa') as client:
            endpoint = f'/state/mobile-alerts/devices/{device}/preferences'
            assert (await client.post(endpoint, json={'paper_events':True})).status_code == 403
            client.headers['X-API-Key'] = os.environ['MOBILE_ALERTS_CONTROL_KEY']
            assert (await client.post(endpoint, json={'paper_events':True})).status_code == 409
            test_id = await conn.fetchval("SELECT id FROM mobile_alert_outbox WHERE dedupe_key='qa-manual-test'")
            receipt = await client.post(f'/state/mobile-alerts/events/{test_id}/confirm')
            assert receipt.status_code == 200
            assert receipt.json()['evidence'] == 'Operator attestation, not device telemetry'
            enabled = await client.post(endpoint, json={'paper_events':True,'quiet_enabled':False,'daily_budget':5})
            assert enabled.status_code == 200, enabled.text
            readback = (await client.get('/state/mobile-alerts/devices')).json()
            assert readback['devices'][0]['notification_preferences']['daily_budget'] == 5
            assert 'topic' not in readback['devices'][0]
            assert (await client.post(endpoint, json={'paper_events':False})).status_code == 200
            assert await conn.fetchval('SELECT paper_events_enabled_at FROM mobile_alert_devices WHERE id=$1', device) is None
            assert (await client.post(endpoint, json={'timezone':'../etc/passwd'})).status_code == 422
        print('PASS: migration UP/DOWN/UP; default opt-out; lifecycle dedupe; budget; dispatch opt-out; all-day quiet; explicit test bypass; opt-in boundary; no receipt fabrication. Fake transport only.')
        print('PASS: real preferences API rejects unauthorized/unconfirmed opt-in, accepts fixture receipt then preferences, reads back parsed preferences without topic, clears opt-in timestamp, rejects invalid timezone.')
    finally:
        await outer.rollback()
        await conn.close()
        print('All QA tables and migration changes rolled back; public tables untouched.')


asyncio.run(main())
