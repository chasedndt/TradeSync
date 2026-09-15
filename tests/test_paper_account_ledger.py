from decimal import Decimal

import pytest

from tradesync_core import paper_funding as funding
from tradesync_core.managed_paper import advance, open_position, settle_funding
from tradesync_core.paper_account_ledger import (
    balances,
    capital_entry,
    compare,
    expected_entries,
    funding_adjustment,
    money,
    realised_entry,
)

H = 3600
ENTRY = 10 * H + 600


def book(at, bid=99.99, ask=100.01):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': 100}], 'asks': [{'price': ask, 'size': 100}]}


def settlement(position, hour, rate=1e-4):
    return funding.settle(position['side'], position['quantity'], hour, {'funding_rate': rate}, {'value': 100.0, 'source': 'test'})


def closed(side='long', close_at=12 * H + 300, hours=(11 * H, 12 * H)):
    opened = open_position(side, 'scalp', 1000, 1, book(ENTRY), ENTRY)
    bid, ask = (100.0, 100.02) if side == 'long' else (99.99, 100.0)
    return advance(opened, book(close_at, bid, ask), close_at, manual_close=True, funding_rows=[settlement(opened, h) for h in hours])


def late(at_close):
    return settle_funding(at_close, [settlement(at_close, 11 * H), settlement(at_close, 12 * H)])


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


def codes(issues):
    return [(i['code'], i.get('position_id')) for i in issues]


def test_money_is_quantised_and_refuses_non_numbers():
    assert money(0.1 + 0.2) == Decimal('0.30000000')
    assert money(-1.234567894) == Decimal('-1.23456789')
    for bad in (float('nan'), float('inf'), True, None, 'nan'):
        with pytest.raises((ValueError, ArithmeticError)):
            money(bad)


def test_realised_entry_nets_fees_and_settled_funding_and_reports_fill_costs_once():
    state = closed()
    entry = realised_entry('p1', state)
    assert entry.amount_usdc == entry.gross_pnl_usdc - entry.fees_usdc - entry.funding_usdc
    assert entry.gross_pnl_usdc == money(state['gross_pnl_usdc']) and entry.funding_usdc == money(state['funding_usdc'])
    costs = state['slippage']['entry']['cost_usdc'] + state['slippage']['exit']['cost_usdc']
    assert costs > 0 and float(entry.slippage_usdc) == pytest.approx(costs)
    assert entry.detail['funding_source'] == 'settled' and entry.occurred_at == state['exit_time']


def test_funding_awaiting_rows_is_settled_in_part_and_older_states_charge_the_scenario():
    assert realised_entry('p1', closed(hours=(11 * H,))).detail['funding_source'] == 'settled_partial'
    legacy = {'status': 'closed', 'side': 'long', 'gross_pnl_usdc': 1.0, 'fees_usdc': 0.9, 'funding_scenario_usdc': 0.05,
              'exit_time': 1010.0, 'slippage_bps': 2.0, 'quantity': 10.0, 'entry_price': 100.02, 'exit_price': 99.98}
    entry = realised_entry('p1', legacy)
    assert entry.detail['funding_source'] == 'scenario' and entry.funding_usdc == Decimal('0.05000000')
    assert float(entry.slippage_usdc) == pytest.approx(10 * (abs(100.02 - 100.02 / 1.0002) + abs(99.98 / 0.9998 - 99.98)))


def test_open_position_has_no_realised_result_or_adjustment():
    opened = open_position('long', 'scalp', 1000, 1, book(ENTRY), ENTRY)
    with pytest.raises(ValueError):
        realised_entry('p1', opened)
    with pytest.raises(ValueError):
        funding_adjustment('p1', Decimal(0), opened, ENTRY)


def test_late_funding_is_an_adjustment_of_exactly_the_change():
    at_close = closed(hours=(11 * H,))
    settled = late(at_close)
    booked = realised_entry('p1', at_close).funding_usdc
    adjustment = funding_adjustment('p1', booked, settled, 13 * H)
    change = money(settled['funding_usdc']) - money(at_close['funding_usdc'])
    assert change != 0 and adjustment.funding_usdc == change and adjustment.amount_usdc == -change
    assert adjustment.kind == 'funding_adjustment' and adjustment.gross_pnl_usdc == adjustment.fees_usdc == adjustment.slippage_usdc == 0
    assert adjustment.detail['funding_source'] == 'settled' and adjustment.detail['settled_hours'] == 2
    assert funding_adjustment('p1', money(settled['funding_usdc']), settled, 13 * H) is None


def test_ledger_recomputed_from_events_equals_stored_balances_including_late_funding():
    a_close = closed(hours=(11 * H,))
    a_latest = late(a_close)
    b_close = closed('short')
    entries = expected_entries(10_000, 0.0, [('a', a_close, a_latest), ('b', b_close, b_close)])
    assert sorted(e.kind for e in entries) == ['capital', 'funding_adjustment', 'realised', 'realised']
    rows, account = stored(entries)
    assert compare(rows, account, entries) == []
    assert account['cash_usdc'] == money(10_000) + sum(e.amount_usdc for e in entries[1:]) and account['closed_positions'] == 2
    change = money(a_latest['funding_usdc']) - money(a_close['funding_usdc'])
    before, after = balances(e for e in entries if e.kind != 'funding_adjustment'), balances(entries)
    assert after['cash_usdc'] - before['cash_usdc'] == -change and after['funding_usdc'] - before['funding_usdc'] == change
    assert after['realised_pnl_usdc'] - before['realised_pnl_usdc'] == -change


def test_missing_unexpected_and_differing_entries_are_each_reported():
    a, b = closed(), closed(close_at=12 * H + 400)
    entries = expected_entries(10_000, 0.0, [('a', a, a), ('b', b, b)])
    rows, account = stored([e for e in entries if e.position_id != 'b'])
    assert ('LEDGER_MISSING_ENTRY', 'b') in codes(compare(rows, account, entries))

    rows, account = stored(entries)
    assert ('LEDGER_UNEXPECTED_ENTRY', 'b') in codes(compare(rows, account, [e for e in entries if e.position_id != 'b']))

    changed = expected_entries(10_000, 0.0, [('a', {**a, 'fees_usdc': 9.0}, {**a, 'fees_usdc': 9.0}), ('b', b, b)])
    assert [i['code'] for i in compare(rows, account, changed)] == ['LEDGER_ENTRY_DIFFERS']


def test_late_funding_not_booked_or_booked_twice_is_reported():
    at_close = closed(hours=(11 * H,))
    entries = expected_entries(10_000, 0.0, [('a', at_close, late(at_close))])
    rows, account = stored([e for e in entries if e.kind != 'funding_adjustment'])
    assert codes(compare(rows, account, entries)) == [('LEDGER_FUNDING_ADJUSTMENT_DIFFERS', 'a')]
    rows, account = stored(entries + [e for e in entries if e.kind == 'funding_adjustment'])
    assert codes(compare(rows, account, entries)) == [('LEDGER_FUNDING_ADJUSTMENT_DIFFERS', 'a')]


def test_broken_running_balance_and_stored_totals_are_reported():
    state = closed()
    entries = expected_entries(10_000, 0.0, [('a', state, state)])
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
