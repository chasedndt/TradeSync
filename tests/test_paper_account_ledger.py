from decimal import Decimal

import pytest

from tradesync_core.managed_paper import advance, open_position
from tradesync_core.paper_account_ledger import (
    balances,
    capital_entry,
    compare,
    expected_entries,
    money,
    realised_entry,
)


def book(at=1000, bid=99.99, ask=100.01):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': 100}], 'asks': [{'price': ask, 'size': 100}]}


def closed(side='long', at=1010, bid=100.0, ask=100.01):
    opened = open_position(side, 'scalp', 1000, 1, book(), 1000)
    return advance(opened, book(at=at, bid=bid, ask=ask), at, manual_close=True)


def stored(entries):
    rows, running = [], Decimal(0)
    for sequence, entry in enumerate(entries, start=1):
        running += entry.amount_usdc
        rows.append({'sequence': sequence, 'kind': entry.kind, 'position_id': entry.position_id,
                     'occurred_at': entry.occurred_at, 'amount_usdc': entry.amount_usdc,
                     'gross_pnl_usdc': entry.gross_pnl_usdc, 'fees_usdc': entry.fees_usdc,
                     'funding_usdc': entry.funding_usdc, 'slippage_usdc': entry.slippage_usdc,
                     'balance_after_usdc': running})
    account = {'starting_capital_usdc': money(10_000), 'last_sequence': rows[-1]['sequence'], **balances(entries)}
    return rows, account


def test_money_is_quantised_and_refuses_non_numbers():
    assert money(0.1 + 0.2) == Decimal('0.30000000')
    assert money(-1.234567894) == Decimal('-1.23456789')
    for bad in (float('nan'), float('inf'), True, None, 'nan'):
        with pytest.raises((ValueError, ArithmeticError)):
            money(bad)


def test_realised_entry_nets_fees_and_funding_and_reports_slippage_once():
    state = closed()
    entry = realised_entry('p1', state)
    assert entry.amount_usdc == entry.gross_pnl_usdc - entry.fees_usdc - entry.funding_usdc
    assert entry.gross_pnl_usdc == money(state['gross_pnl_usdc'])
    # Slippage sits inside both fill prices: 2 bps adverse at entry and at exit.
    expected = state['quantity'] * ((state['entry_price'] - 100.01) + (100.0 - state['exit_price']))
    assert float(entry.slippage_usdc) == pytest.approx(expected, rel=1e-6)
    assert entry.detail['funding_source'] == 'scenario'
    assert entry.occurred_at == state['exit_time']


def test_settled_funding_wins_over_the_scenario():
    state = {**closed(), 'funding_settled_usdc': 0.5}
    entry = realised_entry('p1', state)
    assert entry.funding_usdc == Decimal('0.50000000')
    assert entry.detail['funding_source'] == 'settled'


def test_open_position_has_no_realised_result():
    with pytest.raises(ValueError):
        realised_entry('p1', open_position('long', 'scalp', 1000, 1, book(), 1000))


def test_ledger_recomputed_from_closing_events_equals_stored_balances():
    positions = [('a', closed()), ('b', closed('short', at=1020, bid=99.99, ask=100.0)), ('c', closed(at=1030, bid=104, ask=104.01))]
    entries = expected_entries(10_000, 0.0, positions)
    rows, account = stored(entries)
    assert compare(rows, account, entries) == []
    assert account['cash_usdc'] == money(10_000) + sum(e.amount_usdc for e in entries[1:])
    assert account['closed_positions'] == 3


def test_missing_unexpected_and_differing_entries_are_each_reported():
    positions = [('a', closed()), ('b', closed(at=1020))]
    entries = expected_entries(10_000, 0.0, positions)
    rows, account = stored(entries[:2])  # b never booked
    codes = {(i['code'], i.get('position_id')) for i in compare(rows, account, entries)}
    assert ('LEDGER_MISSING_ENTRY', 'b') in codes

    rows, account = stored(entries)
    assert ('LEDGER_UNEXPECTED_ENTRY', 'b') in {(i['code'], i.get('position_id')) for i in compare(rows, account, entries[:2])}

    changed = expected_entries(10_000, 0.0, [('a', {**positions[0][1], 'fees_usdc': 9.0}), positions[1]])
    assert [i['code'] for i in compare(rows, account, changed)] == ['LEDGER_ENTRY_DIFFERS']


def test_broken_running_balance_and_stored_totals_are_reported():
    entries = expected_entries(10_000, 0.0, [('a', closed())])
    rows, account = stored(entries)
    rows[1] = {**rows[1], 'balance_after_usdc': rows[1]['balance_after_usdc'] + 1}
    assert 'LEDGER_RUNNING_BALANCE' in [i['code'] for i in compare(rows, account, entries)]

    rows, account = stored(entries)
    issues = compare(rows, {**account, 'cash_usdc': account['cash_usdc'] + Decimal('0.00000001')}, entries)
    assert [i['code'] for i in issues] == ['ACCOUNT_BALANCE']
    assert compare(rows, None, entries)[0]['code'] == 'ACCOUNT_MISSING'


def test_capital_must_be_positive_and_single():
    with pytest.raises(ValueError):
        capital_entry(0, 0.0)
    entries = expected_entries(10_000, 0.0, [])
    rows, account = stored(entries)
    doubled = rows + [{**rows[0], 'sequence': 2, 'balance_after_usdc': rows[0]['balance_after_usdc'] * 2}]
    assert 'LEDGER_CAPITAL_ENTRY' in [i['code'] for i in compare(doubled, {**account, 'last_sequence': 2}, entries)]
