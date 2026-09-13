"""The quant lab's matrix, equity, scorecards, cohorts and health read the way the dashboard shows them."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tradesync_core.strikezone_scorecards import assumption_view, cohort_rows, scorecard_rows
from tradesync_core.strikezone_summary import MAX_CURVE_POINTS, equity_curve, forward_cells, health_view, stale_after_minutes

NOW = datetime(2026, 9, 13, 15, 0, tzinfo=timezone.utc)


def test_the_matrix_marks_missing_and_stale_pairs() -> None:
    latest = [
        {"asset": "BTC", "timeframe": "15m", "direction": "no_trade", "confidence": 0.0, "signal_at": NOW - timedelta(minutes=20)},
        {"asset": "ETH", "timeframe": "1h", "direction": "long", "confidence": 0.6, "signal_at": NOW - timedelta(hours=3)},
    ]
    trades = [{"asset": "ETH", "timeframe": "1h", "direction": "long", "signal_at": NOW - timedelta(hours=3),
               "expiry_at": NOW + timedelta(hours=1), "entry_price": 10.0, "invalidation_price": 9.0, "target_price": 12.0,
               "has_outcome": False}]
    counts = [{"asset": "BTC", "timeframe": "15m", "calls_24h": 40, "trades_24h": 3}]
    results = [{"asset": "BTC", "timeframe": "15m", "resolved": 4, "wins": 1, "net": -3.456}]
    assets, timeframes, cells = forward_cells(latest, trades, counts, results, {("ETH", "1h"): 1}, NOW)
    assert assets == ["BTC", "ETH"] and timeframes == ["15m", "1h"] and len(cells) == 4
    by = {(c["asset"], c["timeframe"]): c for c in cells}
    btc = by[("BTC", "15m")]
    assert not btc["stale"] and btc["win_rate_7d"] == 0.25 and btc["net_7d"] == -3.46 and btc["calls_24h"] == 40
    eth = by[("ETH", "1h")]
    assert eth["stale"] and eth["last_trade"]["status"] == "open" and eth["open_trades"] == 1
    assert by[("BTC", "1h")]["last_signal_at"] is None and by[("BTC", "1h")]["stale"]
    assert stale_after_minutes("15m") == 75 and stale_after_minutes("1h") == 135


def test_the_equity_curve_tracks_drawdown_and_keeps_the_last_point() -> None:
    t0 = NOW - timedelta(days=1)
    curve = equity_curve([(t0, 10), (t0 + timedelta(hours=1), -15), (t0 + timedelta(hours=2), "2.5"), (None, 5), (t0, None)])
    assert curve["trades"] == 3 and curve["net_pnl_usdc"] == -2.5 and curve["max_drawdown_usdc"] == 15.0 and curve["win_rate"] == 0.667
    many = equity_curve([(t0 + timedelta(minutes=i), 1) for i in range(1000)])
    assert len(many["points"]) == MAX_CURVE_POINTS and many["points"][-1]["cumulative"] == 1000


def test_health_explains_codes_dedupes_names_and_diagnoses_jobs() -> None:
    health = {"ok": False, "checked_at_utc": "2026-09-13T14:30:00Z", "issues": ["signal_ledger_stale", "brand_new_code"],
              "signal_records": 12968, "resolved_outcomes": 644}
    fleet = {"issue_names": ["A", "StrikeZone x", "StrikeZone x"], "strikezone_issue_names": ["StrikeZone x", "StrikeZone x"],
             "fingerprint_first_seen_at": "2026-07-27T16:41:56Z"}
    jobs = [
        {"job_id": "j1", "name": "watchdog", "enabled": True, "last_status": "error",
         "last_error": "line 3: $'\\r': command not found", "next_run_at": NOW - timedelta(hours=1)},
        {"job_id": "j2", "name": "forward test", "enabled": True, "last_status": "ok", "last_error": None,
         "last_delivery_error": "Cannot connect to host discord.com:443 [Temporary failure in name resolution]",
         "next_run_at": NOW + timedelta(minutes=5)},
    ]
    view = health_view(health, fleet, jobs, NOW)
    assert view["ok"] is False and view["checked_age_minutes"] == 30.0 and view["counts"]["signal_records"] == 12968
    assert view["issues"][0]["text"].startswith("No new closed-candle call") and view["issues"][1]["text"] == "Brand new code."
    assert view["fleet"]["strikezone_issue_names"] == ["StrikeZone x"] and view["fleet"]["other_issue_names"] == ["A"]
    first, second = view["jobs"]
    assert "CRLF" in first["diagnosis"] and first["overdue"] and view["failing_jobs"] == 1
    assert second["diagnosis"] is None and "discord.com" in second["delivery_problem"] and not second["overdue"]
    assert health_view(None, None, [], NOW)["ok"] is None


CARD = {
    "asset": "ETH", "timeframe": "30m", "resolved_trades": 58, "wins": 19, "losses": 39, "win_rate_percentage": "32.75",
    "net_pnl_usdc": "-61.349", "profit_factor": "0.5588", "maturity": "insufficient_sample", "score_withheld_reason": "floor not met",
    "confidence_calibration": {"brier_score": "0.25", "average_confidence": "0.51"},
    "rolling_7d": {"trades": 22, "wins": 9, "losses": 13, "net_pnl_usdc": "-27.9"},
    "direction_results": {"long": {"trades": 30, "wins": 10, "losses": 20, "net_pnl_usdc": "-40"}},
    "exit_reason_counts": {"stop": 30, "target": 19},
}


def test_scorecards_become_numbers_in_market_order() -> None:
    rows = scorecard_rows({"scorecards": [CARD, {**CARD, "asset": "BTC", "timeframe": "1h"}, {**CARD, "asset": "BTC", "timeframe": "15m"}, "junk"]})
    assert [(r["asset"], r["timeframe"]) for r in rows] == [("BTC", "15m"), ("BTC", "1h"), ("ETH", "30m")]
    eth = rows[-1]
    assert eth["net_pnl_usdc"] == -61.349 and eth["resolved_trades"] == 58 and eth["brier_score"] == 0.25
    assert eth["rolling_7d"] == {"trades": 22, "wins": 9, "losses": 13, "net_pnl_usdc": -27.9}
    assert eth["direction_results"]["long"]["net_pnl_usdc"] == -40.0 and eth["exit_reason_counts"] == {"stop": 30, "target": 19}
    assert scorecard_rows(None) == []


def test_cohorts_rank_by_independent_sample() -> None:
    doc = {"regime_conditioned_paper_analytics": {"minimum_independent_sample": 30, "cohorts": [
        {"asset": "ETH", "timeframe": "1h", "utc_session": "london", "independent_sample": 5, "net_pnl_usdc": "1.5", "sample_adequacy": "insufficient"},
        {"asset": "BTC", "timeframe": "15m", "utc_session": "asia", "independent_sample": 45, "net_pnl_usdc": "-76.1", "sample_adequacy": "adequate"},
    ], "aggregate": {"resolved_trades": 628, "net_pnl_usdc": "-910.34"}}}
    view = cohort_rows(doc)
    assert [c["independent_sample"] for c in view["cohorts"]] == [45, 5]
    assert view["aggregate"]["net_pnl_usdc"] == -910.34 and view["minimum_independent_sample"] == 30
    assert cohort_rows({})["cohorts"] == []


def test_assumptions_view() -> None:
    view = assumption_view({"paper_notional_usdc": "1000", "entry_fee_rate": "0.00045", "entry_liquidity": "taker",
                            "exit_liquidity": "taker", "adverse_slippage_bps_each_fill": "2"})
    assert view["paper_notional_usdc"] == 1000.0 and view["liquidity"] == "taker in, taker out"
    assert assumption_view(None) is None
