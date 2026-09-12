"""Extraction is conservative: a clear symbol and one clear direction, or no claim with a reason."""

from __future__ import annotations

from tradesync_core.claim_extraction import (
    Claim,
    NoClaim,
    direction_of,
    extract,
    horizon_for_interval,
    normalise_symbol,
)

T = 1_789_240_000_000


def test_symbols_normalise_to_the_tracked_universe_only() -> None:
    assert normalise_symbol("BTCUSD") == "BTC-PERP" and normalise_symbol("$eth") == "ETH-PERP"
    assert normalise_symbol("SOL-PERP") == "SOL-PERP" and normalise_symbol("solana") == "SOL-PERP"
    assert normalise_symbol("DOGE") is None and normalise_symbol("ES") is None


def test_direction_needs_one_side_and_no_negation() -> None:
    assert direction_of("EMA crossed up, bullish continuation") == "LONG"
    assert direction_of("lost the level, bearish") == "SHORT"
    assert direction_of("bullish above, bearish below") is None
    assert direction_of("no trade: bullish setup invalidated") is None
    assert direction_of("closed-candle scan, 0 candidates") is None


def test_horizons_follow_the_chart_interval_and_never_exceed_what_is_measured() -> None:
    assert horizon_for_interval("1") == 15 and horizon_for_interval("5") == 15
    assert horizon_for_interval("15") == 60 and horizon_for_interval("30") == 60
    assert horizon_for_interval("60") == 240 and horizon_for_interval("4h") == 240 and horizon_for_interval("D") == 240
    assert horizon_for_interval(None) == 240


def test_a_tradingview_alert_with_a_direction_becomes_one_claim() -> None:
    payload = {
        "schema_version": "tradingview_alert_v1", "indicator": "StrikeZone Universal EMA 21/55 Cross v6 - EMA Fast",
        "ticker": "BTCUSD", "interval": "15", "action": "buy",
        "alert": {"time": "2026-09-12T20:54:27Z", "close": "77145", "note": "cross up"},
    }
    result = extract("tradingview", payload, T)
    assert isinstance(result, list) and len(result) == 1
    c = result[0]
    assert c == Claim("tradingview", "StrikeZone Universal EMA 21/55 Cross v6", "BTC-PERP", "LONG", 60, 1789246467000, "rule_v1", c.excerpt)


def test_the_acceptance_alert_without_a_direction_is_no_claim_with_a_reason() -> None:
    payload = {
        "schema_version": "tradingview_alert_v1", "indicator": "StrikeZone Universal EMA 21/55 Cross v6 - EMA Fast acceptance",
        "ticker": "BTCUSD", "interval": "15", "action": "", "alert": {"note": "first acceptance alert"},
    }
    result = extract("tradingview", payload, T)
    assert isinstance(result, NoClaim) and "no unambiguous direction" in result.reason


def test_a_discord_post_yields_one_claim_per_symbol_with_a_clear_direction() -> None:
    payload = {
        "schema_version": "discord_message_v1", "agent": "sz-market-thesis-desk", "posted_at": "2026-09-12T19:00:00Z",
        "content": "BTC: bearish below 77.3k, looking for continuation lower. ETH bullish above 3.4k. SOL ranging.",
        "embeds": [],
    }
    result = extract("discord", payload, T)
    assert isinstance(result, list)
    by = {c.symbol: c for c in result}
    assert by["BTC-PERP"].direction == "SHORT" and by["ETH-PERP"].direction == "LONG"
    assert "SOL-PERP" not in by and by["BTC-PERP"].horizon_minutes == 240
    assert by["BTC-PERP"].source_id == "sz-market-thesis-desk"


def test_a_post_that_says_both_for_one_symbol_abstains_on_that_symbol() -> None:
    payload = {"schema_version": "discord_message_v1", "agent": "a", "content": "BTC bullish above 78k, bearish below 76k", "embeds": []}
    result = extract("discord", payload, T)
    assert isinstance(result, NoClaim)


def test_a_ledger_describing_a_past_trade_is_not_a_call() -> None:
    assert direction_of("SOL short resolved +0.4% at 240m") is None
    assert direction_of("Paper outcomes: 3 resolved now, BTC sell closed") is None
    payload = {"schema_version": "discord_message_v1", "agent": "sz-hl-paper-outcomes",
               "content": "## Hyperliquid Paper Outcomes\n> Resolved now: 3\n- SOL short resolved +0.4%\n- ETH short resolved -0.1%", "embeds": []}
    assert isinstance(extract("discord", payload, T), NoClaim)
    ledger = {"schema_version": "discord_message_v1", "agent": "sz-hl-paper-outcomes",
              "content": "## 🧾 Hyperliquid Paper Outcomes\n> Resolved now: 1\n\n### 🟢 SOL 30m SHORT — TARGET HIT\n> Net paper PnL: 2.18", "embeds": []}
    r = extract("discord", ledger, T)
    assert isinstance(r, NoClaim) and "report or ledger" in r.reason


def test_hermes_reports_without_direction_are_no_claim() -> None:
    payload = {"schema_version": "hermes_job_output_v1", "agent": "StrikeZone resolver",
               "content": '{"observations": 0, "status": "pass", "read_only": true}'}
    assert isinstance(extract("chaseos", payload, T, observed_ms=T - 5000), NoClaim)


def test_unknown_schema_is_refused_by_name() -> None:
    r = extract("discord", {"schema_version": "something_else"}, T)
    assert isinstance(r, NoClaim) and "no extractor" in r.reason
