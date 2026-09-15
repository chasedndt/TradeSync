import asyncio
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import paper_reconciliation_runner as runner
from paper_fakes import FakeConn, FakePool
from tradesync_core.managed_paper import advance, open_position
from tradesync_core.paper_account_ledger import balances, expected_entries, money


def book(at, bid=99.99, ask=100.01):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': 100}], 'asks': [{'price': ask, 'size': 100}]}


def restart_data(now):
    """One position still open from before a 10-minute outage, one closed and booked."""
    open_id, closed_id = uuid.uuid4(), uuid.uuid4()
    observed = advance(open_position('long', 'scalp', 1000, 1, book(1000), 1000), book(1015, bid=100.2, ask=100.21), 1015)
    closed = advance(open_position('short', 'scalp', 1000, 1, book(1000), 1000), book(1020, bid=99.9, ask=99.91), 1020, manual_close=True)
    entries = expected_entries(10_000, 0.0, [(closed_id, closed)])
    ledger, running = [], Decimal(0)
    for sequence, e in enumerate(entries, start=1):
        running += e.amount_usdc
        ledger.append({'sequence': sequence, 'kind': e.kind, 'position_id': e.position_id, 'occurred_at': e.occurred_at,
                       'amount_usdc': e.amount_usdc, 'gross_pnl_usdc': e.gross_pnl_usdc, 'fees_usdc': e.fees_usdc,
                       'funding_usdc': e.funding_usdc, 'slippage_usdc': e.slippage_usdc, 'balance_after_usdc': running})
    last_at = datetime.fromtimestamp(now - 600, timezone.utc)
    data = {
        'positions': [{'id': open_id, 'symbol': 'BTC-PERP', 'position_state': observed},
                      {'id': closed_id, 'symbol': 'ETH-PERP', 'position_state': closed}],
        'latest': {str(open_id): observed, str(closed_id): closed},
        'opened': {str(open_id), str(closed_id)},
        'account': {'starting_capital_usdc': money(10_000), 'last_sequence': len(ledger), 'peak_equity_usdc': money(10_000), **balances(entries)},
        'ledger': ledger, 'peaks': [], 'pairs': [],
        'last_seen': [{'id': open_id, 'symbol': 'BTC-PERP', 'last_at': last_at, 'last_s': last_at.timestamp()}],
    }
    return data, open_id, last_at


@pytest.fixture
def world(monkeypatch):
    ns = SimpleNamespace(upsert=AsyncMock(), lock=AsyncMock(), pause=AsyncMock(return_value=True))
    monkeypatch.setattr(runner.accounts, 'ensure_account', AsyncMock())
    monkeypatch.setattr(runner.store, 'upsert_gaps', ns.upsert)
    monkeypatch.setattr(runner.store, 'insert_run', AsyncMock(side_effect=lambda conn, run: run))
    monkeypatch.setattr(runner.store, 'prune_runs', AsyncMock())
    monkeypatch.setattr(runner.control, 'take_entry_lock', ns.lock)
    monkeypatch.setattr(runner.control, 'pause_automatically', ns.pause)
    return ns


def reconcile(monkeypatch, data, trigger='periodic'):
    monkeypatch.setattr(runner, 'collect', AsyncMock(return_value=data))
    return asyncio.run(runner.run_once(FakePool(FakeConn()), trigger))


def test_restart_with_an_open_position_reconciles_clean_and_flags_the_outage_gap(world, monkeypatch):
    data, open_id, last_at = restart_data(time.time())
    run = reconcile(monkeypatch, data, 'startup')
    assert (run['status'], run['trigger'], run['positions_checked'], run['open_positions'], run['mismatches']) == ('clean', 'startup', 2, 1, [])
    assert run['gaps'] == [{'position_id': str(open_id), 'symbol': 'BTC-PERP', 'started_at': last_at.isoformat(),
                            'ended_at': None, 'seconds': None, 'ongoing': True}]
    recorded = world.upsert.await_args.args[1][0]
    assert recorded['started_at'] is last_at and recorded['ended_at'] is None and recorded['position_id'] == open_id
    world.pause.assert_not_awaited()


def test_the_first_observation_after_restart_gives_the_gap_its_end(world, monkeypatch):
    now = time.time()
    data, open_id, last_at = restart_data(now)
    resumed = datetime.fromtimestamp(now - 5, timezone.utc)
    data['pairs'] = [{'position_id': open_id, 'symbol': 'BTC-PERP', 'prev_at': last_at, 'created_at': resumed,
                      'started_s': last_at.timestamp(), 'ended_s': resumed.timestamp()}]
    data['last_seen'] = [{'id': open_id, 'symbol': 'BTC-PERP', 'last_at': resumed, 'last_s': resumed.timestamp()}]
    run = reconcile(monkeypatch, data)
    assert [(g['started_at'], g['ended_at'], g['ongoing']) for g in run['gaps']] == [(last_at.isoformat(), resumed.isoformat(), False)]
    assert world.upsert.await_args.args[1][0]['ended_at'] is resumed


def test_any_mismatch_pauses_entries_with_the_reason(world, monkeypatch):
    data, _, _ = restart_data(time.time())
    first = data['positions'][0]
    data['positions'][0] = {**first, 'position_state': {**first['position_state'], 'stop': 1.0}}
    run = reconcile(monkeypatch, data)
    assert run['status'] == 'mismatch' and [m['code'] for m in run['mismatches']] == ['POSITION_STATE_DIFFERS']
    world.lock.assert_awaited_once()
    assert world.pause.await_args.args[1].startswith('Automatic pause [RECONCILIATION_MISMATCH]: 1 mismatch(es); first POSITION_STATE_DIFFERS')


def test_an_unbooked_close_is_reported_not_repaired(world, monkeypatch):
    data, _, _ = restart_data(time.time())
    data['ledger'] = data['ledger'][:1]
    data['account'] = {**data['account'], 'cash_usdc': money(10_000), 'realised_pnl_usdc': money(0), 'gross_pnl_usdc': money(0),
                       'fees_usdc': money(0), 'funding_usdc': money(0), 'slippage_usdc': money(0), 'closed_positions': 0, 'last_sequence': 1}
    run = reconcile(monkeypatch, data)
    assert [m['code'] for m in run['mismatches']] == ['LEDGER_MISSING_ENTRY']
    world.pause.assert_awaited_once()


def test_a_failed_run_is_recorded_without_pausing_or_writing_gaps(world, monkeypatch):
    monkeypatch.setattr(runner, 'collect', AsyncMock(side_effect=RuntimeError('database gone')))
    run = asyncio.run(runner.run_once(FakePool(FakeConn()), 'startup'))
    assert run['status'] == 'failed' and run['error'].startswith('RuntimeError')
    world.pause.assert_not_awaited()
    world.upsert.assert_not_awaited()
