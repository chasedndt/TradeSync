"""Eligibility: directional, fresh, and in the universe the API reports; nothing names a symbol list."""

from datetime import datetime, timedelta, timezone

from tradesync_core import paper_eligibility as eligibility

NOW = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)


def opportunity(**overrides):
    return {'symbol': 'HYPE-PERP', 'dir': 'SHORT', 'snapshot_ts': NOW - timedelta(seconds=30), **overrides}


def test_a_fresh_directional_opportunity_in_the_universe_is_eligible():
    assert eligibility.opportunity_refusal(opportunity(), NOW.timestamp()) is None
    assert eligibility.universe_refusal('HYPE-PERP', ['BTC-PERP', 'HYPE-PERP', 'ZEC-PERP']) is None
    assert eligibility.direction(opportunity()) == 'short'


def test_refusals_say_why():
    now = NOW.timestamp()
    assert eligibility.opportunity_refusal(opportunity(dir='NEUTRAL'), now)[0] == 422
    assert eligibility.opportunity_refusal(opportunity(snapshot_ts=NOW - timedelta(minutes=6)), now)[0] == 409
    assert eligibility.opportunity_refusal(opportunity(snapshot_ts=NOW + timedelta(seconds=5)), now)[0] == 409
    assert eligibility.opportunity_refusal(opportunity(snapshot_ts=None), now)[0] == 409
    assert eligibility.opportunity_refusal(opportunity(snapshot_ts=datetime(2026, 9, 15, 0, 59)), now)[0] == 409
    assert eligibility.universe_refusal('DOGE-PERP', ['BTC-PERP']) == (422, 'DOGE-PERP is not in the tracked symbol universe')
    assert eligibility.universe_refusal('BTC-PERP', [])[0] == 503
