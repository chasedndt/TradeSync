from decimal import Decimal

from tradesync_core.managed_paper import advance, open_position
from tradesync_core.paper_account_ledger import balances, expected_entries, money
from tradesync_core.paper_reconciliation import (
    account_mismatches,
    event_state,
    gaps,
    latest_state,
    position_mismatches,
)


def book(at=1000, bid=99.99, ask=100.01):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': 100}], 'asks': [{'price': ask, 'size': 100}]}


def lifecycle():
    opened = open_position('long', 'scalp', 1000, 1, book(), 1000)
    observed = advance(opened, book(at=1015, bid=100.2, ask=100.21), 1015)
    closed = advance(observed, book(at=1030, bid=100.3, ask=100.31), 1030, manual_close=True)
    return opened, observed, closed


def test_latest_state_follows_the_lifecycle_not_the_write_order():
    opened, observed, closed = lifecycle()
    assert latest_state([closed, opened, observed]) is closed
    assert latest_state([observed, opened]) is observed
    assert latest_state([]) is None
    assert event_state('opened', opened) is opened
    assert event_state('observed', {'position': observed, 'book': {}}) is observed
    assert event_state('funding', {'amount': 1}) is None


def test_stored_positions_must_equal_their_latest_event():
    opened, observed, closed = lifecycle()
    stored = [{'id': 'a', 'position_state': observed}, {'id': 'b', 'position_state': closed}]
    assert position_mismatches(stored, {'a': observed, 'b': closed}, ['a', 'b']) == []

    drifted = [{'id': 'a', 'position_state': {**observed, 'stop': 1.0}}]
    issue = position_mismatches(drifted, {'a': observed}, ['a'])[0]
    assert issue['code'] == 'POSITION_STATE_DIFFERS' and 'stop' in issue['detail']

    orphan = position_mismatches([{'id': 'c', 'position_state': opened}], {}, [])
    assert [i['code'] for i in orphan] == ['POSITION_WITHOUT_OPENED_EVENT', 'POSITION_WITHOUT_EVENTS']


def test_restart_with_open_position_flags_the_downtime_gap_without_filling_it():
    down_at, restart = 10_000.0, 10_600.0
    # At restart the position's last observation is from before the outage: an ongoing gap.
    ongoing = gaps([('a', 'BTC-PERP', down_at - 15, down_at)], [('a', 'BTC-PERP', down_at)], restart)
    assert ongoing == [{'position_id': 'a', 'symbol': 'BTC-PERP', 'started_at': down_at, 'ended_at': None, 'seconds': None, 'ongoing': True}]
    # After the first observation once monitoring resumed, the same gap has an end.
    ended = gaps([('a', 'BTC-PERP', down_at - 15, down_at), ('a', 'BTC-PERP', down_at, restart + 5)],
                 [('a', 'BTC-PERP', restart + 5)], restart + 10)
    assert ended == [{'position_id': 'a', 'symbol': 'BTC-PERP', 'started_at': down_at, 'ended_at': restart + 5,
                      'seconds': 605.0, 'ongoing': False}]


def test_ordinary_observation_spacing_is_not_a_gap():
    assert gaps([('a', 'ETH-PERP', 0.0, 45.0), ('a', 'ETH-PERP', 45.0, 60.0)], [('a', 'ETH-PERP', 60.0)], 100.0) == []


def ledger(entries):
    rows, running = [], Decimal(0)
    for sequence, entry in enumerate(entries, start=1):
        running += entry.amount_usdc
        rows.append({'sequence': sequence, 'kind': entry.kind, 'position_id': entry.position_id, 'occurred_at': entry.occurred_at,
                     'amount_usdc': entry.amount_usdc, 'gross_pnl_usdc': entry.gross_pnl_usdc, 'fees_usdc': entry.fees_usdc,
                     'funding_usdc': entry.funding_usdc, 'slippage_usdc': entry.slippage_usdc, 'balance_after_usdc': running})
    account = {'starting_capital_usdc': money(10_000), 'last_sequence': len(rows), 'peak_equity_usdc': money(10_000), **balances(entries)}
    return rows, account


def test_account_rebuilt_from_events_matches_or_names_the_difference():
    closed = lifecycle()[2]
    entries = expected_entries(10_000, 0.0, [('a', closed)])
    rows, account = ledger(entries)
    assert account_mismatches(account, rows, [('a', closed)], []) == []

    unbooked_rows, unbooked_account = ledger(entries[:1])
    assert [i['code'] for i in account_mismatches(unbooked_account, unbooked_rows, [('a', closed)], [])] == ['LEDGER_MISSING_ENTRY']

    unreadable = {k: v for k, v in closed.items() if k != 'gross_pnl_usdc'}
    assert [i['code'] for i in account_mismatches(account, rows, [('a', unreadable)], [])] == ['CLOSED_POSITION_UNREADABLE']

    assert [i['code'] for i in account_mismatches(account, rows, [('a', closed)], [10_250.5])] == ['PEAK_EQUITY_DIFFERS']
    assert account_mismatches({**account, 'peak_equity_usdc': money(10_250.5)}, rows, [('a', closed)], [10_100, 10_250.5]) == []
    assert account_mismatches(None, [], [], [])[0]['code'] == 'ACCOUNT_MISSING'
