import copy

import pytest

from tradesync_core import paper_funding as funding
from tradesync_core.managed_paper import advance, open_position
from tradesync_core.paper_kill import EXIT_REASON, kill_close

H = 3600
ENTRY = 10 * H + 600


def book(at, bid=99.99, ask=100.01, bids=None, asks=None):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': bids if bids is not None else [{'price': bid, 'size': 100}],
            'asks': asks if asks is not None else [{'price': ask, 'size': 100}]}


def opened(side='long'):
    return open_position(side, 'scalp', 1000, 1, book(ENTRY), ENTRY)


def test_kill_closes_a_long_by_walking_the_bid_ladder_and_paying_the_exit_fee():
    position = opened()
    before = copy.deepcopy(position)
    ladder = [{'price': 100.0, 'size': 4}, {'price': 99.98, 'size': 4}, {'price': 99.95, 'size': 50}]
    result = kill_close(position, book(ENTRY + 60, bid=100.0, ask=100.02, bids=ladder), ENTRY + 60)
    assert position == before
    assert result['status'] == 'closed' and result['exit_reason'] == EXIT_REASON == 'kill_switch'
    assert result['exit']['rule'] == 'kill_switch' and 'coincided_rule' not in result['exit']
    fill = result['slippage']['exit']
    assert fill['basis'] == 'book_walk' and [level[0] for level in fill['levels_taken']] == [100.0, 99.98, 99.95]
    assert 99.95 < result['exit_price'] < 100.0
    assert result['fees']['exit_usdc'] == pytest.approx(result['fees']['rate'] * result['exit_price'] * result['quantity'])
    assert result['net_estimate_usdc'] == pytest.approx(result['gross_pnl_usdc'] - result['fees_usdc'] - result['funding_usdc'])
    assert result['execution_authority'] is False


def test_kill_closes_a_short_by_walking_the_ask_ladder():
    result = kill_close(opened('short'), book(ENTRY + 60, bid=99.99, ask=100.0), ENTRY + 60)
    assert result['exit_reason'] == 'kill_switch' and result['exit_price'] == pytest.approx(100.0)
    assert result['slippage']['exit']['side'] == 'buy'


def test_kill_nets_the_funding_settled_so_far():
    position = opened()
    rows = [funding.settle('long', position['quantity'], hour, {'funding_rate': 1e-4}, {'value': 100.0, 'source': 'test'})
            for hour in (11 * H, 12 * H)]
    now = 12 * H + 120
    result = kill_close(position, book(now, bid=100.0, ask=100.02), now, funding_rows=rows)
    assert result['funding']['status'] == 'complete' and result['funding']['settled_hours'] == 2
    assert result['funding_usdc'] == pytest.approx(sum(row['payment_usdc'] for row in rows))
    assert result['net_estimate_usdc'] == pytest.approx(result['gross_pnl_usdc'] - result['fees_usdc'] - result['funding_usdc'])


def test_a_stop_seen_at_the_same_observation_is_kept_beside_the_kill_reason():
    result = kill_close(opened(), book(ENTRY + 60, bid=95.0, ask=95.01), ENTRY + 60)
    assert result['exit_reason'] == 'kill_switch' and result['exit']['rule'] == 'kill_switch'
    assert result['exit']['coincided_rule'] == 'stop' and result['exit']['gap_fill'] is True


def test_a_thin_book_leaves_the_kill_switch_exit_owed_until_an_observation_can_fill_it():
    owed = kill_close(opened(), book(ENTRY + 60, bid=100.0, ask=100.02, bids=[{'price': 100.0, 'size': 2}]), ENTRY + 60)
    assert owed['status'] == 'open' and owed['pending_exit']['rule'] == 'kill_switch'
    assert 'displayed depth' in owed['pending_exit']['unfilled']
    filled = advance(owed, book(ENTRY + 75, bid=100.0, ask=100.02), ENTRY + 75)
    assert filled['status'] == 'closed' and filled['exit_reason'] == 'kill_switch'


def test_no_usable_book_means_no_close_and_no_assumed_price():
    position = opened()
    for unusable, now in [(book(ENTRY + 10), ENTRY + 100), (dict(book(ENTRY + 10), bids=[]), ENTRY + 10)]:
        with pytest.raises(ValueError):
            kill_close(position, unusable, now)
    assert position['status'] == 'open'


def test_closed_position_is_refused():
    closed = kill_close(opened(), book(ENTRY + 60, bid=100.0, ask=100.02), ENTRY + 60)
    with pytest.raises(ValueError):
        kill_close(closed, book(ENTRY + 70, bid=100.0, ask=100.02), ENTRY + 70)
