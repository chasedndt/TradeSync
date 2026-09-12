"""The derivatives read lists every context feature, absent ones included, and scores nothing."""

from __future__ import annotations

from tradesync_core.thesis_context import CONTEXT_FEATURES, derivatives_line, derivatives_read

NOW = 1_800_000_000_000


def test_every_context_feature_is_listed_in_sop_order_with_absent_ones_marked() -> None:
    results = [
        {"feature_id": "hl_direct_cvd", "current_value": 12345.6, "unit": "USD_delta", "observed_at_ms": NOW - 5_000, "status": "ready", "scoring_allowed": True},
        {"feature_id": "gdelt_news_tone", "current_value": -1.2, "unit": "tone_score", "observed_at_ms": NOW - 600_000, "status": "context_ready", "scoring_allowed": False},
        {"feature_id": "hl_mark_price_usd", "current_value": 77000.0, "unit": "USD_per_asset", "observed_at_ms": NOW},
    ]
    items = derivatives_read(results, NOW)
    assert [i["feature_id"] for i in items] == [f for f, _ in CONTEXT_FEATURES]
    by = {i["feature_id"]: i for i in items}
    assert by["hl_direct_cvd"]["value"] == 12345.6 and by["hl_direct_cvd"]["age_ms"] == 5_000
    assert by["gdelt_news_tone"]["scoring_allowed"] is False
    assert by["hl_funding_hourly_rate"]["value"] is None and by["hl_funding_hourly_rate"]["status"] == "absent"
    assert "hl_mark_price_usd" not in by


def test_line_formats_by_unit_and_says_absent() -> None:
    items = derivatives_read(
        [{"feature_id": "funding_spread_vs_binance_bps", "current_value": 3.25, "unit": "basis_points", "observed_at_ms": NOW},
         {"feature_id": "hl_funding_hourly_rate", "current_value": 0.0000125, "unit": "decimal_rate_per_hour", "observed_at_ms": NOW}],
        NOW,
    )
    line = derivatives_line(items)
    assert line.startswith("Derivatives and context: ")
    assert "funding spread vs Binance +3.2 bps" in line
    assert "funding (hourly) +0.0013%" in line
    assert "CVD absent" in line and "news tone absent" in line
