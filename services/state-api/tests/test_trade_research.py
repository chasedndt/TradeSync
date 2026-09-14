from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from app.main import app, state
from app import trade_research

client = TestClient(app)


def pool(conn):
    @asynccontextmanager
    async def acquire():
        yield conn
    return MagicMock(acquire=acquire)


def test_diagnostics_exclude_ineligible_rows_without_hiding_the_denominator():
    conn = MagicMock(fetch=AsyncMock(return_value=[
        {'asset':'BTC','timeframe':'15m','direction':'long','signal_eligible':True,'outcome_eligible':True},
        {'asset':'ETH','timeframe':'1h','direction':'long','signal_eligible':False}]))
    with patch.object(state, 'pool', pool(conn)), patch.object(trade_research, '_methodology', AsyncMock(return_value=('v1', {}))):
        response = client.get('/state/trade-research/diagnostics')
    assert response.status_code==200
    body=response.json()
    assert body['excluded']==1 and body['summary']['trades']==1
    assert body['summary']['net_usdc'] is None and body['truncated'] is False


def test_replay_refuses_unknown_symbols_and_invalid_costs():
    for body in ({'symbol':'DOGE-PERP'}, {'style':'autonomous'}, {'fee_bps':-1}):
        assert client.post('/state/trade-research/replay', json=body).status_code==422


def test_candle_proxy_preserves_explicit_time_bounds():
    from app import main
    response = MagicMock(status_code=200)
    response.json.return_value = {'candles': []}
    with patch.object(main, '_market_data_get', return_value=response) as fetch:
        result = client.get('/state/market/candles?start_ms=1000&end_ms=2000')
    assert result.status_code==200
    assert 'start_ms=1000' in fetch.call_args.args[0] and 'end_ms=2000' in fetch.call_args.args[0]
    assert client.get('/state/market/candles?start_ms=2000&end_ms=1000').status_code==400


def test_evidence_coverage_is_explicitly_not_strategy_influence():
    conn = MagicMock(fetch=AsyncMock(side_effect=[
        [{'source': 'tradingview', 'accepted': 7, 'latest': datetime.now(timezone.utc)}],
        [{'source': 'tradingview', 'claims': 3, 'measured': 2}]]))
    with patch.object(state, 'pool', pool(conn)):
        response = client.get('/state/trade-research/evidence')
    assert response.status_code == 200
    assert response.json()['sources'][0]['measured'] == 2
    assert 'candles only' in response.json()['note']
