import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app import paper_account_store as accounts
from app import paper_risk_hooks as hooks
from app import paper_risk_signals
from paper_fakes import H, FakeMarket, market_routes
from paper_fakes import FakeConn as PositionsConn
from paper_risk_fakes import FakeConn
from test_paper_positions_routes import build, held_position, position_handlers
from tradesync_core import paper_funding as funding
from tradesync_core.managed_paper import advance, open_position, settle_funding
from tradesync_core.paper_account_ledger import money, realised_entry

ENTRY = 10 * H + 600


def book(at, bid=99.99, ask=100.01):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': 100}], 'asks': [{'price': ask, 'size': 100}]}


def settlement(position, hour):
    return funding.settle(position['side'], position['quantity'], hour, {'funding_rate': 1e-4}, {'value': 100.0, 'source': 'test'})


def closed_state(hours=(11 * H, 12 * H)):
    opened = open_position('long', 'scalp', 1000, 1, book(ENTRY), ENTRY)
    at = 12 * H + 300
    return advance(opened, book(at, bid=100.0, ask=100.02), at, manual_close=True, funding_rows=[settlement(opened, h) for h in hours])


def late(at_close):
    return settle_funding(at_close, [settlement(at_close, 11 * H), settlement(at_close, 12 * H)])


class LedgerConn:
    """The statements ``book_position`` issues, over one account row, its ledger and a position's closed event."""

    def __init__(self, close_state=None, *, moved=False):
        self.close_state, self.moved = close_state, moved
        self.account = {'cash_usdc': Decimal('10000'), 'last_sequence': 1, 'realised_pnl_usdc': Decimal(0),
                        'funding_usdc': Decimal(0), 'closed_positions': 0}
        self.rows = []

    def transaction(self, **kwargs):
        @asynccontextmanager
        async def tx():
            yield
        return tx()

    async def fetchrow(self, sql, *args):
        assert sql.startswith('SELECT * FROM paper_account WHERE singleton')
        return dict(self.account)

    async def fetch(self, sql, *args):
        assert sql == accounts.POSITION_ENTRIES_SQL
        return [{'kind': r['kind'], 'funding_usdc': r['funding_usdc']} for r in self.rows if r['position_id'] == args[0]]

    async def fetchval(self, sql, *args):
        if sql == accounts.CLOSE_STATE_SQL:
            return None if self.close_state is None else json.dumps(self.close_state)
        assert sql == accounts.INSERT_ENTRY_SQL
        self.rows.append({'kind': args[1], 'position_id': args[2], 'amount_usdc': args[4], 'funding_usdc': args[7]})
        return self.account['last_sequence'] + 1

    async def execute(self, sql, *args):
        assert sql == accounts.UPDATE_BALANCES_SQL
        if self.moved or args[8] != self.account['last_sequence']:
            return 'UPDATE 0'
        self.account.update(cash_usdc=args[0], last_sequence=args[7], realised_pnl_usdc=self.account['realised_pnl_usdc'] + args[1],
                            funding_usdc=self.account['funding_usdc'] + args[4], closed_positions=self.account['closed_positions'] + args[6])
        return 'UPDATE 1'


def test_only_a_closed_state_is_booked(monkeypatch):
    booked = AsyncMock()
    monkeypatch.setattr(hooks.paper_account_store, 'book_position_safely', booked)
    asyncio.run(hooks.record_position_event(object(), 'p', {'status': 'open'}))
    booked.assert_not_awaited()
    asyncio.run(hooks.record_position_event(object(), 'p', {'status': 'closed'}))
    booked.assert_awaited_once()


def test_a_failed_booking_never_undoes_the_close_and_asks_for_reconciliation(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(accounts, 'book_position', AsyncMock(side_effect=RuntimeError('ledger unavailable')))
    paper_risk_signals.take('reconcile')
    assert asyncio.run(accounts.book_position_safely(conn, 'p1', {'status': 'closed'})) == []
    assert conn.transactions == 1  # a savepoint inside the transaction that stores the state
    assert 'RuntimeError' in accounts.booking_status['last_error']
    assert paper_risk_signals.take('reconcile') is True


def test_a_close_is_booked_once_then_late_funding_moves_cash_by_exactly_the_change():
    at_close = closed_state(hours=(11 * H,))
    identity = uuid.uuid4()
    conn = LedgerConn(at_close)
    entry = realised_entry(identity, at_close)
    assert len(asyncio.run(accounts.book_position(conn, identity, at_close))) == 1
    assert conn.account['cash_usdc'] == Decimal('10000') + entry.amount_usdc and conn.account['closed_positions'] == 1
    assert asyncio.run(accounts.book_position(conn, identity, at_close)) == []

    settled = late(at_close)
    cash, charged, realised = conn.account['cash_usdc'], conn.account['funding_usdc'], conn.account['realised_pnl_usdc']
    assert len(asyncio.run(accounts.book_position(conn, identity, settled))) == 1
    change = money(settled['funding_usdc']) - money(at_close['funding_usdc'])
    assert change != 0 and [row['kind'] for row in conn.rows] == ['realised', 'funding_adjustment']
    assert conn.account['cash_usdc'] - cash == -change and conn.account['funding_usdc'] - charged == change
    assert conn.account['realised_pnl_usdc'] - realised == -change and conn.account['closed_positions'] == 1
    assert asyncio.run(accounts.book_position(conn, identity, settled)) == []


def test_a_close_booked_after_late_funding_still_takes_its_result_from_the_closed_event():
    at_close = closed_state(hours=(11 * H,))
    settled = late(at_close)
    conn = LedgerConn(at_close)
    asyncio.run(accounts.book_position(conn, uuid.uuid4(), settled))
    realised, adjustment = conn.rows
    assert realised['funding_usdc'] == money(at_close['funding_usdc'])
    assert adjustment['funding_usdc'] == money(settled['funding_usdc']) - money(at_close['funding_usdc'])


def test_open_states_book_nothing_and_a_moved_account_is_refused():
    assert asyncio.run(accounts.book_position(LedgerConn(), uuid.uuid4(), {'status': 'open'})) == []
    state = closed_state()
    with pytest.raises(RuntimeError):
        asyncio.run(accounts.book_position(LedgerConn(state, moved=True), uuid.uuid4(), state))


def test_starting_capital_setting_must_be_a_positive_number(monkeypatch):
    monkeypatch.setenv(accounts.STARTING_CAPITAL_ENV, '25000')
    assert accounts.configured_starting_capital() == Decimal('25000.00000000')
    for bad in ('0', '-5', 'ten thousand'):
        monkeypatch.setenv(accounts.STARTING_CAPITAL_ENV, bad)
        with pytest.raises(ValueError):
            accounts.configured_starting_capital()


# The hook inside the real observer (managed_paper.update).

@pytest.fixture
def market():
    FakeMarket.routes, FakeMarket.requested = market_routes(), []
    with patch('httpx.AsyncClient', FakeMarket):
        yield FakeMarket


def observe(state, *, manual=False):
    identity = uuid.uuid4()
    conn = PositionsConn(position_handlers(state))
    _, handles = build(conn)
    hook = AsyncMock()
    with patch('app.managed_paper.record_position_event', hook):
        result = asyncio.run(handles.update(identity, manual=manual))
    return result, hook, conn, identity


def test_the_observer_hands_an_operator_close_to_the_account_hook(market):
    result, hook, conn, identity = observe(held_position(time.time()), manual=True)
    assert result['status'] == 'closed' and result['exit_reason'] == 'operator_close'
    hook.assert_awaited_once_with(conn, identity, result)


def test_the_observer_hands_funding_settled_after_a_close_to_the_account_hook(market):
    result, hook, conn, identity = observe(held_position(time.time(), closed_after_s=H))
    assert result['funding']['status'] == 'complete'
    assert [args[2] for args in conn.statements('INSERT INTO managed_paper_events')] == ['funding_settled']
    hook.assert_awaited_once_with(conn, identity, result)


def test_an_observation_of_an_open_position_books_nothing(market):
    result, hook, _, _ = observe(held_position(time.time()))
    assert result['status'] == 'open'
    hook.assert_not_awaited()
