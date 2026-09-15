import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import background
from app import paper_risk_readmodel as readmodel
from app import paper_risk_routes as routes
from app.main import app, state
from paper_fakes import FakeConn, FakePool
from tradesync_core.paper_account import snapshot
from tradesync_core.paper_correlation import BucketView

client = TestClient(app)
LIMITS = dict(daily_loss_limit_usdc=200.0, max_drawdown_fraction=0.06, max_gross_exposure_fraction=0.35,
              max_symbol_exposure_fraction=0.12, max_bucket_exposure_fraction=0.25, correlation_threshold=0.7,
              max_concurrent_positions=3, max_entry_quote_age_s=15.0, max_mark_age_s=60.0)
BODY = {'operator': 'chase', 'reason': 'Stop all paper risk for review'}


def now_utc():
    return datetime.now(timezone.utc)


def test_routes_and_loops_are_registered():
    paths = {(route.path, method) for route in app.routes for method in getattr(route, 'methods', ())}
    for expected in [('/state/paper-account', 'GET'), ('/state/paper-limits', 'GET'), ('/state/paper-limits', 'POST'),
                     ('/state/paper-risk', 'GET'), ('/state/paper-pause', 'POST'), ('/state/paper-kill', 'POST'),
                     ('/state/paper-kill/resume', 'POST'), ('/state/paper-reconciliation', 'GET')]:
        assert expected in paths
    assert {'paper_reconciliation', 'paper_risk_monitor', 'paper_correlation'} <= set(background.registered())


def test_kill_and_resume_need_an_operator_a_reason_and_confirmation():
    with patch.object(state, 'pool', None):
        for body in (BODY, {**BODY, 'confirm': False}, {**BODY, 'operator': '  ', 'confirm': True}, {**BODY, 'reason': '   ', 'confirm': True}):
            assert client.post('/state/paper-kill', json=body).status_code == 422
            assert client.post('/state/paper-kill/resume', json=body).status_code == 422
        assert client.post('/state/paper-kill', json={**BODY, 'confirm': True}).status_code == 503


def test_limit_changes_need_a_value_a_reason_and_valid_ranges():
    with patch.object(state, 'pool', None):
        assert client.post('/state/paper-limits', json=BODY).status_code == 422
        assert client.post('/state/paper-limits', json={**BODY, 'reason': 'x', 'daily_loss_limit_usdc': 150}).status_code == 422
        for field, value in (('max_drawdown_fraction', 1.5), ('max_concurrent_positions', 0), ('correlation_threshold', 0), ('max_entry_quote_age_s', 31)):
            assert client.post('/state/paper-limits', json={**BODY, field: value}).status_code == 422


def test_limit_change_is_audited_under_the_entry_lock(monkeypatch):
    lock = AsyncMock()
    row = {**LIMITS, 'daily_loss_limit_usdc': 150.0, 'operator': 'chase', 'reason': 'Tighten the daily loss limit', 'updated_at': now_utc()}
    update = AsyncMock(return_value=(dict(LIMITS), row))
    monkeypatch.setattr(routes.control, 'take_entry_lock', lock)
    monkeypatch.setattr(routes.limit_store, 'update', update)
    with patch.object(state, 'pool', FakePool(FakeConn())):
        response = client.post('/state/paper-limits', json={'operator': 'chase', 'reason': 'Tighten the daily loss limit', 'daily_loss_limit_usdc': 150})
    assert response.status_code == 200, response.text
    lock.assert_awaited_once()
    assert update.await_args.kwargs == {'changes': {'daily_loss_limit_usdc': 150.0}, 'operator': 'chase', 'reason': 'Tighten the daily loss limit'}
    assert response.json()['limits']['daily_loss_limit_usdc'] == 150.0 and response.json()['previous']['daily_loss_limit_usdc'] == 200.0


def test_inconsistent_limits_are_refused(monkeypatch):
    monkeypatch.setattr(routes.control, 'take_entry_lock', AsyncMock())
    monkeypatch.setattr(routes.limit_store, 'update', AsyncMock(side_effect=ValueError('Per-symbol exposure must not exceed the correlated bucket limit')))
    with patch.object(state, 'pool', FakePool(FakeConn())):
        response = client.post('/state/paper-limits', json={**BODY, 'max_symbol_exposure_fraction': 0.5})
    assert response.status_code == 422 and 'Per-symbol' in response.json()['detail']


def pause_world(monkeypatch, *, kill_active=False, snap=None):
    set_pause = AsyncMock(return_value={'entries_paused': True, 'reason': 'Review before the US open', 'updated_at': now_utc()})
    monkeypatch.setattr(routes.control, 'take_entry_lock', AsyncMock())
    monkeypatch.setattr(routes.control, 'kill_state', AsyncMock(return_value={'active': kill_active, 'operator': 'chase', 'reason': 'Stop all paper risk'}))
    monkeypatch.setattr(routes.control, 'set_pause', set_pause)
    monkeypatch.setattr(routes.runs, 'latest_run', AsyncMock(return_value={'status': 'clean', 'started_at': now_utc(), 'finished_at': now_utc(), 'mismatches': []}))
    monkeypatch.setattr(routes.limit_store, 'load', AsyncMock(return_value=dict(LIMITS)))
    monkeypatch.setattr(routes.view, 'account_snapshot', AsyncMock(return_value=snap))
    return set_pause


def test_resuming_entries_is_refused_while_the_kill_switch_is_engaged(monkeypatch):
    set_pause = pause_world(monkeypatch, kill_active=True)
    with patch.object(state, 'pool', FakePool(FakeConn())):
        response = client.post('/state/paper-pause', json={**BODY, 'entries_paused': False})
    assert response.status_code == 409 and '[KILL_SWITCH_ACTIVE]' in response.json()['detail']
    set_pause.assert_not_awaited()


def test_resuming_entries_is_refused_during_a_standing_loss_breach(monkeypatch):
    breached = snapshot(now_s=time.time(), starting_capital=10_000, cash=9_750, stored_peak=10_000, marks=(), realised_today=-250, unrealised_at_day_start=0)
    set_pause = pause_world(monkeypatch, snap=breached)
    with patch.object(state, 'pool', FakePool(FakeConn())):
        response = client.post('/state/paper-pause', json={**BODY, 'entries_paused': False})
    assert response.status_code == 409 and '[DAILY_LOSS_LIMIT]' in response.json()['detail']
    set_pause.assert_not_awaited()


def test_pausing_is_audited_with_the_operator(monkeypatch):
    set_pause = pause_world(monkeypatch)
    with patch.object(state, 'pool', FakePool(FakeConn())):
        response = client.post('/state/paper-pause', json={'operator': 'chase', 'reason': 'Review before the US open', 'entries_paused': True})
    assert response.status_code == 200, response.text
    assert set_pause.await_args.kwargs == {'paused': True, 'operator': 'chase', 'reason': 'Review before the US open'}


def risk_world(monkeypatch, *, cash=10_000.0, realised_today=0.0):
    measured = now_utc()
    monkeypatch.setattr(readmodel.control, 'pause_state', AsyncMock(return_value={'entries_paused': False, 'reason': 'Resumed after review', 'updated_at': now_utc()}))
    monkeypatch.setattr(readmodel.control, 'kill_state', AsyncMock(return_value={'active': False, 'operator': 'migration 031', 'reason': 'Not engaged', 'changed_at': now_utc()}))
    monkeypatch.setattr(readmodel.control, 'recent_control_events', AsyncMock(return_value=[]))
    monkeypatch.setattr(readmodel.control, 'recent_kill_events', AsyncMock(return_value=[]))
    monkeypatch.setattr(readmodel.runs, 'latest_run', AsyncMock(return_value={'status': 'clean', 'started_at': now_utc(), 'finished_at': now_utc(), 'mismatches': [], 'gaps': []}))
    monkeypatch.setattr(readmodel.limit_store, 'load', AsyncMock(return_value={**LIMITS, 'operator': 'migration 031', 'reason': 'Initial conservative paper limits', 'updated_at': now_utc()}))
    monkeypatch.setattr(readmodel.view, 'account_snapshot', AsyncMock(return_value=snapshot(
        now_s=time.time(), starting_capital=10_000, cash=cash, stored_peak=10_000, marks=(), realised_today=realised_today, unrealised_at_day_start=0)))
    monkeypatch.setattr(readmodel.view, 'buckets', AsyncMock(return_value=(
        BucketView(measured.timestamp(), (('BTC-PERP', 'ETH-PERP'), ('HYPE-PERP',)), frozenset({'PUMP-PERP'})),
        {'measured_at': measured, 'bar_interval': '1h', 'window_bars': 168, 'source': 'test measurement'})))


def test_risk_state_names_each_block_and_how_much_of_each_limit_is_used(monkeypatch):
    risk_world(monkeypatch, cash=9_750, realised_today=-250)
    with patch.object(state, 'pool', FakePool(FakeConn())):
        body = client.get('/state/paper-risk').json()
    assert body['entries_allowed'] is False
    assert [b['code'] for b in body['blocking']] == ['DAILY_LOSS_LIMIT']
    assert body['utilisation']['daily_loss']['fraction_of_limit'] == 1.25
    assert body['correlation']['buckets'] == [['BTC-PERP', 'ETH-PERP'], ['HYPE-PERP']] and body['correlation']['unmeasured'] == ['PUMP-PERP']
    assert body['authority'] == 'paper_only'


def test_clean_risk_state_allows_entries(monkeypatch):
    risk_world(monkeypatch)
    with patch.object(state, 'pool', FakePool(FakeConn())):
        body = client.get('/state/paper-risk').json()
    assert body['entries_allowed'] is True and body['blocking'] == []


def test_last_reconciliation_is_published(monkeypatch):
    run = {'id': 'r1', 'trigger': 'startup', 'started_at': now_utc(), 'finished_at': now_utc(), 'status': 'mismatch',
           'positions_checked': 3, 'open_positions': 1, 'account': {}, 'error': None,
           'mismatches': [{'code': 'LEDGER_MISSING_ENTRY', 'detail': 'Closed paper position has no realised ledger entry', 'position_id': 'p'}],
           'gaps': [{'position_id': 'p', 'symbol': 'BTC-PERP', 'started_at': '2026-09-15T10:00:00+00:00', 'ended_at': None, 'seconds': None, 'ongoing': True}]}
    monkeypatch.setattr(readmodel.runs, 'latest_run', AsyncMock(return_value=run))
    monkeypatch.setattr(readmodel.runs, 'recent_gaps', AsyncMock(return_value=[]))
    with patch.object(state, 'pool', FakePool(FakeConn())):
        body = client.get('/state/paper-reconciliation').json()
    last = body['last_run']
    assert (last['status'], last['positions_checked'], last['mismatches'][0]['code'], last['gaps'][0]['ongoing']) == ('mismatch', 3, 'LEDGER_MISSING_ENTRY', True)
    assert isinstance(last['finished_at'], str)


def test_account_is_unavailable_until_reconciliation_creates_it(monkeypatch):
    monkeypatch.setattr(readmodel.accounts, 'load_account', AsyncMock(return_value=None))
    monkeypatch.setattr(readmodel.view, 'account_snapshot', AsyncMock(return_value=None))
    with patch.object(state, 'pool', FakePool(FakeConn())):
        assert client.get('/state/paper-account').status_code == 503
