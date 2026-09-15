import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app import paper_kill_switch as kill
from app.paper_market import Market
from tradesync_core import paper_funding as funding
from tradesync_core.managed_paper import open_position

REASON = 'Stop all paper risk for review'
H = 3600


def book(at, bid=99.99, ask=100.01, size=100):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': size}], 'asks': [{'price': ask, 'size': size}]}


def market(*, age_s=0.0, size=100):
    return Market(book=AsyncMock(side_effect=lambda symbol: book(time.time() - age_s, size=size)),
                  funding=AsyncMock(side_effect=lambda symbol, hours: ({}, time.time())))


class Table:
    """managed_paper_positions and managed_paper_events, for the statements a kill-switch close issues."""

    def __init__(self, positions):
        self.rows = {pid: {'symbol': symbol, 'position_state': json.dumps(state)} for pid, symbol, state in positions}
        self.events = []

    def state(self, pid):
        return json.loads(self.rows[pid]['position_state'])

    def acquire(self):
        @asynccontextmanager
        async def acquired():
            yield self
        return acquired()

    def transaction(self, **kwargs):
        @asynccontextmanager
        async def tx():
            yield
        return tx()

    async def fetchrow(self, sql, pid):
        assert sql.startswith('SELECT symbol, position_state') or 'FOR UPDATE' in sql
        return self.rows.get(pid)

    async def fetchval(self, sql, *args):
        return sum(1 for pid in self.rows if self.state(pid)['status'] == 'open')

    async def execute(self, sql, *args):
        if sql.startswith('UPDATE managed_paper_positions'):
            self.rows[args[0]]['position_state'] = args[1]
        elif sql.startswith('INSERT INTO managed_paper_events'):
            self.events.append({'position_id': args[1], 'kind': args[2], **json.loads(args[3])})
        return 'OK'


@pytest.fixture
def world(monkeypatch):
    opened_at = time.time() - 2 * H  # hourly settlements have passed since entry
    table = Table([(uuid.uuid4(), symbol, open_position('long', 'scalp', 1000, 1, book(opened_at), opened_at))
                   for symbol in ('BTC-PERP', 'ETH-PERP', 'SOL-PERP')])
    ns = SimpleNamespace(table=table, kill_event=AsyncMock(), set_pause=AsyncMock(), hook=AsyncMock(),
                         switch={'active': False, 'operator': 'migration 031', 'reason': 'Kill switch installed and not engaged', 'changed_at': None},
                         pause={'entries_paused': False, 'reason': 'Resumed after review', 'updated_at': None})

    def settle(conn, pid, symbol, state, rates, received, now):
        rows = [funding.settle(state['side'], state['quantity'], hour, {'funding_rate': 1e-4}, {'value': 100.0, 'source': 'test'})
                for hour in funding.settlement_hours(state['entry_time'], now)]
        return len(rows), rows

    def set_kill(conn, *, active, operator, reason):
        ns.switch.update(active=active, operator=operator, reason=reason)
        return dict(ns.switch)

    def open_rows(conn):
        return [{'id': pid, 'symbol': row['symbol'], 'position_state': table.state(pid)}
                for pid, row in table.rows.items() if table.state(pid)['status'] == 'open']

    ns.settle = AsyncMock(side_effect=settle)
    monkeypatch.setattr(kill.control, 'take_entry_lock', AsyncMock())
    monkeypatch.setattr(kill.control, 'kill_state', AsyncMock(side_effect=lambda conn, lock=False: dict(ns.switch)))
    monkeypatch.setattr(kill.control, 'set_kill', AsyncMock(side_effect=set_kill))
    monkeypatch.setattr(kill.control, 'kill_event', ns.kill_event)
    monkeypatch.setattr(kill.control, 'pause_state', AsyncMock(side_effect=lambda conn, lock=False: ns.pause))
    monkeypatch.setattr(kill.control, 'set_pause', ns.set_pause)
    monkeypatch.setattr(kill.accounts, 'open_positions', AsyncMock(side_effect=open_rows))
    monkeypatch.setattr(kill.funding_store, 'outstanding', AsyncMock(return_value=[1]))
    monkeypatch.setattr(kill.funding_store, 'settle_rows', ns.settle)
    monkeypatch.setattr(kill.hooks, 'record_position_event', ns.hook)
    return ns


def test_kill_pauses_entries_and_closes_every_open_position_through_the_managed_close(world):
    shop = market()
    result = asyncio.run(kill.engage(world.table, shop, operator='chase', reason=REASON))
    assert result['already_engaged'] is False and world.switch['active'] is True
    assert [c['exit_reason'] for c in result['closed']] == ['kill_switch'] * 3 and result['pending'] == []
    for pid in world.table.rows:
        state = world.table.state(pid)
        assert state['status'] == 'closed' and state['exit']['rule'] == 'kill_switch'
        assert state['slippage']['exit']['basis'] == 'book_walk' and state['fees']['exit_usdc'] > 0
        expected_hours = len(funding.settlement_hours(state['entry_time'], state['exit_time']))
        assert expected_hours >= 2 and state['funding']['status'] == 'complete' and state['funding']['settled_hours'] == expected_hours
        assert state['net_estimate_usdc'] == pytest.approx(state['gross_pnl_usdc'] - state['fees_usdc'] - state['funding_usdc'])
    assert [e['kind'] for e in world.table.events] == ['closed'] * 3
    assert world.table.events[0]['kill_switch'] == {'operator': 'chase', 'reason': REASON}
    assert [c.kwargs['action'] for c in world.kill_event.await_args_list] == ['kill', 'close', 'close', 'close']
    assert world.set_pause.await_args.kwargs == {'paused': True, 'operator': 'chase', 'reason': f'Kill switch engaged: {REASON}'}
    assert world.hook.await_count == 3 and all(call.args[2]['status'] == 'closed' for call in world.hook.await_args_list)
    assert shop.book.await_count == shop.funding.await_count == world.settle.await_count == 3


def test_a_position_without_a_fresh_book_stays_open_and_nothing_is_written(world):
    result = asyncio.run(kill.engage(world.table, market(age_s=100), operator='chase', reason=REASON))
    assert result['closed'] == [] and [p['reason'] for p in result['pending']] == ['Quote stale or future-dated'] * 3
    assert all(world.table.state(pid)['status'] == 'open' for pid in world.table.rows)
    assert world.table.events == [] and world.hook.await_count == 0 and world.switch['active'] is True


def test_a_book_too_thin_for_the_quantity_leaves_the_kill_switch_exit_owed(world):
    result = asyncio.run(kill.close_open_positions(world.table, market(size=1), operator='chase', reason=REASON))
    assert result['closed'] == []
    assert all(p['reason'].startswith('Kill-switch exit owed: displayed depth') for p in result['pending']) and len(result['pending']) == 3
    for pid in world.table.rows:
        state = world.table.state(pid)
        assert state['status'] == 'open' and state['pending_exit']['rule'] == 'kill_switch'
    assert [e['kind'] for e in world.table.events] == ['observed'] * 3 and world.hook.await_count == 0


def test_market_data_failure_leaves_closes_pending_for_the_next_tick(world):
    down = Market(book=AsyncMock(side_effect=ConnectionError('market-data down')), funding=AsyncMock(return_value=({}, 0.0)))
    result = asyncio.run(kill.close_open_positions(world.table, down, operator='chase', reason=REASON))
    assert [p['reason'] for p in result['pending']] == ['ConnectionError'] * 3


def test_unpublished_funding_never_holds_up_the_close(world):
    shop = Market(book=AsyncMock(side_effect=lambda symbol: book(time.time())), funding=AsyncMock(side_effect=ConnectionError('funding down')))
    result = asyncio.run(kill.close_open_positions(world.table, shop, operator='chase', reason=REASON))
    assert len(result['closed']) == 3 and world.settle.await_args.args[4] == {}


def test_a_repeated_kill_keeps_the_original_operator_and_reason(world):
    world.switch.update(active=True, operator='chase', reason='First stop of the day')
    result = asyncio.run(kill.engage(world.table, market(), operator='someone else', reason='Second stop request'))
    assert result['already_engaged'] is True
    assert world.table.events[0]['kill_switch'] == {'operator': 'chase', 'reason': 'First stop of the day'}
    assert 'kill' not in [c.kwargs['action'] for c in world.kill_event.await_args_list]


def test_resume_is_refused_when_not_engaged_or_while_positions_remain_open(world):
    with pytest.raises(HTTPException) as caught:
        asyncio.run(kill.resume(world.table, operator='chase', reason='Resume after review'))
    assert caught.value.status_code == 409 and 'not engaged' in caught.value.detail
    world.switch['active'] = True
    with pytest.raises(HTTPException) as caught:
        asyncio.run(kill.resume(world.table, operator='chase', reason='Resume after review'))
    assert caught.value.status_code == 409 and '3 paper position(s) still open' in caught.value.detail


def test_resume_after_every_close_clears_the_kill_but_leaves_entries_paused(world):
    asyncio.run(kill.engage(world.table, market(), operator='chase', reason=REASON))
    world.pause = {'entries_paused': True, 'reason': f'Kill switch engaged: {REASON}', 'updated_at': None}
    world.set_pause.reset_mock()
    result = asyncio.run(kill.resume(world.table, operator='chase', reason='Reviewed; clear the kill switch'))
    assert world.switch['active'] is False and result['entries_paused'] is True
    world.set_pause.assert_not_awaited()
    assert world.kill_event.await_args.kwargs['action'] == 'resume'
