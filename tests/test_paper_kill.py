import copy

import pytest

from tradesync_core.managed_paper import open_position
from tradesync_core.paper_kill import EXIT_REASON, kill_close


def book(at=1000, bid=99.99, ask=100.01):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': 100}], 'asks': [{'price': ask, 'size': 100}]}


def test_kill_closes_long_at_observed_bid_after_slippage_with_kill_reason():
    position = open_position('long', 'scalp', 1000, 1, book(), 1000)
    before = copy.deepcopy(position)
    result = kill_close(position, book(at=1010, bid=100.0, ask=100.01), 1010)
    assert position == before
    assert result['status'] == 'closed'
    assert result['exit_reason'] == EXIT_REASON == 'kill_switch'
    assert result['exit_price'] == pytest.approx(100.0 * (1 - 2 / 10000))
    assert result['execution_authority'] is False
    assert 'kill_switch_coincided_with' not in result


def test_kill_closes_short_at_observed_ask():
    position = open_position('short', 'scalp', 1000, 1, book(), 1000)
    result = kill_close(position, book(at=1010, bid=99.99, ask=100.0), 1010)
    assert result['exit_price'] == pytest.approx(100.0 * (1 + 2 / 10000))
    assert result['exit_reason'] == 'kill_switch'


def test_a_stop_seen_at_the_same_observation_is_recorded_not_substituted():
    position = open_position('long', 'scalp', 1000, 1, book(), 1000)
    result = kill_close(position, book(at=1010, bid=95.0, ask=95.01), 1010)
    assert result['exit_reason'] == 'kill_switch'
    assert result['kill_switch_coincided_with'] == 'stop'


def test_no_fresh_executable_quote_means_no_close_and_no_assumed_price():
    position = open_position('long', 'scalp', 1000, 1, book(), 1000)
    for stale, now in [(book(at=1000), 1100), (dict(book(at=1010), bids=[]), 1010)]:
        with pytest.raises(ValueError):
            kill_close(position, stale, now)
    assert position['status'] == 'open'


def test_closed_position_is_refused():
    closed = kill_close(open_position('long', 'scalp', 1000, 1, book(), 1000), book(at=1010, bid=100, ask=100.01), 1010)
    with pytest.raises(ValueError):
        kill_close(closed, book(at=1020, bid=100, ask=100.01), 1020)
