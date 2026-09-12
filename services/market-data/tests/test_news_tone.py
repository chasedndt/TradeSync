"""GDELT tone: only closed buckets, never a defaulted value, absent when stale."""

from __future__ import annotations

from datetime import datetime, timezone

from app.news_tone import attach_news_tone, parse_timelinetone, query_for

# 2026-09-12 05:45:00Z, the 'last' bucket seen in the live probe.
T_0545 = int(datetime(2026, 9, 12, 5, 45, tzinfo=timezone.utc).timestamp() * 1000)
NOW = T_0545 + 20 * 60 * 1000  # 06:05Z: the 05:45 bucket has closed, 06:00 has not


def timeline(*points):
    return {"timeline": [{"series": "Average Tone", "data": [{"date": d, "value": v} for d, v in points]}]}


def test_the_newest_closed_bucket_is_used_not_the_one_still_filling() -> None:
    payload = timeline(("20260912T053000Z", -1.2), ("20260912T054500Z", 0.4939), ("20260912T060000Z", 3.0))
    reading = parse_timelinetone(payload, NOW)
    assert reading["value"] == 0.4939
    assert reading["observed_at_ms"] == T_0545
    assert reading["buckets_seen"] == 3


def test_a_timeline_with_no_closed_bucket_yields_nothing() -> None:
    assert parse_timelinetone(timeline(("20260912T060000Z", 1.0)), NOW) is None


def test_an_exactly_zero_bucket_is_no_news_not_neutral_news() -> None:
    """GDELT fills a bucket with no matching articles with 0, not a gap."""
    only_empty = timeline(("20260912T053000Z", 0), ("20260912T054500Z", 0))
    assert parse_timelinetone(only_empty, NOW) is None
    # The newest closed bucket with real articles is used, even if a later one is empty.
    mixed = timeline(("20260912T053000Z", -0.8), ("20260912T054500Z", 0))
    assert parse_timelinetone(mixed, NOW)["value"] == -0.8


def test_gdelt_s_empty_object_for_a_thin_query_yields_nothing() -> None:
    assert parse_timelinetone({}, NOW) is None


def test_malformed_points_are_skipped_and_an_empty_result_is_none() -> None:
    payload = timeline(("not-a-date", 1.0), ("20260912T054500Z", "0.5"), ("20260912T054500Z", True))
    assert parse_timelinetone(payload, NOW) is None
    assert parse_timelinetone({"timeline": "x"}, NOW) is None
    assert parse_timelinetone(None, NOW) is None
    assert parse_timelinetone({"timeline": []}, NOW) is None


def test_queries_name_the_project_not_the_ticker() -> None:
    """'NEAR', 'LINK' and 'UNI' are ordinary words; a bare ticker would match noise."""
    assert query_for("NEAR-PERP") == '"NEAR protocol"'
    assert query_for("LINK-PERP") == "chainlink"
    assert query_for("BTC-PERP") == "bitcoin"
    assert query_for("XYZ-PERP") is None


def test_tone_is_attached_only_while_fresh_and_never_as_zero() -> None:
    reading = {"value": 0.5, "observed_at_ms": T_0545, "source": "gdelt_doc_2_timelinetone"}
    fresh = attach_news_tone({"symbol": "BTC-PERP", "ts": T_0545 + 600_000}, {"BTC-PERP": reading}, 3_600_000)
    assert fresh["derived"]["gdelt_news_tone"]["value"] == 0.5

    stale = attach_news_tone({"symbol": "BTC-PERP", "ts": T_0545 + 4_000_000}, {"BTC-PERP": reading}, 3_600_000)
    assert "derived" not in stale

    unknown = attach_news_tone({"symbol": "ETH-PERP", "ts": T_0545}, {"BTC-PERP": reading}, 3_600_000)
    assert "derived" not in unknown
