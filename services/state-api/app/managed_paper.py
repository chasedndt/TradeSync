"""Durable operator-opened paper positions; observed quotes, never real orders."""
import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field
from tradesync_core.managed_paper import PROFILES, atr, open_position, advance
from tradesync_core.source_comparison import compare
from tradesync_core.research_trial import specification, fingerprint, evaluate
from app import background
from app.entry_context import liquidation_snapshot, book_snapshot

# Printed under the paper portfolio in the Cockpit.
POSITIONS_NOTE = (
    "Priced from observed quotes, not exchange fills. 100 latest positions. Funding is a frozen scenario, "
    "not actual settlement. Observation gaps disqualify clean performance evidence."
)


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


def serial(value):
    return json.dumps(value, sort_keys=True, default=str, allow_nan=False)


class OpenRequest(BaseModel):
    opportunity_id: uuid.UUID
    style: str = Field('intraday', pattern='^(scalp|intraday|swing)$')
    notional: float = Field(250, gt=0, le=1000, allow_inf_nan=False)


class TrialRequest(BaseModel):
    style: str = Field(pattern='^(scalp|intraday|swing)$')


class PaperControlRequest(BaseModel):
    entries_paused: bool
    reason: str = Field(min_length=5, max_length=240)


def register(app, state, *, market_data_url):
    health = {'last_tick': None, 'last_error': None}
    def pool():
        if state.pool is None: raise HTTPException(503, 'Paper-position database unavailable')
        return state.pool

    async def fetch(path):
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            result = await client.get(market_data_url+path)
            result.raise_for_status()
            return result.json()

    async def event(conn, identity, kind, payload):
        await conn.execute('INSERT INTO managed_paper_events(id,position_id,kind,payload) VALUES($1,$2,$3,$4::jsonb)', uuid.uuid4(), identity, kind, serial(payload))

    async def update(identity, manual=False):
        async with pool().acquire() as conn:
            row = await conn.fetchrow('SELECT symbol,position_state FROM managed_paper_positions WHERE id=$1', identity)
        if row is None: raise HTTPException(404, 'Paper position not found')
        book = await fetch('/depth/hyperliquid/'+row['symbol'])
        async with pool().acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow('SELECT position_state FROM managed_paper_positions WHERE id=$1 FOR UPDATE', identity)
                current = decode(row['position_state'])
                if current['status'] != 'open': return current
                result = advance(current, book, time.time(), manual_close=manual)
                await conn.execute('UPDATE managed_paper_positions SET position_state=$2::jsonb,updated_at=now() WHERE id=$1', identity, serial(result))
                await event(conn, identity, 'closed' if result['status']=='closed' else 'observed', {'position': result, 'book': book})
        return result

    @app.get('/state/paper-control')
    async def paper_control():
        async with pool().acquire() as conn:
            row = await conn.fetchrow('SELECT entries_paused,reason,updated_at FROM managed_paper_control WHERE singleton=true')
        if row is None: raise HTTPException(503, 'Paper control missing; entries disabled')
        return {**dict(row), 'authority':'paper_only', 'note':'Pauses new entries only. Observation and closing remain active; existing positions are not liquidated.'}

    @app.post('/state/paper-control')
    async def change_paper_control(body: PaperControlRequest):
        reason = body.reason.strip()
        if len(reason) < 5: raise HTTPException(422, 'Meaningful control reason required')
        async with pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute('SELECT pg_advisory_xact_lock(230914)')
                row = await conn.fetchrow('UPDATE managed_paper_control SET entries_paused=$1,reason=$2,updated_at=clock_timestamp() WHERE singleton=true RETURNING entries_paused,reason,updated_at', body.entries_paused, reason)
                if row is None: raise HTTPException(503, 'Paper control missing; entries disabled')
                await conn.execute('INSERT INTO managed_paper_control_events(id,entries_paused,reason) VALUES($1,$2,$3)',uuid.uuid4(),body.entries_paused,reason)
        return {**dict(row), 'authority':'paper_only'}

    @app.get('/state/paper-positions')
    async def listing():
        async with pool().acquire() as conn:
            rows = await conn.fetch('SELECT id,opportunity_id,symbol,created_at,updated_at,evidence_sha256,position_state FROM managed_paper_positions ORDER BY created_at DESC LIMIT 100')
        return {'positions': [{**dict(r), 'position_state': decode(r['position_state'])} for r in rows],
                'worker': health, 'execution_authority': False,
                'note': POSITIONS_NOTE}

    @app.get('/state/research-trials')
    async def trials():
        async with pool().acquire() as conn:
            rows = await conn.fetch('SELECT * FROM research_trials ORDER BY registered_at DESC LIMIT 100')
        return {'trials':[{**dict(r), 'specification':decode(r['specification'])} for r in rows],
                'authority':'research_only', 'note':'Registration freezes a protocol; it does not start a job or open a position. Results require later entries and resolved outcomes.'}

    @app.get('/state/research-trials/{identity}/evaluation')
    async def trial_evaluation(identity: uuid.UUID):
        async with pool().acquire() as conn:
            trial = await conn.fetchrow('SELECT * FROM research_trials WHERE id=$1', identity)
            if trial is None:
                raise HTTPException(404, 'Research trial not found')
            spec = decode(trial['specification'])
            if fingerprint(spec) != trial['specification_sha256']:
                raise HTTPException(409, 'Stored specification fingerprint mismatch')
            rows = await conn.fetch('SELECT id,symbol,entry_evidence,position_state FROM managed_paper_positions WHERE created_at >= $1 ORDER BY created_at,id LIMIT 10001', trial['registered_at'])
        if len(rows) > 10000:
            return {'state':'incomplete_record_window', 'promotion_allowed':False,
                    'note':'More than 10000 candidate records; evaluation refused rather than silently truncating outcomes.'}
        records = [{**dict(r), 'id':str(r['id']), 'entry_evidence':decode(r['entry_evidence']), 'position_state':decode(r['position_state'])} for r in rows]
        try:
            result = evaluate(spec, trial['registered_at'].timestamp(), time.time(), records)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {'trial_id':str(identity), 'specification_sha256':trial['specification_sha256'],
                'records_considered':len(records), **result}

    @app.post('/state/research-trials')
    async def register_trial(body: TrialRequest):
        spec = specification(body.style)
        digest = fingerprint(spec)
        async with pool().acquire() as conn:
            async with conn.transaction():
                inserted = await conn.fetchval('INSERT INTO research_trials(id,specification,specification_sha256) VALUES($1,$2::jsonb,$3) ON CONFLICT(specification_sha256) DO NOTHING RETURNING id', uuid.uuid4(), serial(spec), digest)
                row = await conn.fetchrow('SELECT * FROM research_trials WHERE specification_sha256=$1', digest)
        return {**dict(row), 'specification':decode(row['specification']), 'duplicate':inserted is None,
                'authority':'research_only', 'note':'No trade, schedule, source weight or execution permission changed.'}

    @app.get('/state/paper-positions/source-comparison')
    async def source_comparison():
        async with pool().acquire() as conn:
            rows = await conn.fetch('SELECT id,entry_evidence,position_state FROM managed_paper_positions ORDER BY created_at DESC,id DESC LIMIT 1001')
        records = [{**dict(r), 'id':str(r['id']), 'entry_evidence':decode(r['entry_evidence']), 'position_state':decode(r['position_state'])} for r in rows[:1000]]
        return {'summary': compare(records), 'cohorts': [
            {'style':style, **compare([r for r in records if isinstance(r['position_state'],dict) and r['position_state'].get('style') == style])}
            for style in PROFILES], 'records_considered':len(records), 'truncated':len(rows)>1000,
            'scope':'Latest 1000 managed-paper entries only; operator-selected, not a registered forward trial. Read-only; no strategy or execution changes.'}

    @app.get('/state/paper-positions/{identity}/evidence')
    async def evidence(identity: uuid.UUID):
        async with pool().acquire() as conn:
            row = await conn.fetchrow('SELECT entry_evidence,evidence_sha256,initial_plan FROM managed_paper_positions WHERE id=$1', identity)
        if row is None: raise HTTPException(404, 'Paper position not found')
        return {k: decode(v) if k != 'evidence_sha256' else v for k,v in dict(row).items()}

    @app.post('/state/paper-positions')
    async def opening(body: OpenRequest):
        async with pool().acquire() as conn:
            existing = await conn.fetchval('SELECT id FROM managed_paper_positions WHERE opportunity_id=$1', body.opportunity_id)
            if existing: return {'id': str(existing), 'duplicate': True}
            row = await conn.fetchrow('SELECT * FROM opportunities WHERE id=$1', body.opportunity_id)
        if row is None: raise HTTPException(404, 'Opportunity not found')
        opportunity = dict(row)
        symbol, direction = opportunity['symbol'], str(opportunity.get('dir', '')).lower()
        if symbol not in ('BTC-PERP','ETH-PERP','SOL-PERP') or direction not in ('long','short'):
            raise HTTPException(422, 'Only directional BTC/ETH/SOL paper opportunities are supported')
        at = opportunity.get('snapshot_ts')
        if not isinstance(at, datetime) or not 0 <= (datetime.now(timezone.utc)-at).total_seconds() <= 300:
            raise HTTPException(409, 'Opportunity older than five minutes or timestamp unavailable')
        profile = PROFILES[body.style]
        # Optional context is captured before executable-side entry observations.
        # Failure is frozen explicitly and cannot become a dependency for trading.
        try:
            context_payload = await asyncio.wait_for(fetch('/liquidation-context/'+symbol), timeout=3)
            context_cutoff = time.time()
            if context_payload.get('symbol') != symbol or context_payload.get('venue') != 'bybit':
                raise ValueError('Context source or symbol mismatch')
            external_context = liquidation_snapshot(context_payload, context_cutoff)
        except Exception as exc:
            external_context = {'status': 'unavailable', 'reason': type(exc).__name__,
                                'cutoff': time.time(), 'events': [], 'authority': 'context_only', 'scoring_influence': False}
        try:
            history_payload = await asyncio.wait_for(fetch('/book-history/'+symbol), timeout=3)
            liquidity_context = book_snapshot(history_payload, time.time(), symbol)
        except Exception as exc:
            liquidity_context = {'status': 'unavailable', 'reason': type(exc).__name__,
                                 'cutoff': time.time(), 'samples': [], 'authority': 'context_only', 'scoring_influence': False}
        try:
            book, candles = await asyncio.gather(fetch('/depth/hyperliquid/'+symbol), fetch(f"/candles/hyperliquid/{symbol}?interval={profile['interval']}&limit=100"))
            now = time.time()
            volatility = atr(candles['candles'], profile['seconds'], now)
            plan = open_position(direction, body.style, body.notional, volatility, book, now)
        except Exception as exc:
            raise HTTPException(409, 'Paper entry refused: '+(str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
        # Save exactly what was received now; no later claim is backfilled into entry.
        captured = {'captured_at': now, 'opportunity': opportunity, 'entry_book': book,
                    'atr_candles': candles, 'atr': volatility,
                    'authority': 'paper_only', 'external_context': {'bybit_liquidations': external_context, 'hyperliquid_book_history': liquidity_context},
                    'external_evidence': 'Bybit receipts and Hyperliquid book history captured before entry; context only, no scoring influence. Other sources remain limited to the opportunity snapshot.'}
        encoded = serial(captured)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        identity = uuid.uuid4()
        async with pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute('SELECT pg_advisory_xact_lock(230914)')
                existing = await conn.fetchval('SELECT id FROM managed_paper_positions WHERE opportunity_id=$1', body.opportunity_id)
                if existing: return {'id': str(existing), 'duplicate': True}
                paused = await conn.fetchval('SELECT entries_paused FROM managed_paper_control WHERE singleton=true')
                if paused is not False:
                    raise HTTPException(409, 'New paper entries paused or control unavailable; existing observations and closes remain active')
                active = await conn.fetch("SELECT symbol,position_state FROM managed_paper_positions WHERE position_state->>'status'='open'")
                if len(active) >= 3 or any(r['symbol']==symbol for r in active):
                    raise HTTPException(409, 'Paper portfolio cap: three positions, one per symbol')
                if time.time()-now > 30: raise HTTPException(409, 'Entry evidence expired while waiting for portfolio lock')
                await conn.execute('''INSERT INTO managed_paper_positions
                    (id,opportunity_id,symbol,entry_evidence,evidence_sha256,initial_plan,position_state)
                    VALUES($1,$2,$3,$4::jsonb,$5,$6::jsonb,$6::jsonb)''', identity, body.opportunity_id, symbol, encoded, digest, serial(plan))
                await event(conn, identity, 'opened', plan)
        return {'id': str(identity), 'duplicate': False, 'position': plan, 'evidence_sha256': digest, 'execution_authority': False}

    @app.post('/state/paper-positions/{identity}/close')
    async def close(identity: uuid.UUID):
        try: return await update(identity, manual=True)
        except HTTPException: raise
        except Exception as exc: raise HTTPException(409, 'Paper close unavailable: '+type(exc).__name__)

    async def loop():
        while True:
            try:
                async with pool().acquire() as conn:
                    ids = await conn.fetch("SELECT id FROM managed_paper_positions WHERE position_state->>'status'='open' ORDER BY created_at LIMIT 3")
                errors = []
                for row in ids:
                    try: await update(row['id'])
                    except Exception as exc: errors.append(type(exc).__name__)
                health.update(last_tick=time.time(), last_error=', '.join(errors) or None)
            except asyncio.CancelledError: raise
            except Exception as exc: health.update(last_tick=time.time(), last_error=type(exc).__name__)
            await asyncio.sleep(15)
    background.add('managed_paper', loop)
