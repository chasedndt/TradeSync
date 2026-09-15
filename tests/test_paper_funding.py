"""Settled hourly funding: which settlements a position took part in, payments, and unpublished hours."""

import pytest

from tradesync_core import paper_funding as funding

H = 3600


def test_settlements_are_after_entry_and_at_or_before_the_end():
    assert funding.settlement_hours(10 * H + 5, 13 * H) == [11 * H, 12 * H, 13 * H]
    assert funding.settlement_hours(10 * H, 11 * H - 1) == []
    assert funding.settlement_hours(10 * H + 5, 10 * H + 50) == []


def test_longs_pay_positive_rates_and_shorts_receive_them():
    assert funding.payment('long', 2.0, 100.0, 0.0001) == pytest.approx(0.02)
    assert funding.payment('short', 2.0, 100.0, 0.0001) == pytest.approx(-0.02)
    assert funding.payment('short', 2.0, 100.0, -0.0001) == pytest.approx(0.02)


def test_published_rows_normalise_to_the_hour_and_skip_what_is_not_a_settlement():
    rows = funding.published_rates([[11 * H + 3, 1e-5, -2e-4], [12 * H + 1000, 2e-5, 0], [13 * H, float('nan'), 0], 'junk', [14 * H, 3e-5]])
    assert sorted(rows) == [11 * H, 14 * H]
    assert rows[11 * H] == {'funding_rate': 1e-5, 'premium': -2e-4, 'published_time': 11 * H + 3}
    with pytest.raises(ValueError, match='Conflicting'):
        funding.published_rates([[11 * H, 1e-5, 0], [11 * H + 1, 2e-5, 0]])


def test_accrual_so_far_lists_unpublished_hours_instead_of_estimating_them():
    published = funding.published_rates([[11 * H, 1e-5, 0], [12 * H, -2e-5, 0]])
    rows = [funding.settle('long', 3.0, hour, published[hour], {'value': 200.0, 'source': 'market_open_interest.oracle_price', 'observed_at': hour - 20})
            for hour in (11 * H, 12 * H)]
    open_now = funding.summary(10 * H + 30, 13 * H + 10, rows)
    assert (open_now['expected_hours'], open_now['settled_hours'], open_now['missing_hours']) == (3, 2, [13 * H])
    assert open_now['status'] == 'awaiting_rows'
    assert open_now['accrued_usdc'] == pytest.approx(3 * 200 * 1e-5 - 3 * 200 * 2e-5)
    closed = funding.summary(10 * H + 30, 12 * H + 59, rows)
    assert closed['status'] == 'complete' and closed['expected_hours'] == 2


def test_settlement_rows_refuse_unusable_prices_and_off_hour_times():
    published = {'funding_rate': 1e-5, 'premium': 0}
    with pytest.raises(ValueError):
        funding.settle('long', 1.0, 11 * H, published, {'value': 0, 'source': 'x'})
    with pytest.raises(ValueError):
        funding.settle('long', 1.0, 11 * H + 1, published, {'value': 10, 'source': 'x'})


def test_planning_rate_uses_settled_rows_above_a_declared_floor():
    quiet = funding.planning_bps_hour(funding.published_rates([[hour * H, 1e-6] for hour in range(1, 30)]), 0.125)
    assert (quiet['basis'], quiet['bps_hour'], quiet['rows']) == ('declared_floor', 0.125, 24)
    busy = funding.planning_from_records([{'observed_at': hour * H, 'funding_rate': (-1) ** hour * 5e-5} for hour in range(1, 5)], 0.125)
    assert busy['basis'] == 'mean_absolute_settled_rate' and busy['bps_hour'] == pytest.approx(0.5)
    assert funding.planning_bps_hour({}, 0.125)['basis'] == 'declared_floor'
