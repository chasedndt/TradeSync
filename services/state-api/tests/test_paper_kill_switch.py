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
from tradesync_core.managed_paper import open_position

REASON = 'Stop all paper risk for review'


def book(at, bid=99.99, ask=100.01):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': 100}], 'asks': [{'price': ask, 'size': 100}]}


def fresh():
    return AsyncMock(side_effect=lambda symbol: book(time.time()))


class Table:
    """managed_paper_positions and managed_paper_events, for the statements a kill close issues."""

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
        assert 'FOR UPDATE' in sql
        return self.rows.get(pid)

    async def fetchval(self, sql, *args):
        return sum(1 for pid in self.rows if self.state(pid)['status'] == 'open')

    async def execute(self, sql, *args):
        if sql.startswith('UPDATE managed_paper_positions'):
            self.rows[args[0]]['position_state'] = args[1]
        elif sql.startswith('INSERT INTO managed_paper_events'):
            self.events.append({'position_id': args[1], **json.loads(args[2])})
        return 'OK'


@pytest.fixture
def world(monkeypatch):
    opened_at = time.time() - 20
    table = Table([(uuid.uuid4(), symbol, open_position('long', 'scalp', 1000, 1, book(opened_at), opened_at))
                   for symbol in ('BTC-PERP', 'ETH-PERP', 'SOL-PERP')])
    ns = SimpleNamespace(table=table, kill_event=AsyncMock(), set_pause=AsyncMock(), booked=AsyncMock(),
                         switch={'active': False, 'operator': 'migration 031', 'reason': 'Kill switch installed and not engaged', 'changed_at': None},
                         pause={'entries_paused': False, 'reason': 'Resumed after review', 'updated_at': None})

    def set_kill(conn, *, active, operator, reason):
        ns.switch.update(active=active, operator=operator, reason=reason)
        return dict(ns.switch)

    def open_rows(conn):
        return [{'id': pid, 'symbol': row['symbol'], 'position_state': table.state(pid)}
                for pid, row in table.rows.items() if table.state(pid)['status'] == 'open']

    monkeypatch.setattr(kill.control, 'take_entry_lock', AsyncMock())
    monkeypatch.setattr(kill.control, 'kill_state', AsyncMock(side_effect=lambda conn, lock=False: dict(ns.switch)))
    monkeypatch.setattr(kill.control, 'set_kill', AsyncMock(side_effect=set_kill))
    monkeypatch.setattr(kill.control, 'kill_event', ns.kill_event)
    monkeypatch.setattr(kill.control, 'pause_state', AsyncMock(side_effect=lambda conn, lock=False: ns.pause))
    monkeypatch.setattr(kill.control, 'set_pause', ns.set_pause)
    monkeypatch.setattr(kill.accounts, 'open_positions', AsyncMock(side_effect=open_rows))
    monkeypatch.setattr(kill.accounts, 'book_close_safely', ns.booked)
    return ns


def test_kill_pauses_entries_and_closes_every_open_position_with_its_reason(world):
    fetch = fresh()
    result = asyncio.run(kill.engage(world.table, fetch, operator='chase', reason=REASON))
    assert result['already_engaged'] is False and world.switch['active'] is True
    assert [c['exit_reason'] for c in result['closed']] == ['kill_switch'] * 3 and result['pending'] == []
    assert all(world.table.state(pid)['status'] == 'closed' for pid in world.table.rows)
    assert [e['position']['exit_reason'] for e in world.table.events] == ['kill_switch'] * 3
    assert world.table.events[0]['kill_switch'] == {'operator': 'chase', 'reason': REASON}
    assert [c.kwargs['action'] for c in world.kill_event.await_args_list] == ['kill', 'close', 'close', 'close']
    assert world.set_pause.await_args.kwargs == {'paused': True, 'operator': 'chase', 'reason': f'Kill switch engaged: {REASON}'}
    assert world.booked.await_count == 3 and fetch.await_count == 3


def test_a_position_without_a_fresh_quote_stays_open_and_is_reported_pending(world):
    stale = AsyncMock(side_effect=lambda symbol: book(time.time() - 100))
    result = asyncio.run(kill.engage(world.table, stale, operator='chase', reason=REASON))
    assert result['closed'] == []
    assert [p['reason'] for p in result['pending']] == ['Quote stale or future-dated'] * 3
    assert all(world.table.state(pid)['status'] == 'open' for pid in world.table.rows)
    assert world.table.events == [] and world.booked.await_count == 0
    assert world.switch['active'] is True


def test_market_data_failure_leaves_closes_pending_for_the_next_tick(world):
    down = AsyncMock(side_effect=ConnectionError('market-data down'))
    result = asyncio.run(kill.close_open_positions(world.table, down, operator='chase', reason=REASON))
    assert [p['reason'] for p in result['pending']] == ['ConnectionError'] * 3


def test_a_repeated_kill_keeps_the_original_operator_and_reason(world):
    world.switch.update(active=True, operator='chase', reason='First stop of the day')
    result = asyncio.run(kill.engage(world.table, fresh(), operator='someone else', reason='Second stop request'))
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
    asyncio.run(kill.engage(world.table, fresh(), operator='chase', reason=REASON))
    world.pause = {'entries_paused': True, 'reason': f'Kill switch engaged: {REASON}', 'updated_at': None}
    world.set_pause.reset_mock()
    result = asyncio.run(kill.resume(world.table, operator='chase', reason='Reviewed; clear the kill switch'))
    assert world.switch['active'] is False and result['entries_paused'] is True
    world.set_pause.assert_not_awaited()
    assert world.kill_event.await_args.kwargs['action'] == 'resume'
