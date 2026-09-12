"""The thesis is assembled from measured evidence and never invents a direction."""

from __future__ import annotations

from tradesync_core.thesis import (
    HIGH_IMPACT_WINDOW_MINUTES,
    STALE_AFTER_MS,
    anchor_levels,
    build_thesis,
    confirmation_stack,
    invalidation,
    no_trade_conditions,
)

NOW = 1_800_000_000_000
BUCKET = 900


def candles(n: int, start_price: float = 100.0):
    """n closed 15m candles, each one unit higher than the last."""
    out = []
    for i in range(n):
        p = start_price + i
        out.append({"time": 1_000_000 + i * BUCKET, "open": p, "high": p + 0.5, "low": p - 0.5, "close": p + 0.2})
    return out


def test_anchors_cover_1h_4h_24h_and_say_when_coverage_is_short() -> None:
    a = anchor_levels(candles(96), BUCKET)
    assert a["high_24h"] == 195.5 and a["low_24h"] == 99.5 and a["covered_24h"]
    assert a["high_1h"] == 195.5 and a["low_1h"] == 191.5
    short = anchor_levels(candles(8), BUCKET)
    assert short["covered_4h"] is False and short["covered_1h"] is True and short["candles"] == 8
    assert anchor_levels([], BUCKET)["note"].startswith("no candles")


def test_invalidation_is_the_trailing_hour_extreme_against_the_read() -> None:
    a = anchor_levels(candles(8), BUCKET)
    assert invalidation("SHORT", a, "falling")["level"] == a["high_1h"]
    assert invalidation("LONG", a, "rising")["level"] == a["low_1h"]
    assert invalidation("NONE", a, "flat")["level"] is None


def test_confirmation_stack_joins_contributors_to_what_they_earned() -> None:
    stack = confirmation_stack(
        [{"feature_id": "a", "score": -0.4, "quality": 1.0}, {"feature_id": "b", "score": 0.1, "quality": 1.0}],
        {"a": {"standing": "scoring", "earned": True, "earned_by": ["60m as_read"], "entries_with_reading": 40}},
    )
    assert stack[0]["reads"] == "SHORT" and stack[0]["earned"] and stack[0]["earned_by"] == ["60m as_read"]
    assert stack[1]["reads"] == "LONG" and not stack[1]["earned"] and stack[1]["standing"] == "unknown"


def test_no_trade_conditions_each_state_their_reason_active_or_not() -> None:
    conds = no_trade_conditions(
        gate="CLOSED", execution_enabled=False, observation_age_ms=5_000, source_live=True,
        coverage=0.7, events=[{"impact": "High", "title": "CPI", "minutes_until": 30}], earned_count=0,
    )
    by = {c.code: c for c in conds}
    assert by["no_demonstrated_edge"].active and by["execution_disabled"].active
    assert not by["stale_evidence"].active and not by["low_coverage"].active
    assert by["high_impact_event_near"].active and "CPI in 30 min" in by["high_impact_event_near"].detail
    assert by["no_earned_inputs"].active
    far = no_trade_conditions(gate="OPEN", execution_enabled=True, observation_age_ms=STALE_AFTER_MS + 1, source_live=True,
                              coverage=0.2, events=[{"impact": "High", "title": "x", "minutes_until": HIGH_IMPACT_WINDOW_MINUTES + 1}], earned_count=2)
    by = {c.code: c for c in far}
    assert not by["no_demonstrated_edge"].active and by["stale_evidence"].active and by["low_coverage"].active
    assert not by["high_impact_event_near"].active and not by["no_earned_inputs"].active


def _thesis(**over):
    args = dict(
        symbol="BTC-PERP", now_ms=NOW,
        regime={"regime": "falling", "trailing_return_pct": -0.2, "lookback_minutes": 60, "computed_at_ms": NOW - 60_000},
        signal={"direction": "SHORT", "data_coverage": 0.52, "directional_score": -0.34, "evaluated_at_ms": NOW - 30_000},
        source_status={"status": "live"}, observation_age_ms=4_000, candles=candles(96), bucket_s=BUCKET,
        contributors=[{"feature_id": "hl_return_1h_pct", "score": -0.8, "quality": 1.0}],
        cards=[{"feature_id": "hl_return_1h_pct", "standing": "scoring", "earned": False, "earned_by": []}],
        gate={"gate": "CLOSED", "any_economic_edge": False}, events=[], execution_enabled=False,
    )
    args.update(over)
    return build_thesis(**args)


def test_thesis_has_every_sop_part_and_is_private() -> None:
    t = _thesis()
    for part in ("structure", "anchors", "confirmation_stack", "invalidation", "no_trade_conditions", "confidence"):
        assert part in t
    assert t["visibility"] == "private" and t["schema_version"] == "thesis_v1"
    assert t["verdict"] == "NO TRADE"
    assert t["structure"]["direction"] == "SHORT" and t["structure"]["entry_regime"] == "falling"
    assert t["confidence"]["evidence_coverage"] == 0.52 and "never a win probability" in t["confidence"]["meaning"]
    assert t["invalidation"]["level"] == t["anchors"]["high_1h"]


def test_every_line_names_its_source_and_the_text_is_the_lines_joined() -> None:
    t = _thesis()
    assert len(t["lines"]) == 10
    assert all(line["source"] for line in t["lines"])
    assert t["text"] == "\n".join(line["text"] for line in t["lines"])
    assert t["lines"][1]["age_ms"] == 30_000
    assert t["lines"][3]["text"].startswith("Derivatives and context: ") and t["derivatives"]
    assert t["lines"][5]["text"].startswith("External sources: none of 0 measured")


def test_earned_sources_join_the_stack_and_clear_the_no_earned_inputs_condition() -> None:
    sources = [
        {"source_id": "StrikeZone FVG Engine", "source": "tradingview", "earned": True, "earned_by": ["60m as_stated"], "claims_measured": 40},
        {"source_id": "sz-market-thesis-desk", "source": "discord", "earned": False, "earned_by": [], "claims_measured": 12},
        {"source_id": "quiet", "source": "discord", "earned": False, "earned_by": [], "claims_measured": 0},
    ]
    t = _thesis(sources=sources)
    assert t["sources"] == {"earned": [{"source_id": "StrikeZone FVG Engine", "source": "tradingview", "earned_by": ["60m as_stated"]}],
                            "measured": 2, "recording": 3}
    assert "StrikeZone FVG Engine earned 60m as_stated (2 of 3 sources measured)" in t["text"]
    by = {c["code"]: c["active"] for c in t["no_trade_conditions"]}
    assert by["no_earned_inputs"] is False
    assert "Verdict: NO TRADE" in t["text"] and "not for publication" in t["text"]


def test_no_admitted_read_means_no_direction_no_invalidation_no_coverage() -> None:
    t = _thesis(signal={"direction": "NONE", "data_coverage": None, "directional_score": None, "evaluated_at_ms": NOW})
    assert t["structure"]["direction"] == "NONE" and t["invalidation"]["level"] is None
    assert t["confidence"]["evidence_coverage"] is None
    assert "No admitted paper read" in t["text"]


def test_missing_regime_and_candles_are_reported_not_guessed() -> None:
    t = _thesis(regime=None, candles=[])
    assert t["structure"]["entry_regime"] == "unknown"
    assert "Anchors unavailable" in t["text"] and t["invalidation"]["level"] is None
