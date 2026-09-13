"""What the dashboard shows of the StrikeZone quant lab.

The forward-test matrix (every asset and timeframe with its latest call, how
long ago, whether that is stale, open trades and the last week's results),
the equity of resolved paper trades, the scorecards and regime cohorts with
their decimal strings made numbers, and the lab's health in plain words.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Sequence

from tradesync_core.job_errors import diagnose
from tradesync_core.strikezone_ledger import ledger_status, num, parse_ts

ASSET_ORDER = ("BTC", "ETH", "SOL")
TIMEFRAME_ORDER = ("5m", "15m", "30m", "1h", "4h")
TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}
# The forward-test job runs every 30 minutes (lowered from 15 on 2026-09-13).
JOB_CADENCE_MINUTES = 30
MAX_CURVE_POINTS = 400
JOB_OVERDUE = timedelta(minutes=15)

HEALTH_ISSUES = {
    "signal_ledger_stale": "No new closed-candle call reached the ledger in the last 45 minutes.",
    "signal_matrix_incomplete": "At least one asset and timeframe has had no call in the last 90 minutes.",
    "funding_archive_stale": "Funding history is more than three hours old, so funding costs on new outcomes may be incomplete.",
    "mature_outcome_unresolved": "A trade past its expiry still has no resolved outcome.",
    "active_outcome_integrity_invalid": "An outcome failed its integrity check and is held out of the analysis.",
}


def _rank(value: str, order: Sequence[str]) -> tuple[int, str]:
    return (order.index(value) if value in order else len(order), value)


def _iso(value: Any) -> str | None:
    parsed = parse_ts(value)
    return parsed.isoformat() if parsed else None


def _int(value: Any) -> int:
    parsed = num(value)
    return int(parsed) if parsed is not None else 0


def stale_after_minutes(timeframe: str) -> int:
    """A pair is stale once two job runs (or two candles, if longer) pass without a call, plus a margin."""
    return max(TIMEFRAME_MINUTES.get(timeframe, 60), JOB_CADENCE_MINUTES) * 2 + 15


def forward_cells(
    latest: Sequence[Mapping[str, Any]],
    latest_trades: Sequence[Mapping[str, Any]],
    counts: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    open_counts: Mapping[tuple[str, str], int],
    now: datetime,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """The asset by timeframe matrix. A pair with no call at all still gets a cell, marked stale."""

    def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
        return {(str(r["asset"]), str(r["timeframe"])): r for r in rows}

    by_latest, by_trade, by_count, by_result = keyed(latest), keyed(latest_trades), keyed(counts), keyed(results)
    pairs = set(by_latest) | set(by_count) | set(by_trade)
    assets = sorted({a for a, _ in pairs}, key=lambda a: _rank(a, ASSET_ORDER))
    timeframes = sorted({t for _, t in pairs}, key=lambda t: _rank(t, TIMEFRAME_ORDER))
    cells: list[dict[str, Any]] = []
    for asset in assets:
        for timeframe in timeframes:
            key = (asset, timeframe)
            last, trade = by_latest.get(key), by_trade.get(key)
            count, result = by_count.get(key) or {}, by_result.get(key) or {}
            last_at = parse_ts(last["signal_at"]) if last else None
            age = (now - last_at).total_seconds() / 60 if last_at else None
            resolved, wins = _int(result.get("resolved")), _int(result.get("wins"))
            cells.append({
                "asset": asset,
                "timeframe": timeframe,
                "last_signal_at": last_at.isoformat() if last_at else None,
                "age_minutes": round(age, 1) if age is not None else None,
                "stale_after_minutes": stale_after_minutes(timeframe),
                "stale": age is None or age > stale_after_minutes(timeframe),
                "last_direction": str(last["direction"]) if last else None,
                "last_confidence": num(last.get("confidence")) if last else None,
                "last_trade": {
                    "direction": str(trade["direction"]),
                    "signal_at": _iso(trade["signal_at"]),
                    "entry_price": num(trade.get("entry_price")),
                    "invalidation_price": num(trade.get("invalidation_price")),
                    "target_price": num(trade.get("target_price")),
                    "status": ledger_status(str(trade["direction"]), parse_ts(trade.get("expiry_at")), bool(trade.get("has_outcome")), now),
                } if trade else None,
                "calls_24h": _int(count.get("calls_24h")),
                "trades_24h": _int(count.get("trades_24h")),
                "open_trades": int(open_counts.get(key, 0)),
                "resolved_7d": resolved,
                "wins_7d": wins,
                "win_rate_7d": round(wins / resolved, 3) if resolved else None,
                "net_7d": round(num(result.get("net")) or 0.0, 2),
            })
    return assets, timeframes, cells


def equity_curve(rows: Iterable[tuple[Any, Any]]) -> dict[str, Any]:
    """Cumulative net P&L over resolved trades in exit order, with win rate and maximum drawdown."""
    points: list[dict[str, Any]] = []
    total = peak = max_drawdown = 0.0
    trades = wins = 0
    for at, net in rows:
        exit_at, value = parse_ts(at), num(net)
        if exit_at is None or value is None:
            continue
        trades += 1
        wins += value > 0
        total += value
        peak = max(peak, total)
        max_drawdown = max(max_drawdown, peak - total)
        points.append({"t": exit_at.isoformat(), "cumulative": round(total, 2), "n": trades})
    if len(points) > MAX_CURVE_POINTS:
        step = len(points) / MAX_CURVE_POINTS
        points = [points[int(i * step)] for i in range(MAX_CURVE_POINTS - 1)] + [points[-1]]
    return {
        "points": points,
        "trades": trades,
        "net_pnl_usdc": round(total, 2),
        "win_rate": round(wins / trades, 3) if trades else None,
        "max_drawdown_usdc": round(max_drawdown, 2),
    }


def explain_issue(code: str) -> dict[str, str]:
    return {"code": code, "text": HEALTH_ISSUES.get(code, code.replace("_", " ").capitalize() + ".")}


def lab_job(job: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    status = job.get("last_status")
    failing = status in ("error", "failed")
    next_run = parse_ts(job.get("next_run_at"))
    return {
        "job_id": str(job["job_id"]),
        "name": str(job.get("name") or job["job_id"]),
        "enabled": bool(job.get("enabled", True)),
        "schedule_display": str(job.get("schedule_display") or ""),
        "last_status": status,
        "last_run_at": _iso(job.get("last_run_at")),
        "next_run_at": next_run.isoformat() if next_run else None,
        "overdue": bool(job.get("enabled", True)) and next_run is not None and now - next_run > JOB_OVERDUE,
        "runs_24h": _int(job.get("runs_24h")),
        "failed_24h": _int(job.get("failed_24h")),
        "diagnosis": diagnose(job.get("last_error")) if failing else None,
        "error_excerpt": (str(job.get("last_error"))[:600] if failing and job.get("last_error") else None),
        "delivery_problem": diagnose(job.get("last_delivery_error")),
    }


def health_view(health: Mapping[str, Any] | None, fleet: Mapping[str, Any] | None,
                jobs: Sequence[Mapping[str, Any]], now: datetime) -> dict[str, Any]:
    """The lab's integrity report, the fleet inspector's standing issues, and each lab job with its cause."""
    health = health or {}
    checked = parse_ts(health.get("checked_at_utc"))
    lab_jobs = [lab_job(j, now) for j in jobs]
    fleet_view = None
    if fleet:
        lab_names = list(dict.fromkeys(str(n) for n in fleet.get("strikezone_issue_names") or []))
        all_names = list(dict.fromkeys(str(n) for n in fleet.get("issue_names") or []))
        fleet_view = {
            "issue_count": len(all_names),
            "strikezone_issue_names": lab_names,
            "other_issue_names": [n for n in all_names if n not in lab_names],
            "unchanged_since": _iso(fleet.get("fingerprint_first_seen_at")),
            "checked_at": _iso(fleet.get("checked_at")),
            "last_alert_at": _iso(fleet.get("last_alert_at")),
        }
    return {
        "ok": health.get("ok") if "ok" in health else None,
        "checked_at": checked.isoformat() if checked else None,
        "checked_age_minutes": round((now - checked).total_seconds() / 60, 1) if checked else None,
        "issues": [explain_issue(str(code)) for code in health.get("issues") or []],
        "counts": {
            "signal_records": _int(health.get("signal_records")),
            "paper_candidates": _int(health.get("paper_candidates")),
            "resolved_outcomes": _int(health.get("resolved_outcomes")),
            "correlation_adjusted_sample": _int(health.get("active_correlation_adjusted_sample")),
            "excluded_duplicate_outcomes": _int(health.get("excluded_duplicate_outcomes")),
        },
        "overdue_signal_ids": [str(s) for s in health.get("overdue_signal_ids") or []],
        "fleet": fleet_view,
        "jobs": lab_jobs,
        "failing_jobs": sum(1 for j in lab_jobs if j["last_status"] in ("error", "failed")),
    }
