from types import MappingProxyType

import pytest

from tradesync_core.paper_account import Mark, snapshot
from tradesync_core.paper_correlation import MAX_AGE_S, BucketView
from tradesync_core.paper_limits import (
    PAUSING,
    Code,
    Entry,
    check_limits,
    evaluate_entry,
    standing_breaches,
    utilisation,
)

NOW = 1_800_000_000.0
# Read-only: an evaluation that tried to change a limit would raise.
LIMITS = MappingProxyType(dict(daily_loss_limit_usdc=200.0, max_drawdown_fraction=0.06, max_gross_exposure_fraction=0.35,
                               max_symbol_exposure_fraction=0.12, max_bucket_exposure_fraction=0.25, correlation_threshold=0.7,
                               max_concurrent_positions=3, max_entry_quote_age_s=15.0, max_mark_age_s=60.0))
BUCKETS = BucketView(NOW - 60, (('BTC-PERP', 'ETH-PERP', 'SOL-PERP'), ('HYPE-PERP',), ('ZEC-PERP',)), frozenset({'PUMP-PERP'}))


def account(marks=(), cash=10_000.0, peak=10_000.0, realised_today=0.0, opening=0.0):
    return snapshot(now_s=NOW, starting_capital=10_000, cash=cash, stored_peak=peak, marks=marks,
                    realised_today=realised_today, unrealised_at_day_start=opening)


def held(symbol, notional=1000.0, unrealised=0.0, age=5.0):
    return Mark(symbol, symbol, 'long', notional / 100, 100.0, notional, unrealised, NOW - age, 'observed_exit_side')


def entry(symbol='BTC-PERP', notional=1000.0, risk=20.0, age=1.0):
    return Entry(symbol, notional, risk, NOW - age)


def codes(entry_, account_, buckets=BUCKETS):
    return [r.code for r in evaluate_entry(entry_, account_, LIMITS, buckets=buckets, now_s=NOW)]


def test_an_entry_inside_every_limit_is_admitted():
    assert codes(entry(), account()) == []


def test_daily_loss_breach_refuses_and_is_a_pausing_breach():
    breached = account(cash=9_800, realised_today=-200)
    assert codes(entry(), breached) == [Code.DAILY_LOSS_LIMIT]
    assert [b.code for b in standing_breaches(breached, LIMITS)] == [Code.DAILY_LOSS_LIMIT]
    assert Code.DAILY_LOSS_LIMIT in PAUSING


def test_planned_risk_past_the_daily_budget_refuses_without_pausing():
    near = account(cash=9_850, realised_today=-150)
    assert codes(entry(risk=60), near) == [Code.DAILY_LOSS_BUDGET]
    assert standing_breaches(near, LIMITS) == []
    assert Code.DAILY_LOSS_BUDGET not in PAUSING


def test_drawdown_breach_refuses_and_pauses():
    breached = account(cash=9_400)
    assert codes(entry(), breached) == [Code.DRAWDOWN_LIMIT]
    assert [b.code for b in standing_breaches(breached, LIMITS)] == [Code.DRAWDOWN_LIMIT]


def test_planned_risk_past_the_drawdown_budget_refuses():
    assert codes(entry(risk=60), account(cash=9_450)) == [Code.DRAWDOWN_BUDGET]


def test_concurrent_position_limit():
    marks = [held('HYPE-PERP', 300), held('ZEC-PERP', 300), held('ETH-PERP', 300)]
    assert codes(entry(), account(marks)) == [Code.MAX_POSITIONS_LIMIT]


def test_stale_or_future_entry_quote_is_refused():
    assert codes(entry(age=16), account()) == [Code.STALE_ENTRY_QUOTE]
    assert codes(entry(age=-5), account()) == [Code.STALE_ENTRY_QUOTE]


def test_stale_open_position_mark_is_refused():
    assert codes(entry(), account([held('HYPE-PERP', 300, age=61)])) == [Code.STALE_POSITION_MARK]


def test_gross_exposure_limit():
    assert codes(entry(), account([held('HYPE-PERP', 1200), held('ZEC-PERP', 1400)])) == [Code.GROSS_EXPOSURE_LIMIT]


def test_symbol_exposure_limit():
    assert codes(entry(), account([held('BTC-PERP', 500)])) == [Code.SYMBOL_EXPOSURE_LIMIT]


def test_correlated_bucket_limit():
    assert codes(entry(), account([held('ETH-PERP', 1000), held('SOL-PERP', 800)])) == [Code.CORRELATED_EXPOSURE_LIMIT]


def test_unmeasured_open_symbols_count_against_the_bucket():
    assert codes(entry(), account([held('ETH-PERP', 700)])) == []
    assert codes(entry(), account([held('ETH-PERP', 700), held('PUMP-PERP', 900)])) == [Code.CORRELATED_EXPOSURE_LIMIT]


def test_missing_stale_or_non_covering_correlation_refuses():
    assert codes(entry(), account(), buckets=None) == [Code.CORRELATION_UNAVAILABLE]
    stale = BucketView(NOW - MAX_AGE_S - 1, BUCKETS.groups, BUCKETS.unmeasured)
    assert codes(entry(), account(), buckets=stale) == [Code.CORRELATION_UNAVAILABLE]
    assert codes(entry('PUMP-PERP'), account()) == [Code.CORRELATION_UNAVAILABLE]
    assert codes(entry('LINK-PERP'), account()) == [Code.CORRELATION_UNAVAILABLE]


def test_non_positive_equity_refuses_alone():
    assert codes(entry(), account(cash=0)) == [Code.NON_POSITIVE_EQUITY]


def test_limit_ordering_is_checked_and_missing_limits_refused():
    assert check_limits(LIMITS)['max_concurrent_positions'] == 3
    with pytest.raises(ValueError):
        check_limits({**LIMITS, 'max_symbol_exposure_fraction': 0.3})
    with pytest.raises(ValueError):
        check_limits({k: v for k, v in LIMITS.items() if k != 'max_mark_age_s'})


def test_utilisation_reports_each_limit_in_use():
    state = account([held('ETH-PERP', 1000, unrealised=-50), held('PUMP-PERP', 500)], cash=9_950, realised_today=-50)
    used = utilisation(state, LIMITS, BUCKETS)
    assert used['daily_loss']['loss_usdc'] == pytest.approx(100)
    assert used['daily_loss']['fraction_of_limit'] == pytest.approx(0.5)
    assert used['gross_exposure']['fraction_of_equity'] == pytest.approx(1500 / 9_900)
    assert used['positions'] == {'open': 2, 'limit': 3}
    assert used['buckets'][0]['members'] == ['BTC-PERP', 'ETH-PERP', 'SOL-PERP']
    assert used['buckets'][0]['exposure_usdc'] == pytest.approx(1000)
    assert used['unmeasured_open_symbols'] == ['PUMP-PERP']
