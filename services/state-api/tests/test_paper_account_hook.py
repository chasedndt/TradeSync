import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import paper_account_store as accounts
from app import paper_risk_hooks as hooks
from app import paper_risk_signals
from app.main import app, state
from paper_fakes import FakeConn, pool_of
from tradesync_core.managed_paper import advance, open_position
from tradesync_core.paper_account_ledger import realised_entry


def book(at, bid=99.99, ask=100.01):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': 100}], 'asks': [{'price': ask, 'size': 100}]}


def closed_state():
    return advance(open_position('long', 'scalp', 1000, 1, book(1000), 1000), book(1010, bid=100.0), 1010, manual_close=True)


def test_only_a_closed_state_is_booked(monkeypatch):
    booked = AsyncMock()
    monkeypatch.setattr(hooks.paper_account_store, 'book_close_safely', booked)
    asyncio.run(hooks.record_position_event(object(), 'p', {'status': 'open'}))
    booked.assert_not_awaited()
    asyncio.run(hooks.record_position_event(object(), 'p', {'status': 'closed'}))
    booked.assert_awaited_once()


def test_a_failed_booking_never_undoes_the_close_and_asks_for_reconciliation(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(accounts, 'book_close', AsyncMock(side_effect=RuntimeError('ledger unavailable')))
    paper_risk_signals.take('reconcile')
    assert asyncio.run(accounts.book_close_safely(conn, 'p1', {'status': 'closed'})) is None
    assert conn.transactions == 1  # a savepoint inside the closing transaction
    assert 'RuntimeError' in accounts.booking_status['last_error']
    assert paper_risk_signals.take('reconcile') is True


def test_booking_appends_the_realised_entry_and_moves_cash_by_it():
    state_ = closed_state()
    identity = uuid.uuid4()
    entry = realised_entry(identity, state_)
    conn = FakeConn(fetchrow={'cash_usdc': Decimal('10000'), 'last_sequence': 1})
    conn.fetchval = AsyncMock(side_effect=[None, 2])  # not yet booked; the insert returns sequence 2
    conn.execute = AsyncMock(return_value='UPDATE 1')
    assert asyncio.run(accounts.book_close(conn, identity, state_)) == 2
    update_args = conn.execute.await_args.args
    assert update_args[1] == Decimal('10000') + entry.amount_usdc
    assert update_args[-2:] == (2, 1)


def test_booking_is_idempotent_and_refuses_a_moved_account():
    conn = FakeConn(fetchrow={'cash_usdc': Decimal('10000'), 'last_sequence': 1}, fetchval=1)
    assert asyncio.run(accounts.book_close(conn, uuid.uuid4(), closed_state())) is None
    conn.execute.assert_not_awaited()

    moved = FakeConn(fetchrow={'cash_usdc': Decimal('10000'), 'last_sequence': 1})
    moved.fetchval = AsyncMock(side_effect=[None, 2])
    moved.execute = AsyncMock(return_value='UPDATE 0')
    with pytest.raises(RuntimeError):
        asyncio.run(accounts.book_close(moved, uuid.uuid4(), closed_state()))


def test_starting_capital_setting_must_be_a_positive_number(monkeypatch):
    monkeypatch.setenv(accounts.STARTING_CAPITAL_ENV, '25000')
    assert accounts.configured_starting_capital() == Decimal('25000.00000000')
    for bad in ('0', '-5', 'ten thousand'):
        monkeypatch.setenv(accounts.STARTING_CAPITAL_ENV, bad)
        with pytest.raises(ValueError):
            accounts.configured_starting_capital()


# The close hook inside the real close route.

class Response:
    def raise_for_status(self):
        pass

    def json(self):
        return {}


class Client:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        return Response()


def test_closing_observation_hands_the_closed_state_to_the_account_hook():
    identity = uuid.uuid4()
    opened = json.dumps({'status': 'open'})
    closed = {'status': 'closed', 'exit_reason': 'operator_close'}
    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=[{'symbol': 'BTC-PERP', 'position_state': opened}, {'position_state': opened}])
    conn.execute = AsyncMock(return_value='OK')

    @asynccontextmanager
    async def transaction():
        yield

    conn.transaction = transaction
    hook = AsyncMock()
    with patch.object(state, 'pool', pool_of(conn)), patch('app.managed_paper.httpx.AsyncClient', Client), \
            patch('app.managed_paper.advance', return_value=closed), patch('app.managed_paper.record_position_event', hook):
        response = TestClient(app).post(f'/state/paper-positions/{identity}/close')
    assert response.status_code == 200, response.text
    hook.assert_awaited_once()
    assert hook.await_args.args[1:] == (identity, closed)
