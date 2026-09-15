import pytest

from tradesync_core.managed_paper import advance, open_position
from tradesync_core.paper_account import DAY_S, Mark, daily_pnl, mark, snapshot, utc_day_start


def book(at=1000, bid=99.99, ask=100.01):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': 100}], 'asks': [{'price': ask, 'size': 100}]}


def test_unobserved_position_is_marked_at_entry_less_round_trip_fees():
    plan = open_position('long', 'scalp', 1000, 1, book(), 1000)
    m = mark('p1', 'BTC-PERP', plan)
    assert m.source == 'entry_less_round_trip_fees'
    assert m.unrealised_usdc == pytest.approx(-2 * plan['entry_fee_usdc'])
    assert m.notional_usdc == pytest.approx(1000)
    assert m.marked_at == plan['entry_quote_time']


def test_observed_position_is_marked_at_its_exit_side_after_costs():
    observed = advance(open_position('long', 'scalp', 1000, 1, book(), 1000), book(at=1010, bid=100.5, ask=100.51), 1010)
    m = mark('p1', 'BTC-PERP', observed)
    assert m.source == 'observed_exit_side'
    assert m.mark_price == observed['mark_exit_price']
    assert m.unrealised_usdc == observed['net_estimate_usdc']
    assert m.notional_usdc == pytest.approx(observed['quantity'] * observed['mark_exit_price'])
    with pytest.raises(ValueError):
        mark('p1', 'BTC-PERP', {**observed, 'quantity': float('nan')})


def held(pid, symbol, notional, unrealised, at=5000.0):
    return Mark(pid, symbol, 'long', notional / 100, 100.0, notional, unrealised, at, 'observed_exit_side')


def test_equity_is_cash_plus_marks_and_day_pnl_is_the_equity_change():
    now = 3 * DAY_S + 3600
    marks = [held('a', 'BTC-PERP', 1000, -40), held('b', 'ETH-PERP', 500, 15), held('c', 'BTC-PERP', 250, 5)]
    account = snapshot(now_s=now, starting_capital=10_000, cash=9_970, stored_peak=10_100, marks=marks,
                       realised_today=-30, unrealised_at_day_start=12)
    assert account.unrealised_usdc == pytest.approx(-20)
    assert account.equity_usdc == pytest.approx(9_950)
    assert account.exposure_by_symbol == {'BTC-PERP': 1250, 'ETH-PERP': 500}
    assert account.gross_exposure_usdc == pytest.approx(1750)
    assert account.peak_equity_usdc == 10_100
    assert account.drawdown_usdc == pytest.approx(150)
    assert account.drawdown_fraction == pytest.approx(150 / 10_100)
    assert account.day_start == 3 * DAY_S
    # Equity at day start was (9_970 + 30) + 12; now it is 9_950.
    assert account.day_pnl_usdc == pytest.approx(9_950 - (10_000 + 12))


def test_a_new_high_raises_the_peak_and_has_no_drawdown():
    account = snapshot(now_s=DAY_S, starting_capital=10_000, cash=10_050, stored_peak=10_000,
                       marks=[held('a', 'BTC-PERP', 1000, 25)], realised_today=0, unrealised_at_day_start=0)
    assert account.peak_equity_usdc == pytest.approx(10_075)
    assert account.drawdown_fraction == 0


def test_daily_pnl_rows_are_realised_plus_unrealised_change_per_utc_day():
    now = 2 * DAY_S + 3600
    rows = daily_pnl(now_s=now, days=2, realised=[(DAY_S + 100, -20.0), (2 * DAY_S + 10, 5.0), (10.0, 99.0)],
                     unrealised_at={DAY_S: 1.0, 2 * DAY_S: -3.0}, unrealised_now=2.0)
    assert [r['day'] for r in rows] == ['1970-01-02', '1970-01-03']
    assert rows[0] == {'day': '1970-01-02', 'realised_usdc': -20.0, 'unrealised_change_usdc': -4.0, 'pnl_usdc': -24.0, 'complete': True}
    assert rows[1] == {'day': '1970-01-03', 'realised_usdc': 5.0, 'unrealised_change_usdc': 5.0, 'pnl_usdc': 10.0, 'complete': False}


def test_utc_day_start():
    assert utc_day_start(DAY_S * 5 + 1) == DAY_S * 5
    assert utc_day_start(DAY_S * 5) == DAY_S * 5
