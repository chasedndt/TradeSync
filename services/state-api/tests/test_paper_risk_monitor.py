import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import paper_risk_monitor as monitor
from paper_fakes import FakeConn, FakePool
from tradesync_core.paper_account import snapshot

NOW = 1_800_000_000.0
LIMITS = dict(daily_loss_limit_usdc=200.0, max_drawdown_fraction=0.06, max_gross_exposure_fraction=0.35,
              max_symbol_exposure_fraction=0.12, max_bucket_exposure_fraction=0.25, correlation_threshold=0.7,
              max_concurrent_positions=3, max_entry_quote_age_s=15.0, max_mark_age_s=60.0)


def account(cash=10_000.0, realised_today=0.0):
    return snapshot(now_s=NOW, starting_capital=10_000, cash=cash, stored_peak=10_000, marks=(),
                    realised_today=realised_today, unrealised_at_day_start=0)


@pytest.fixture
def world(monkeypatch):
    ns = SimpleNamespace(kill={'active': False, 'operator': 'migration 031', 'reason': 'Kill switch installed and not engaged'},
                         snap=account(), pause=AsyncMock(return_value=True), peak=AsyncMock(return_value=False),
                         close=AsyncMock(return_value={'closed': [], 'pending': []}), update=AsyncMock(), lock=AsyncMock())
    monkeypatch.setattr(monitor.control, 'kill_state', AsyncMock(side_effect=lambda conn, lock=False: ns.kill))
    monkeypatch.setattr(monitor.accounts, 'load_account', AsyncMock(return_value={'singleton': True}))
    monkeypatch.setattr(monitor.view, 'account_snapshot', AsyncMock(side_effect=lambda conn, now_s, lock=None: ns.snap))
    monkeypatch.setattr(monitor.accounts, 'record_peak', ns.peak)
    monkeypatch.setattr(monitor.limit_store, 'load', AsyncMock(return_value=dict(LIMITS)))
    monkeypatch.setattr(monitor.limit_store, 'update', ns.update)
    monkeypatch.setattr(monitor.control, 'take_entry_lock', ns.lock)
    monkeypatch.setattr(monitor.control, 'pause_automatically', ns.pause)
    monkeypatch.setattr(monitor.paper_kill_switch, 'close_open_positions', ns.close)
    return ns


def tick():
    asyncio.run(monitor.tick(FakePool(FakeConn()), AsyncMock(), now_s=NOW))


def test_daily_loss_breach_switches_the_pause_on_with_its_reason_and_figures(world):
    world.snap = account(cash=9_750, realised_today=-250)
    tick()
    world.lock.assert_awaited_once()
    reason = world.pause.await_args.args[1]
    assert reason.startswith('Automatic pause [DAILY_LOSS_LIMIT]') and '-250.00 USDC' in reason
    assert monitor.status['breaches'][0]['code'] == 'DAILY_LOSS_LIMIT'
    assert monitor.status['last_automatic_pause']['code'] == 'DAILY_LOSS_LIMIT'
    world.update.assert_not_awaited()


def test_drawdown_breach_switches_the_pause_on(world):
    world.snap = account(cash=9_300)
    tick()
    assert world.pause.await_args.args[1].startswith('Automatic pause [DRAWDOWN_LIMIT]')
    world.update.assert_not_awaited()


def test_no_breach_leaves_the_pause_and_the_limits_alone(world):
    tick()
    world.pause.assert_not_awaited()
    world.lock.assert_not_awaited()
    world.update.assert_not_awaited()
    assert monitor.status['breaches'] == [] and monitor.status['last_error'] is None


def test_engaged_kill_switch_keeps_closing_with_its_operator_and_reason(world):
    world.kill = {'active': True, 'operator': 'chase', 'reason': 'Stop all paper risk'}
    world.close.return_value = {'closed': [], 'pending': [{'position_id': 'p', 'symbol': 'BTC-PERP', 'reason': 'Quote stale or future-dated'}]}
    tick()
    assert world.close.await_args.kwargs == {'operator': 'chase', 'reason': 'Stop all paper risk'}
    assert monitor.status['kill_pending'][0]['symbol'] == 'BTC-PERP'


def test_a_new_equity_high_is_recorded(world):
    world.peak.return_value = True
    tick()
    assert monitor.status['last_peak_at'] == NOW
