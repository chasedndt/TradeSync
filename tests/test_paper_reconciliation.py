from decimal import Decimal

from tradesync_core import paper_funding as funding
from tradesync_core.managed_paper import advance, open_position, settle_funding
from tradesync_core.paper_account_ledger import balances, expected_entries, money
from tradesync_core.paper_lifecycle_rules import COMMON
from tradesync_core.paper_reconciliation import (
    GAP_THRESHOLD_S,
    account_mismatches,
    event_state,
    gaps,
    latest_state,
    position_mismatches,
)

H = 3600
ENTRY = 10 * H + 600


def book(at, bid=99.99, ask=100.01):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': 100}], 'asks': [{'price': ask, 'size': 100}]}


def lifecycle(close_at=ENTRY + 30):
    opened = open_position('long', 'scalp', 1000, 1, book(ENTRY), ENTRY)
    observed = advance(opened, book(ENTRY + 15, bid=100.2, ask=100.22), ENTRY + 15)
    closed = advance(observed, book(close_at, bid=100.3, ask=100.32), close_at, manual_close=True, funding_rows=[])
    return opened, observed, closed


def settled_later(closed):
    row = funding.settle(closed['side'], closed['quantity'], 11 * H, {'funding_rate': 1e-4}, {'value': 100.0, 'source': 'test'})
    return settle_funding(closed, [row])


def codes(issues):
    return [i['code'] for i in issues]


def test_gap_threshold_is_the_lifecycle_latch():
    assert GAP_THRESHOLD_S == COMMON.observation_gap_s


def test_latest_state_follows_the_lifecycle_through_late_funding_not_the_write_order():
    opened, observed, closed = lifecycle(close_at=11 * H + 300)
    settled = settled_later(closed)
    assert closed['funding']['status'] == 'awaiting_rows' and settled['funding']['settled_hours'] == 1
    assert latest_state([settled, closed, opened, observed]) is settled
    assert latest_state([closed, settled]) is settled
    assert latest_state([observed, opened]) is observed
    assert latest_state([]) is None
    assert event_state('opened', opened) is opened
    assert event_state('funding_settled', {'position': settled, 'book': None}) is settled
    assert event_state('funding', {'amount': 1}) is None


def test_stored_positions_must_equal_their_latest_event():
    opened, observed, closed = lifecycle()
    stored = [{'id': 'a', 'position_state': observed}, {'id': 'b', 'position_state': closed}]
    assert position_mismatches(stored, {'a': observed, 'b': closed}, ['a', 'b']) == []

    drifted = [{'id': 'a', 'position_state': {**observed, 'stop': 1.0}}]
    issue = position_mismatches(drifted, {'a': observed}, ['a'])[0]
    assert issue['code'] == 'POSITION_STATE_DIFFERS' and 'stop' in issue['detail']

    orphan = position_mismatches([{'id': 'c', 'position_state': opened}], {}, [])
    assert codes(orphan) == ['POSITION_WITHOUT_OPENED_EVENT', 'POSITION_WITHOUT_EVENTS']


def test_restart_with_open_position_flags_the_downtime_gap_without_filling_it():
    down_at, restart = 10_000.0, 10_600.0
    ongoing = gaps([('a', 'BTC-PERP', down_at - 15, down_at)], [('a', 'BTC-PERP', down_at)], restart)
    assert ongoing == [{'position_id': 'a', 'symbol': 'BTC-PERP', 'started_at': down_at, 'ended_at': None, 'seconds': None, 'ongoing': True}]
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


def test_account_rebuilt_from_the_close_and_later_funding_events_matches_or_names_the_difference():
    at_close = lifecycle(close_at=11 * H + 300)[2]
    latest = settled_later(at_close)
    closed = [('a', at_close, latest)]
    entries = expected_entries(10_000, 0.0, closed)
    rows, account = ledger(entries)
    assert account_mismatches(account, rows, closed, []) == []

    unadjusted_rows, unadjusted_account = ledger([e for e in entries if e.kind != 'funding_adjustment'])
    assert codes(account_mismatches(unadjusted_account, unadjusted_rows, closed, [])) == ['LEDGER_FUNDING_ADJUSTMENT_DIFFERS']

    unbooked_rows, unbooked_account = ledger(entries[:1])
    assert codes(account_mismatches(unbooked_account, unbooked_rows, closed, [])) == ['LEDGER_MISSING_ENTRY', 'LEDGER_FUNDING_ADJUSTMENT_DIFFERS']

    unreadable = {k: v for k, v in at_close.items() if k != 'gross_pnl_usdc'}
    assert codes(account_mismatches(account, rows, [('a', unreadable, latest)], [])) == ['CLOSED_POSITION_UNREADABLE']
    assert codes(account_mismatches(account, rows, [('a', None, latest)], [])) == ['CLOSED_POSITION_WITHOUT_CLOSE_EVENT']

    assert codes(account_mismatches(account, rows, closed, [10_250.5])) == ['PEAK_EQUITY_DIFFERS']
    assert account_mismatches({**account, 'peak_equity_usdc': money(10_250.5)}, rows, closed, [10_100, 10_250.5]) == []
    assert codes(account_mismatches(None, [], [], [])) == ['ACCOUNT_MISSING']
