"""Binance funding and OI: parsed strictly, compared per 8h, aligned or absent."""

from __future__ import annotations

import pytest

from app.cross_venue import (
    MAX_ALIGNMENT_SKEW_MS,
    attach_cross_venue,
    binance_symbol_for,
    funding_spread_bps,
    parse_open_interest,
    parse_premium_index,
)

T = 1_789_194_597_000
PREMIUM = {"symbol": "BTCUSDT", "markPrice": "77205.80000000", "lastFundingRate": "0.00004476",
           "nextFundingTime": 1_789_200_000_000, "time": T}
OI = {"symbol": "BTCUSDT", "openInterest": "103454.910", "time": T}


def test_symbol_mapping() -> None:
    assert binance_symbol_for("BTC-PERP") == "BTCUSDT"
    assert binance_symbol_for("hype-perp") == "HYPEUSDT"


def test_premium_index_is_parsed_from_the_venue_s_strings() -> None:
    p = parse_premium_index(PREMIUM)
    assert p["funding_rate_8h"] == pytest.approx(0.00004476)
    assert p["mark_price_usd"] == pytest.approx(77205.8)
    assert p["observed_at_ms"] == T and p["next_funding_ms"] == 1_789_200_000_000


def test_malformed_premium_index_yields_nothing() -> None:
    assert parse_premium_index({**PREMIUM, "lastFundingRate": "n/a"}) is None
    assert parse_premium_index({**PREMIUM, "markPrice": "0"}) is None
    assert parse_premium_index({**PREMIUM, "time": "soon"}) is None
    assert parse_premium_index(None) is None


def test_open_interest_is_converted_to_usd_at_the_venue_mark() -> None:
    o = parse_open_interest(OI, 77205.8)
    assert o["contracts"] == pytest.approx(103454.91)
    assert o["open_interest_usd"] == pytest.approx(103454.91 * 77205.8)
    assert parse_open_interest(OI, 0) is None
    assert parse_open_interest({**OI, "openInterest": "-1"}, 77205.8) is None


def test_spread_compares_both_venues_per_eight_hours_in_bps() -> None:
    # Hyperliquid 0.001%/h = 0.008%/8h; Binance 0.004476%/8h; spread 0.3524 bps... times 10,000
    assert funding_spread_bps(0.00001, 0.00004476) == pytest.approx((0.00008 - 0.00004476) * 10_000)
    assert funding_spread_bps(0.0, 0.0) == 0.0


def reference(premium_at=T, oi_at=T):
    return {"BTC-PERP": {
        "premium": {"funding_rate_8h": 0.00004476, "mark_price_usd": 77205.8, "observed_at_ms": premium_at},
        "open_interest": {"open_interest_usd": 7.99e9, "contracts": 103454.91, "observed_at_ms": oi_at},
    }}


def snapshot(ts=T + 30_000, hl_rate=0.00001):
    return {"symbol": "BTC-PERP", "ts": ts, "funding": {"horizons": {"now": hl_rate}}}


def test_all_three_attach_when_fresh_and_aligned() -> None:
    out = attach_cross_venue(snapshot(), reference(), stale_after_ms=600_000)
    d = out["derived"]
    assert d["binance_funding_rate_8h"]["value"] == pytest.approx(0.00004476)
    assert d["binance_open_interest_usd"]["value"] == pytest.approx(7.99e9)
    assert d["funding_spread_vs_binance_bps"]["alignment_skew_ms"] == 30_000
    assert d["funding_spread_vs_binance_bps"]["value"] == pytest.approx(funding_spread_bps(0.00001, 0.00004476))


def test_spread_is_absent_when_the_venues_were_sampled_too_far_apart() -> None:
    """Binance funding is still shown; the comparison is not, because skew would read as spread."""
    out = attach_cross_venue(snapshot(ts=T + MAX_ALIGNMENT_SKEW_MS + 1), reference(), stale_after_ms=3_600_000)
    assert "binance_funding_rate_8h" in out["derived"]
    assert "funding_spread_vs_binance_bps" not in out["derived"]


def test_spread_is_absent_without_a_hyperliquid_funding_reading() -> None:
    snap = {"symbol": "BTC-PERP", "ts": T + 1000}
    out = attach_cross_venue(snap, reference(), stale_after_ms=600_000)
    assert "funding_spread_vs_binance_bps" not in out["derived"]
    assert "binance_open_interest_usd" in out["derived"]


def test_stale_readings_are_dropped_independently() -> None:
    out = attach_cross_venue(snapshot(ts=T + 2_000_000), reference(premium_at=T, oi_at=T + 1_900_000), 600_000)
    assert "binance_funding_rate_8h" not in out["derived"]
    assert "binance_open_interest_usd" in out["derived"]


def test_nothing_attached_means_no_derived_key() -> None:
    out = attach_cross_venue({"symbol": "ETH-PERP", "ts": T}, reference(), 600_000)
    assert "derived" not in out
