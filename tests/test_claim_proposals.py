"""Harness proposals count only when the post itself says it, verbatim."""

from __future__ import annotations

from tradesync_core.claim_extraction import NoClaim
from tradesync_core.claim_proposals import EXTRACTOR, parse_proposals, proposal_prompt

POST = "BTC: I'm bearish below 77.3k into the weekend. ETH looks constructive, bullish above 3.4k. SOL short resolved +0.4%."
T = 1_789_240_000_000


def _parse(content, text=POST):
    return parse_proposals(content, source="discord", source_id="sz-market-thesis-desk", text=text, claimed_at_ms=T)


def test_prompt_asks_what_the_post_said_and_carries_no_authority_words() -> None:
    p = proposal_prompt("desk", POST)
    assert "POST ITSELF" in p and "Do not infer" in p and "POST:\n" in p
    for forbidden in ("approve", "execute", "score the"):
        assert forbidden not in p.lower()


def test_verbatim_proposals_become_claims_under_the_harness_extractor() -> None:
    content = 'Here you go: [{"symbol": "BTC", "stance": "bearish", "horizon_minutes": 240, "quote": "bearish below 77.3k"}, ' \
              '{"symbol": "ETH", "stance": "bullish", "horizon_minutes": 60, "quote": "bullish above 3.4k"}]'
    claims = _parse(content)
    assert isinstance(claims, list) and len(claims) == 2
    by = {c.symbol: c for c in claims}
    assert by["BTC-PERP"].direction == "SHORT" and by["BTC-PERP"].horizon_minutes == 240
    assert by["ETH-PERP"].direction == "LONG" and by["ETH-PERP"].horizon_minutes == 60
    assert all(c.extractor == EXTRACTOR and c.source_id == "sz-market-thesis-desk" for c in claims)


def test_an_invented_quote_is_rejected() -> None:
    r = _parse('[{"symbol": "BTC", "stance": "bullish", "horizon_minutes": 60, "quote": "strongly bullish on BTC"}]')
    assert isinstance(r, NoClaim) and "not found verbatim" in r.reason


def test_a_reporting_or_negated_quote_is_rejected() -> None:
    r = _parse('[{"symbol": "SOL", "stance": "bearish", "horizon_minutes": 240, "quote": "SOL short resolved"}]')
    assert isinstance(r, NoClaim) and "negated or reports" in r.reason


def test_untracked_symbol_bad_stance_and_bad_horizon_are_handled() -> None:
    r = _parse('[{"symbol": "DOGE", "stance": "bullish", "horizon_minutes": 60, "quote": "bearish below 77.3k"}]')
    assert isinstance(r, NoClaim) and "not tracked" in r.reason
    r = _parse('[{"symbol": "BTC", "stance": "neutral", "horizon_minutes": 60, "quote": "bearish below 77.3k"}]')
    assert isinstance(r, NoClaim) and "stance" in r.reason
    claims = _parse('[{"symbol": "BTC", "stance": "bearish", "horizon_minutes": 999, "quote": "bearish below 77.3k"}]')
    assert claims[0].horizon_minutes == 240


def test_empty_list_and_non_json_are_no_claim_with_reasons() -> None:
    assert "no directional call" in _parse("[]").reason
    assert "no JSON array" in _parse("The post is bearish on BTC.").reason
    assert "not valid JSON" in _parse("[{broken}]").reason


def test_a_symbol_proposed_both_ways_is_dropped() -> None:
    content = '[{"symbol": "BTC", "stance": "bearish", "horizon_minutes": 240, "quote": "bearish below 77.3k"}, ' \
              '{"symbol": "BTC", "stance": "bullish", "horizon_minutes": 240, "quote": "bullish above 3.4k"}]'
    r = _parse(content)
    assert isinstance(r, NoClaim) and "both ways" in r.reason
