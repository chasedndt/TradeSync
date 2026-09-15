import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app import paper_risk_gate as gate
from app import paper_risk_signals
from paper_fakes import SYMBOL, FakeMarket, market_routes
from paper_fakes import FakeConn as PositionsConn
from test_paper_positions_routes import build, entry_handlers, opportunity, post_entry
from tradesync_core.paper_account import Mark, snapshot
from tradesync_core.paper_correlation import BucketView
from tradesync_core.paper_lifecycle_rules import LIFECYCLE_VERSION
from tradesync_core.paper_limits import Code

NOW = paper_risk_signals.PROCESS_STARTED_AT + 3600
LIMITS = dict(daily_loss_limit_usdc=200.0, max_drawdown_fraction=0.06, max_gross_exposure_fraction=0.35,
              max_symbol_exposure_fraction=0.12, max_bucket_exposure_fraction=0.25, correlation_threshold=0.7,
              max_concurrent_positions=3, max_entry_quote_age_s=15.0, max_mark_age_s=60.0)
PLAN = {'notional': 1000.0, 'planned_risk_usdc': 20.0, 'entry_quote_time': NOW - 1}


def at(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc)


def clean_run():
    return {'status': 'clean', 'started_at': at(NOW - 60), 'finished_at': at(NOW - 59), 'mismatches': []}


def account(cash=10_000.0, realised_today=0.0, marks=()):
    return snapshot(now_s=NOW, starting_capital=10_000, cash=cash, stored_peak=10_000, marks=marks,
                    realised_today=realised_today, unrealised_at_day_start=0)


@pytest.fixture
def world(monkeypatch):
    current = {'kill': {'active': False, 'operator': 'migration 031', 'reason': 'not engaged'}, 'run': clean_run(),
               'limits': dict(LIMITS), 'account': account(), 'buckets': BucketView(NOW - 60, (('BTC-PERP', 'ETH-PERP'),), frozenset())}
    monkeypatch.setattr(gate.control, 'kill_state', AsyncMock(side_effect=lambda conn: current['kill']))
    monkeypatch.setattr(gate.runs, 'latest_run', AsyncMock(side_effect=lambda conn: current['run']))
    monkeypatch.setattr(gate.limit_store, 'load', AsyncMock(side_effect=lambda conn: current['limits']))
    monkeypatch.setattr(gate.view, 'account_snapshot', AsyncMock(side_effect=lambda conn, now_s, lock=None: current['account']))
    monkeypatch.setattr(gate.view, 'buckets', AsyncMock(side_effect=lambda conn, threshold: (current['buckets'], None)))
    paper_risk_signals.take('evaluate')
    return current


def refused(code, plan=PLAN):
    with pytest.raises(HTTPException) as caught:
        asyncio.run(gate.admit(object(), symbol='BTC-PERP', plan=plan, now_s=NOW))
    assert caught.value.status_code == 409
    assert caught.value.detail.startswith(f'Paper entry refused [{code}]')
    return caught.value.detail


def test_clean_state_admits(world):
    assert asyncio.run(gate.admit(object(), symbol='BTC-PERP', plan=PLAN, now_s=NOW)) is None
    assert gate.view.account_snapshot.await_args.kwargs == {'lock': 'share'}


def test_engaged_or_missing_kill_switch_refuses_first(world):
    world['kill'], world['run'] = {'active': True, 'operator': 'chase', 'reason': 'Stop for review'}, None
    assert 'chase' in refused(Code.KILL_SWITCH_ACTIVE)
    world['kill'] = None
    refused(Code.KILL_SWITCH_ACTIVE)


def test_missing_old_or_mismatched_reconciliation_refuses(world):
    world['run'] = None
    refused(Code.RECONCILIATION_PENDING)
    world['run'] = {**clean_run(), 'started_at': at(paper_risk_signals.PROCESS_STARTED_AT - 5)}
    refused(Code.RECONCILIATION_PENDING)
    world['run'] = {**clean_run(), 'finished_at': at(NOW - 901)}
    refused(Code.RECONCILIATION_PENDING)
    world['run'] = {**clean_run(), 'status': 'mismatch', 'mismatches': [{'code': 'LEDGER_MISSING_ENTRY', 'detail': 'Closed paper position has no realised ledger entry'}]}
    assert 'no realised ledger entry' in refused(Code.RECONCILIATION_MISMATCH)


def test_missing_limits_or_account_refuses(world):
    world['limits'] = None
    refused(Code.LIMITS_UNAVAILABLE)
    world['limits'], world['account'] = dict(LIMITS), None
    refused(Code.ACCOUNT_UNAVAILABLE)


def test_daily_loss_breach_refuses_and_asks_the_monitor_to_pause(world):
    world['account'] = account(cash=9_790, realised_today=-210)
    refused(Code.DAILY_LOSS_LIMIT)
    assert paper_risk_signals.take('evaluate') is True


def test_refusal_leads_with_the_first_limit_and_lists_the_rest_without_pausing(world):
    world['account'] = account(marks=[Mark('e', 'ETH-PERP', 'long', 20, 100.0, 2000.0, 0.0, NOW - 5, 'observed_exit_side')])
    detail = refused(Code.STALE_ENTRY_QUOTE, plan={**PLAN, 'entry_quote_time': NOW - 20})
    assert 'CORRELATED_EXPOSURE_LIMIT' in detail
    assert paper_risk_signals.take('evaluate') is False


def test_unreadable_state_refuses_rather_than_admits(world, monkeypatch):
    monkeypatch.setattr(gate.control, 'kill_state', AsyncMock(side_effect=RuntimeError('database gone')))
    assert 'RuntimeError' in refused(Code.ACCOUNT_UNAVAILABLE)


# The hook inside the real entry route: under the lock, after the pause check, before the insert.

class OrderedConn(PositionsConn):
    """The positions route fake, recording the order of the statements these tests care about."""

    def __init__(self, handlers, order):
        super().__init__(handlers)
        self.order = order

    async def fetchval(self, sql, *args, timeout=None):
        self.order.append(sql.strip())
        return await super().fetchval(sql, *args, timeout=timeout)

    async def execute(self, sql, *args, timeout=None):
        self.order.append(sql.strip())
        return await super().execute(sql, *args, timeout=timeout)


def entry_attempt(outcome):
    FakeMarket.routes, FakeMarket.requested = market_routes(), []
    order = []
    opp = opportunity()
    conn = OrderedConn(entry_handlers(opp), order)

    async def admit(conn_, *, symbol, plan):
        order.append(f"admit {symbol} {plan['version']}")
        if isinstance(outcome, Exception):
            raise outcome

    with patch('httpx.AsyncClient', FakeMarket), patch('app.managed_paper.admit_entry', side_effect=admit):
        client, _ = build(conn)
        response = post_entry(client, opp)
    return response, order, conn


def test_risk_refusal_in_the_entry_route_inserts_nothing():
    response, _, conn = entry_attempt(HTTPException(409, 'Paper entry refused [DAILY_LOSS_LIMIT]: breached'))
    assert response.status_code == 409 and response.json()['detail'] == 'Paper entry refused [DAILY_LOSS_LIMIT]: breached'
    assert conn.statements('INSERT INTO managed_paper_positions') == [] and conn.statements('INSERT INTO managed_paper_events') == []


def test_admission_runs_under_the_lock_after_the_pause_check_and_before_the_insert():
    response, order, _ = entry_attempt(None)
    assert response.status_code == 200, response.text
    lock = order.index('SELECT pg_advisory_xact_lock(230914)')
    paused = next(i for i, step in enumerate(order) if step.startswith('SELECT entries_paused'))
    admit = order.index(f'admit {SYMBOL} {LIFECYCLE_VERSION}')
    insert = next(i for i, step in enumerate(order) if step.startswith('INSERT INTO managed_paper_positions'))
    assert lock < paused < admit < insert
