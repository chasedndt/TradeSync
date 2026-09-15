from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from fastapi.testclient import TestClient
from app.main import app, state
from tradesync_core.research_trial import specification, fingerprint

client = TestClient(app)

def pool(conn):
    @asynccontextmanager
    async def acquire(): yield conn
    return MagicMock(acquire=acquire)


def test_invalid_request_never_reaches_data_or_venue():
    with patch('app.managed_paper.httpx.AsyncClient') as venue:
        assert client.post('/state/paper-positions', json={'opportunity_id':'not-an-id'}).status_code == 422
        assert client.post('/state/paper-positions', json={'opportunity_id':str(uuid.uuid4()),'notional':1001}).status_code == 422
        venue.assert_not_called()


def test_duplicate_source_does_not_open_another_position():
    existing = uuid.uuid4()
    conn = MagicMock(fetchval=AsyncMock(return_value=existing))
    with patch.object(state,'pool',pool(conn)), patch('app.managed_paper.httpx.AsyncClient') as venue:
        result = client.post('/state/paper-positions', json={'opportunity_id':str(uuid.uuid4())})
        venue.assert_not_called()
    assert result.json() == {'id':str(existing),'duplicate':True}


def test_stale_opportunity_cannot_be_backdated_into_new_paper_trade():
    conn = MagicMock(fetchval=AsyncMock(return_value=None), fetchrow=AsyncMock(return_value={
        'symbol':'BTC-PERP','dir':'LONG','snapshot_ts':datetime.now(timezone.utc)-timedelta(hours=1)}))
    with patch.object(state,'pool',pool(conn)), patch('app.managed_paper.httpx.AsyncClient') as venue:
        result = client.post('/state/paper-positions', json={'opportunity_id':str(uuid.uuid4())})
        venue.assert_not_called()
    assert result.status_code == 409


def test_empty_portfolio_is_explicitly_not_execution_authority():
    conn = MagicMock(fetch=AsyncMock(return_value=[]))
    with patch.object(state,'pool',pool(conn)):
        result = client.get('/state/paper-positions')
    assert result.status_code == 200
    assert result.json()['positions'] == []
    assert result.json()['execution_authority'] is False


def test_empty_source_comparison_is_unmeasured_with_separate_styles():
    conn = MagicMock(fetch=AsyncMock(return_value=[]))
    with patch.object(state,'pool',pool(conn)):
        result = client.get('/state/paper-positions/source-comparison')
    assert result.status_code == 200
    body = result.json()
    assert body['summary']['paired_mean_difference_bps'] is None
    assert body['summary']['promotion_allowed'] is False
    assert [c['style'] for c in body['cohorts']] == ['scalp','intraday','swing']


def trial_row():
    spec = specification('scalp')
    return {'id':uuid.uuid4(),'specification':spec,'specification_sha256':fingerprint(spec),'registered_at':datetime.now(timezone.utc)-timedelta(minutes=1)}


def test_trial_evaluation_empty_is_collecting_not_success():
    trial = trial_row()
    conn = MagicMock(fetchrow=AsyncMock(return_value=trial),fetch=AsyncMock(return_value=[]))
    with patch.object(state,'pool',pool(conn)):
        result = client.get(f"/state/research-trials/{trial['id']}/evaluation")
    assert result.status_code == 200
    assert result.json()['state'] == 'collecting'
    assert result.json()['comparison']['eligible'] == 0
    assert result.json()['promotion_allowed'] is False


def test_trial_evaluation_refuses_truncated_population():
    trial = trial_row()
    conn = MagicMock(fetchrow=AsyncMock(return_value=trial),fetch=AsyncMock(return_value=[{}]*10001))
    with patch.object(state,'pool',pool(conn)):
        result = client.get(f"/state/research-trials/{trial['id']}/evaluation")
    assert result.json()['state'] == 'incomplete_record_window'
    assert 'comparison' not in result.json()


def test_trial_fingerprint_mismatch_stops_before_outcome_query():
    trial = trial_row(); trial['specification_sha256'] = 'wrong'
    conn = MagicMock(fetchrow=AsyncMock(return_value=trial),fetch=AsyncMock())
    with patch.object(state,'pool',pool(conn)):
        result = client.get(f"/state/research-trials/{trial['id']}/evaluation")
    assert result.status_code == 409
    conn.fetch.assert_not_awaited()


def test_missing_persistent_paper_control_fails_closed():
    conn = MagicMock(fetchrow=AsyncMock(return_value=None))
    with patch.object(state,'pool',pool(conn)):
        result = client.get('/state/paper-control')
    assert result.status_code == 503


def test_paper_control_does_not_claim_to_close_positions():
    conn = MagicMock(fetchrow=AsyncMock(return_value={'entries_paused':True,'reason':'Operator review','updated_at':datetime.now(timezone.utc)}))
    with patch.object(state,'pool',pool(conn)):
        result = client.get('/state/paper-control')
    assert result.json()['entries_paused'] is True
    assert 'not liquidated' in result.json()['note']


def test_the_unaudited_pause_route_is_retired():
    with patch.object(state,'pool',None):
        result = client.post('/state/paper-control',json={'entries_paused':False,'reason':'Operator review'})
    assert result.status_code == 410 and '/state/paper-pause' in result.json()['detail']
