"""Cost-aware diagnostics of the real ledger and separately stored paper replays."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.strikezone_lab import _methodology
from tradesync_core.trade_economics import summarize
from tradesync_core.trade_replay import PROFILES, replay

router = APIRouter(tags=['trade-research'])
_replay_lock = asyncio.Lock()

DIAGNOSTIC_SQL = '''
WITH selected AS MATERIALIZED (
    SELECT * FROM sz_signals WHERE methodology_version=$1 AND direction IN ('long','short')
    ORDER BY signal_at DESC LIMIT 10001
), latest AS MATERIALIZED (
    SELECT DISTINCT ON (x.signal_id) x.* FROM sz_outcomes x
    JOIN selected s ON s.signal_id=x.signal_id
    WHERE x.methodology_version=$1
    ORDER BY x.signal_id,x.exit_at DESC NULLS LAST,x.outcome_id
)
SELECT s.asset, s.timeframe, s.direction, s.signal_at, s.entry_price,
       s.invalidation_price, s.target_price, s.analysis_eligible AS signal_eligible,
       o.outcome_id, o.exit_reason, o.holding_minutes, o.entry_fill_price,
       o.exit_fill_price, o.quantity, o.net_pnl_usdc, o.gross_pnl_usdc,
       o.analysis_eligible AS outcome_eligible
FROM selected s LEFT JOIN latest o ON o.signal_id=s.signal_id
ORDER BY s.signal_at DESC
'''


class ReplayRequest(BaseModel):
    symbol: str = Field('BTC-PERP', pattern=r'^(BTC|ETH|SOL)-PERP$')
    style: str = Field('scalp', pattern=r'^(scalp|swing)$')
    fee_bps: float = Field(4.5, ge=0, le=100, allow_inf_nan=False)
    slippage_bps: float = Field(2, ge=0, le=100, allow_inf_nan=False)
    funding_bps_hour: float = Field(.125, ge=0, le=10, allow_inf_nan=False)


def register(app, state, *, market_data_url: str):
    def pool():
        if not state.pool:
            raise HTTPException(503, 'Database not ready')
        return state.pool

    @router.get('/state/trade-research/diagnostics')
    async def diagnostics():
        async with pool().acquire() as conn:
            method, _ = await _methodology(conn)
            raw = [dict(r) for r in await conn.fetch(DIAGNOSTIC_SQL, method)]
        truncated = len(raw) > 10000
        raw = raw[:10000]
        eligible = [r for r in raw if r['signal_eligible'] and r.get('outcome_eligible') is not False]
        groups = defaultdict(list)
        for row in eligible:
            groups[(row['asset'], row['timeframe'])].append(row)
        return {'schema_version': 'trade_diagnostics_v1', 'methodology_version': method,
                'observed_at': datetime.now(timezone.utc).isoformat(), 'sample_limit': 10000,
                'truncated': truncated, 'excluded': len(raw)-len(eligible),
                'summary': summarize(eligible),
                'cohorts': [{'asset': a, 'timeframe': t, **summarize(rows)} for (a,t), rows in sorted(groups.items())],
                'note': 'Actual eligible ledger records, latest outcome per signal within the active methodology. Price move is unlevered; USDC P&L depends on recorded position size. Timeframe is the entry chart, not a proven scalp/swing strategy. Missing values are not zero. TradeSync opportunity horizons are observations, not actual trade exits.'}

    @router.post('/state/trade-research/replay')
    async def run_replay(req: ReplayRequest):
        pool()
        if _replay_lock.locked():
            raise HTTPException(409, 'One replay is already running; wait for completion')
        async with _replay_lock:
            profile = PROFILES[req.style]
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=45) as client:
                    response = await client.get(f'{market_data_url}/candles/hyperliquid/{req.symbol}',
                                                params={'interval': profile.interval, 'limit': 1000})
                    response.raise_for_status()
                    candles = response.json()['candles']
                result = await asyncio.to_thread(replay, candles, req.style, fee_bps=req.fee_bps,
                                                 slippage_bps=req.slippage_bps, funding_bps_hour=req.funding_bps_hour,
                                                 now_s=time.time())
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                raise HTTPException(422, f'Replay unavailable: {type(exc).__name__}; verify complete candle coverage') from None
            ident = str(uuid.uuid4())
            async with pool().acquire() as conn:
                row = await conn.fetchrow('''INSERT INTO trade_research_runs
                    (id,symbol,style,version,input_sha256,candles,result)
                    VALUES ($1::uuid,$2,$3,$4,$5,$6::jsonb,$7::jsonb) RETURNING created_at''',
                    ident, req.symbol, req.style, result['version'], result['input_sha256'],
                    json.dumps(candles), json.dumps(result))
            return {'id': ident, 'symbol': req.symbol, 'created_at': row['created_at'].isoformat(), **result}

    @router.get('/state/trade-research/evidence')
    async def evidence():
        async with pool().acquire() as conn:
            intake = await conn.fetch('''SELECT source,count(*) AS accepted,max(received_at) AS latest
                FROM quarantine_intake WHERE accepted GROUP BY source ORDER BY source''')
            claims = await conn.fetch('''SELECT c.source,count(*) AS claims,
                count(*) FILTER (WHERE EXISTS (SELECT 1 FROM evidence_claim_outcomes o
                    WHERE o.claim_id=c.id AND o.status='measured')) AS measured
                FROM evidence_claims c GROUP BY c.source''')
        by_source = {r['source']: r for r in claims}
        return {'sources': [{'source': r['source'], 'accepted': r['accepted'],
                             'latest': r['latest'].isoformat() if r['latest'] else None,
                             'claims': by_source.get(r['source'], {}).get('claims', 0),
                             'measured': by_source.get(r['source'], {}).get('measured', 0)} for r in intake],
                'scope': 'All retained accepted intake and extracted claim records; one measured claim needs at least one measured horizon.',
                'note': 'Ingested is not influential. Claim measurements and earned evidence cards are separate from the legacy Signal Ledger strategy. New scalp/swing replays use candles only. External evidence needs an immutable as-of-entry join and held-out incremental value before it can change those decisions.'}

    @router.get('/state/trade-research/runs')
    async def runs():
        async with pool().acquire() as conn:
            rows = await conn.fetch('SELECT id,created_at,symbol,result FROM trade_research_runs ORDER BY created_at DESC LIMIT 20')
        return {'runs': [{'id': str(r['id']), 'created_at': r['created_at'].isoformat(), 'symbol': r['symbol'],
                          **(json.loads(r['result']) if isinstance(r['result'], str) else r['result'])} for r in rows]}

    app.include_router(router)
