"""Generic mobile notifications. Explicit enrollment; never trading authority.

ntfy.sh is fixed, HTTPS only, no caller-controlled URLs or sensitive payloads.
An accepted provider message is NOT proof that either phone received it.
"""
import asyncio
import hmac
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from app import background
from app.mobile_policy import Preferences, quiet

WORKER_STATE = {'last_tick': None, 'last_error': None}


def configured():
    return len(os.getenv('MOBILE_ALERTS_CONTROL_KEY', '')) >= 32


def authorize(request):
    if not configured():
        raise HTTPException(503, 'Mobile controls require a server-side MOBILE_ALERTS_CONTROL_KEY (32+ characters)')
    if not hmac.compare_digest(request.headers.get('X-API-Key', ''), os.environ['MOBILE_ALERTS_CONTROL_KEY']):
        raise HTTPException(403, 'Mobile control authorization required')


def message(kind, event_id):
    if kind not in ('test', 'attention'):
        raise ValueError('Unsupported notification template')
    return ('TradeSync notification test.' if kind == 'test' else 'TradeSync needs attention. Open your dashboard.') + ' Reference ' + str(event_id)[:8]


async def publish(topic, kind, event_id):
    if not re.fullmatch(r'tradesync-[a-f0-9]{48}', topic):
        raise ValueError('Invalid generated topic')
    body = message(kind, event_id)
    async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as client:
        response = await client.post('https://ntfy.sh/'+topic, content=body,
                                     headers={'Title': 'TradeSync', 'Priority': 'default', 'Content-Type': 'text/plain'})
        response.raise_for_status()
        payload = response.json()
    if (not isinstance(payload, dict) or payload.get('event') != 'message'
            or payload.get('topic') != topic or payload.get('message') != body
            or not isinstance(payload.get('id'), str) or not payload['id']):
        raise ValueError('Provider acceptance could not be verified')
    return payload['id']


async def enqueue(conn, device_id, kind, dedupe_key):
    if kind not in ('test', 'attention') or not 1 <= len(dedupe_key) <= 160:
        raise ValueError('Invalid notification event')
    return await conn.fetchval('''INSERT INTO mobile_alert_outbox
        (id,device_id,dedupe_key,kind,expires_at) VALUES ($1,$2,$3,$4,now()+interval '10 minutes')
        ON CONFLICT(device_id,dedupe_key) DO UPDATE SET dedupe_key=EXCLUDED.dedupe_key RETURNING id''',
        uuid.uuid4(), device_id, dedupe_key, kind)


async def dispatch_one(pool):
    if not configured():
        return
    async with pool.acquire() as conn:
        await conn.execute("UPDATE mobile_alert_outbox SET status='expired' WHERE status IN ('queued','retry','sending') AND expires_at <= now()")
        row = await conn.fetchrow('''WITH candidate AS (
          SELECT o.id FROM mobile_alert_outbox o JOIN mobile_alert_devices d ON d.id=o.device_id
          WHERE d.enabled AND o.expires_at>now() AND o.attempts<3
          AND ((o.status IN ('queued','retry') AND o.next_attempt_at<=now())
               OR (o.status='sending' AND o.lease_until<now()))
          ORDER BY o.created_at FOR UPDATE OF o SKIP LOCKED LIMIT 1
        ) UPDATE mobile_alert_outbox o SET status='sending', attempts=attempts+1,
          lease_until=now()+interval '60 seconds' FROM candidate c
          WHERE o.id=c.id RETURNING o.*''')
        if row is None:
            return
        topic = await conn.fetchval('SELECT topic FROM mobile_alert_devices WHERE id=$1 AND enabled', row['device_id'])
    if topic is None:
        return
    if row['kind'] == 'attention' and row['dedupe_key'].startswith('paper:'):
        async with pool.acquire() as conn:
            device = await conn.fetchrow('SELECT notification_preferences,enabled FROM mobile_alert_devices WHERE id=$1', row['device_id'])
            raw = device['notification_preferences'] if device else {}
            prefs = Preferences(**(json.loads(raw) if isinstance(raw, str) else raw))
            if not device or not device['enabled'] or not prefs.paper_events or quiet(prefs, datetime.now(timezone.utc)):
                await conn.execute("UPDATE mobile_alert_outbox SET status='expired',last_error='PreferenceSuppressed',lease_until=NULL WHERE id=$1", row['id'])
                return
    try:
        provider_id = await publish(topic, row['kind'], row['id'])
        async with pool.acquire() as conn:
            await conn.execute("UPDATE mobile_alert_outbox SET status='provider_accepted', provider_id=$2, accepted_at=now(), lease_until=NULL, last_error=NULL WHERE id=$1", row['id'], provider_id)
    except Exception as exc:
        status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
        terminal = row['attempts'] >= 3 or (status_code is not None and 400 <= status_code < 500 and status_code != 429)
        async with pool.acquire() as conn:
            await conn.execute("UPDATE mobile_alert_outbox SET status=$2, last_error=$3, lease_until=NULL, next_attempt_at=now()+interval '60 seconds' WHERE id=$1",
                               row['id'], 'failed' if terminal else 'retry', type(exc).__name__)


class Enrollment(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    platform: Literal['android', 'ios']
    public_topic_generic_only_consent: bool


async def worker_tick(pool):
    """An optional producer failure must not strand the existing delivery queue."""
    errors = []
    for name, operation in (('paper_intake', produce_paper_events), ('delivery', dispatch_one)):
        try:
            await operation(pool)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            errors.append(name+':'+type(exc).__name__)
    return ', '.join(errors) or None


async def produce_paper_events(pool):
    """Queue only new opted-in lifecycle events; quiet/budget drops are recorded.

    Budget uses a rolling 24-hour window, avoiding DST/midnight bursts. Queueing
    happens outside trading transactions, so notification failure cannot stop exits.
    """
    if not configured():
        return
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock(240914)')
            devices = await conn.fetch("SELECT id,notification_preferences,paper_events_enabled_at FROM mobile_alert_devices WHERE enabled AND paper_events_enabled_at IS NOT NULL")
            for device in devices:
                raw = device['notification_preferences']
                prefs = Preferences(**(json.loads(raw) if isinstance(raw, str) else raw))
                if not prefs.paper_events:
                    continue
                events = await conn.fetch("""SELECT e.id FROM managed_paper_events e
                  WHERE e.kind IN ('opened','closed') AND e.created_at>= $1
                  AND e.created_at>now()-interval '10 minutes'
                  AND NOT EXISTS (SELECT 1 FROM mobile_alert_outbox o WHERE o.device_id=$2 AND o.dedupe_key='paper:'||e.id::text)
                  ORDER BY e.created_at,e.id LIMIT 100""", device['paper_events_enabled_at'], device['id'])
                count = await conn.fetchval("SELECT count(*) FROM mobile_alert_outbox WHERE device_id=$1 AND kind='attention' AND created_at>now()-interval '24 hours' AND last_error IS DISTINCT FROM 'PreferenceSuppressed' AND last_error IS DISTINCT FROM 'BudgetSuppressed'", device['id'])
                for event in events:
                    reason = 'PreferenceSuppressed' if quiet(prefs, datetime.now(timezone.utc)) else 'BudgetSuppressed' if count >= prefs.daily_budget else None
                    identity = await enqueue(conn, device['id'], 'attention', 'paper:'+str(event['id']))
                    if reason:
                        await conn.execute("UPDATE mobile_alert_outbox SET status='expired',last_error=$2 WHERE id=$1", identity, reason)
                    else:
                        count += 1


def register(app, state):
    def pool():
        if state.pool is None:
            raise HTTPException(503, 'Notification database unavailable')
        return state.pool

    @app.get('/state/mobile-alerts/status')
    async def status():
        return {'configured': configured(), 'platforms': ['android', 'ios'],
                'worker_running': 'mobile_alerts' in background.running(),
                'worker': dict(WORKER_STATE),
                'provider': 'ntfy.sh', 'authority': 'notify_only',
                'note': 'Generic messages only. Public topic names are not authentication; anyone who learns one can read or spoof messages. Never approve a trade from a notification. Provider acceptance is not phone receipt.'}

    @app.get('/state/mobile-alerts/devices')
    async def devices(request: Request):
        authorize(request)
        async with pool().acquire() as conn:
            records = await conn.fetch('SELECT id,label,platform,enabled,created_at,operator_confirmed_at,notification_preferences FROM mobile_alert_devices ORDER BY created_at DESC LIMIT 20')
            events = await conn.fetch('SELECT id,device_id,kind,status,attempts,created_at,accepted_at,confirmed_at,last_error FROM mobile_alert_outbox ORDER BY created_at DESC LIMIT 50')
        return {'devices': [{**dict(r), 'notification_preferences': json.loads(r['notification_preferences']) if isinstance(r['notification_preferences'], str) else r['notification_preferences']} for r in records], 'events': [dict(r) for r in events]}

    @app.post('/state/mobile-alerts/devices/{device_id}/preferences')
    async def preferences(device_id: uuid.UUID, body: Preferences, request: Request):
        authorize(request)
        async with pool().acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow('SELECT notification_preferences,operator_confirmed_at FROM mobile_alert_devices WHERE id=$1 AND enabled FOR UPDATE', device_id)
                if row is None:
                    raise HTTPException(404, 'Enabled device not found')
                if body.paper_events and row['operator_confirmed_at'] is None:
                    raise HTTPException(409, 'Confirm a received test on this phone before enabling lifecycle alerts')
                raw = row['notification_preferences']
                previous = Preferences(**(json.loads(raw) if isinstance(raw,str) else raw))
                await conn.execute('''UPDATE mobile_alert_devices SET notification_preferences=$2::jsonb,
                    paper_events_enabled_at=CASE WHEN NOT $3 THEN NULL WHEN NOT $4 THEN now() ELSE paper_events_enabled_at END WHERE id=$1''',
                    device_id, body.model_dump_json(), body.paper_events, previous.paper_events)
        return {'status': 'preferences_saved', 'note': 'Applies to future paper open/close events. Quiet-hour and over-budget events are dropped, not replayed. Budget is per rolling 24 hours. Explicit tests bypass quiet hours.'}

    @app.post('/state/mobile-alerts/devices')
    async def enroll(body: Enrollment, request: Request):
        authorize(request)
        if not body.public_topic_generic_only_consent:
            raise HTTPException(422, 'Explicit consent to generic public-topic delivery required')
        identity, topic = uuid.uuid4(), 'tradesync-'+secrets.token_hex(24)
        async with pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(220914)")
                if await conn.fetchval('SELECT count(*) FROM mobile_alert_devices WHERE enabled') >= 10:
                    raise HTTPException(409, 'Ten active device channels already enrolled')
                await conn.execute('INSERT INTO mobile_alert_devices(id,label,platform,topic) VALUES($1,$2,$3,$4)', identity, body.label, body.platform, topic)
        return {'id': str(identity), 'topic': topic, 'server': 'https://ntfy.sh',
                'status': 'awaiting_phone_subscription', 'note': 'Subscribe to this topic in the ntfy phone app. No notification has been sent.'}

    @app.post('/state/mobile-alerts/devices/{device_id}/test')
    async def test(device_id: uuid.UUID, request: Request):
        authorize(request)
        async with pool().acquire() as conn:
            if not await conn.fetchval('SELECT enabled FROM mobile_alert_devices WHERE id=$1', device_id):
                raise HTTPException(404, 'Enabled device not found')
            minute = int(datetime.now(timezone.utc).timestamp())//60
            event_id = await enqueue(conn, device_id, 'test', f'test:{minute}')
        return {'id': str(event_id), 'status': 'queued_or_existing', 'note': 'One test per device per minute. Wait for provider acceptance, then confirm actual receipt.'}

    @app.post('/state/mobile-alerts/devices/{device_id}/subscription')
    async def subscription(device_id: uuid.UUID, request: Request):
        authorize(request)
        async with pool().acquire() as conn:
            topic = await conn.fetchval('SELECT topic FROM mobile_alert_devices WHERE id=$1 AND enabled', device_id)
        if topic is None:
            raise HTTPException(404, 'Enabled device not found')
        return {'topic': topic, 'server': 'https://ntfy.sh', 'note': 'Subscription details revealed to the authorized operator; no message sent.'}

    @app.post('/state/mobile-alerts/events/{event_id}/confirm')
    async def confirm(event_id: uuid.UUID, request: Request):
        authorize(request)
        async with pool().acquire() as conn:
            async with conn.transaction():
                device_id = await conn.fetchval("UPDATE mobile_alert_outbox SET status='operator_confirmed', confirmed_at=now() WHERE id=$1 AND status='provider_accepted' RETURNING device_id", event_id)
                if device_id is None:
                    raise HTTPException(409, 'Only a provider-accepted event can be confirmed')
                await conn.execute('UPDATE mobile_alert_devices SET operator_confirmed_at=now() WHERE id=$1', device_id)
        return {'status': 'operator_confirmed', 'evidence': 'Operator attestation, not device telemetry'}

    @app.post('/state/mobile-alerts/devices/{device_id}/disable')
    async def disable(device_id: uuid.UUID, request: Request):
        authorize(request)
        async with pool().acquire() as conn:
            await conn.execute('UPDATE mobile_alert_devices SET enabled=false WHERE id=$1', device_id)
        return {'status': 'disabled', 'note': 'Queued sends stop; an already in-flight request cannot be recalled.'}

    async def loop():
        while True:
            try:
                if state.pool is not None:
                    error = await worker_tick(state.pool)
                else:
                    error = 'DatabaseUnavailable'
                WORKER_STATE.update(last_tick=datetime.now(timezone.utc).isoformat(), last_error=error)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                WORKER_STATE.update(last_tick=datetime.now(timezone.utc).isoformat(), last_error=type(exc).__name__)
            await asyncio.sleep(10)
    background.add('mobile_alerts', loop)
