"""Durable operator-opened paper positions; observed order books, never real orders.

An entry gathers its evidence before the entry quote (``paper_entry_sources``), cuts
it off at the entry time (``tradesync_core.paper_entry_evidence``) and freezes it with
the plan. ``entry_admission`` holds every check that can refuse an entry once its plan
exists. The observer advances open positions on fresh books every 15 seconds and
stores settled funding as Hyperliquid publishes it (``paper_funding_store``).
"""
import asyncio
import hashlib
import json
import time
import uuid
from types import SimpleNamespace
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field
from tradesync_core import paper_eligibility as eligibility
from tradesync_core import paper_entry_evidence as entry_evidence
from tradesync_core.managed_paper import PROFILES, atr, open_position, advance, settle_funding
from tradesync_core.paper_depth import MODEL as FILL_MODEL
from tradesync_core.paper_funding import MODEL as FUNDING_MODEL, planning_from_records
from tradesync_core.paper_lifecycle_rules import COMMON, RULES, catalog
from tradesync_core.paper_rehearsal import HYPERLIQUID_BASE_FEES
from tradesync_core.source_comparison import compare
from tradesync_core.research_trial import specification, fingerprint, evaluate
from app import background, editions, paper_candidates, paper_entry_sources, paper_funding_store
from app.paper_risk_hooks import admit_entry, record_position_event

# Printed under the paper portfolio in the Cockpit.
POSITIONS_NOTE = (
    "Priced from observed order books, not exchange fills: each fill walks the displayed depth for the position's size. "
    "Fees are Hyperliquid's published base taker rate; funding is Hyperliquid's settled hourly funding, and an hour not yet "
    "published is listed as missing. 100 latest positions. Observation gaps disqualify clean performance evidence."
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


async def entry_admission(conn, symbol, plan, captured_at):
    """Every check that can refuse a paper entry once its plan exists; the one place to add another.

    Runs inside the entry transaction after the portfolio advisory lock and the
    duplicate check, just before the insert. Raise HTTPException to refuse. Named
    apart from the paper risk engine's ``paper_risk_hooks.admit_entry`` so importing
    that hook here can never shadow this function.
    """
    paused = await conn.fetchval('SELECT entries_paused FROM managed_paper_control WHERE singleton=true')
    if paused is not False:
        raise HTTPException(409, 'New paper entries paused or control unavailable; existing observations and closes remain active')
    await admit_entry(conn, symbol=symbol, plan=plan)
    active = await conn.fetch("SELECT symbol,position_state FROM managed_paper_positions WHERE position_state->>'status'='open'")
    if len(active) >= 3 or any(r['symbol']==symbol for r in active):
        raise HTTPException(409, 'Paper portfolio cap: three positions, one per symbol')
    if time.time()-captured_at > 30: raise HTTPException(409, 'Entry evidence expired while waiting for portfolio lock')


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
            symbol, current = row['symbol'], decode(row['position_state'])
            try: hours = await paper_funding_store.outstanding(conn, identity, current, time.time())
            except Exception: hours = []
        book = await fetch('/depth/hyperliquid/'+symbol) if current['status'] == 'open' else None
        try: rates, received = await paper_funding_store.published(market_data_url, symbol, hours) if hours else ({}, None)
        except Exception: rates, received = {}, None  # funding stays listed as missing; exits never wait for it
        async with pool().acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow('SELECT position_state FROM managed_paper_positions WHERE id=$1 FOR UPDATE', identity)
                current = decode(row['position_state'])
                now = time.time()
                added, settled = await paper_funding_store.settle_rows(conn, identity, symbol, current, rates, received, now)
                if current['status'] == 'open':
                    result = advance(current, book, now, manual_close=manual, funding_rows=settled)
                    kind = 'closed' if result['status']=='closed' else 'observed'
                elif added:
                    result, kind = settle_funding(current, settled), 'funding_settled'
                else:
                    return current
                await conn.execute('UPDATE managed_paper_positions SET position_state=$2::jsonb,updated_at=now() WHERE id=$1', identity, serial(result))
                await event(conn, identity, kind, {'position': result, 'book': book, 'funding_rows_added': added})
                if kind == 'closed':  # booked once, at the close; late funding is not yet booked (see the merge change record)
                    await record_position_event(conn, identity, result)
        return result

    @app.get('/state/paper-control')
    async def paper_control():
        async with pool().acquire() as conn:
            row = await conn.fetchrow('SELECT entries_paused,reason,updated_at FROM managed_paper_control WHERE singleton=true')
        if row is None: raise HTTPException(503, 'Paper control missing; entries disabled')
        return {**dict(row), 'authority':'paper_only', 'note':'Pauses new entries only. Observation and closing remain active; existing positions are not liquidated.'}

    @app.post('/state/paper-control')
    async def change_paper_control():
        # Retired 15 September: pause and resume go through POST /state/paper-pause, which records the
        # operator's name and reason and runs the resume checks under the same lock.
        raise HTTPException(410, 'Retired: pause or resume paper entries with POST /state/paper-pause (operator and reason required)')

    @app.get('/state/paper-positions')
    async def listing():
        async with pool().acquire() as conn:
            rows = await conn.fetch('SELECT id,opportunity_id,symbol,created_at,updated_at,evidence_sha256,position_state FROM managed_paper_positions ORDER BY created_at DESC LIMIT 100')
        return {'positions': [{**dict(r), 'position_state': decode(r['position_state'])} for r in rows],
                'worker': health, 'execution_authority': False,
                'note': POSITIONS_NOTE}

    @app.get('/state/paper-positions/rules')
    async def rules():
        return {**catalog(), 'fees': HYPERLIQUID_BASE_FEES.to_dict(), 'fill_model': FILL_MODEL, 'funding_model': FUNDING_MODEL,
                'evidence_schema': entry_evidence.SCHEMA_VERSION, 'authority': 'paper_only'}

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
        document = decode(row['entry_evidence'])
        recomputed = entry_evidence.digest(document) if 'schema_version' in document else hashlib.sha256(serial(document).encode()).hexdigest()
        return {'entry_evidence': document, 'evidence_sha256': row['evidence_sha256'], 'initial_plan': decode(row['initial_plan']),
                'digest_verified': recomputed == row['evidence_sha256']}

    @app.post('/state/paper-positions')
    async def opening(body: OpenRequest):
        async with pool().acquire() as conn:
            existing = await conn.fetchval('SELECT id FROM managed_paper_positions WHERE opportunity_id=$1', body.opportunity_id)
            if existing: return {'id': str(existing), 'duplicate': True}
            row = await conn.fetchrow('SELECT * FROM opportunities WHERE id=$1', body.opportunity_id)
        if row is None: raise HTTPException(404, 'Opportunity not found')
        opportunity = dict(row)
        symbol, direction = opportunity['symbol'], eligibility.direction(opportunity)
        refusal = eligibility.opportunity_refusal(opportunity, time.time())
        refusal = refusal or eligibility.universe_refusal(symbol, await editions.tracked_symbols(market_data_url))
        if refusal: raise HTTPException(*refusal)
        rules = RULES[body.style]
        # Evidence is received before the entry quote is requested; nothing later enters the entry.
        gathered, context = await paper_entry_sources.gather(pool(), market_data_url, editions.SELF_URL, opportunity)
        try:
            book, candles = await asyncio.gather(fetch('/depth/hyperliquid/'+symbol), fetch(f"/candles/hyperliquid/{symbol}?interval={rules.atr_interval}&limit=100"))
            now = time.time()
            gathered['resting_liquidity'] = paper_entry_sources.with_entry_book(gathered.get('resting_liquidity'), book, now)
            volatility = atr(candles['candles'], rules.atr_seconds, now, rules.atr_period)
            captured = entry_evidence.document(gathered, now, inputs={
                'captured_at': now, 'entry_book': book, 'atr_candles': candles, 'atr': volatility, 'external_context': context})
            planning = planning_from_records(captured['items']['funding']['records'], COMMON.planning_funding_floor_bps_hour)
            plan = open_position(direction, body.style, body.notional, volatility, book, now, planning_funding=planning)
        except Exception as exc:
            raise HTTPException(409, 'Paper entry refused: '+(str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
        digest = entry_evidence.digest(captured)
        identity = uuid.uuid4()
        async with pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute('SELECT pg_advisory_xact_lock(230914)')
                existing = await conn.fetchval('SELECT id FROM managed_paper_positions WHERE opportunity_id=$1', body.opportunity_id)
                if existing: return {'id': str(existing), 'duplicate': True}
                await entry_admission(conn, symbol, plan, now)
                await conn.execute('''INSERT INTO managed_paper_positions
                    (id,opportunity_id,symbol,entry_evidence,evidence_sha256,initial_plan,position_state)
                    VALUES($1,$2,$3,$4::jsonb,$5,$6::jsonb,$6::jsonb)''', identity, body.opportunity_id, symbol, entry_evidence.canonical_json(captured), digest, serial(plan))
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
                    # Open positions, and closed ones whose last settlements are not stored yet (for a day after exit).
                    ids = await conn.fetch("""SELECT id FROM managed_paper_positions WHERE position_state->>'status'='open'
                        OR (position_state->'funding'->>'status'='awaiting_rows' AND (position_state->>'exit_time')::float8 > $1)
                        ORDER BY created_at LIMIT 20""", time.time()-86400)
                errors = []
                for row in ids:
                    try: await update(row['id'])
                    except Exception as exc: errors.append(type(exc).__name__)
                health.update(last_tick=time.time(), last_error=', '.join(errors) or None)
            except asyncio.CancelledError: raise
            except Exception as exc: health.update(last_tick=time.time(), last_error=type(exc).__name__)
            await asyncio.sleep(15)
    background.add('managed_paper', loop)
    paper_candidates.register(app, pool, market_data_url=market_data_url)
    paper_funding_store.register(app, pool)
    return SimpleNamespace(update=update, loop=loop)
