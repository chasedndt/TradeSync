"""Read payloads for the paper risk routes: account, limits, risk state and reconciliation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app import paper_account_store as accounts
from app import paper_control_store as control
from app import paper_correlation_job as correlation_job
from app import paper_limits_store as limit_store
from app import paper_reconciliation_runner as runner
from app import paper_reconciliation_store as runs
from app import paper_risk_gate as gate
from app import paper_risk_monitor as monitor
from app import paper_risk_signals
from app import paper_risk_view as view
from tradesync_core.paper_account import daily_pnl, day_boundaries
from tradesync_core.paper_correlation import MAX_AGE_S
from tradesync_core.paper_limits import LIMIT_KEYS, Code, Refusal, check_limits, stale_marks, standing_breaches, utilisation

DAILY_DAYS = 7
AUTHORITY = "paper_only"
NO_ACCOUNT = "Paper account not created yet; the startup reconciliation creates it"


def iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


async def account_payload(conn, now_s: float) -> dict[str, Any]:
    account = await accounts.load_account(conn)
    snap = await view.account_snapshot(conn, now_s)
    if account is None or snap is None:
        raise HTTPException(503, NO_ACCOUNT)
    starts = day_boundaries(now_s, DAILY_DAYS)
    unrealised = {start: await accounts.unrealised_at(conn, start) for start in starts}
    daily = daily_pnl(now_s=now_s, days=DAILY_DAYS, realised=await accounts.realised_since(conn, starts[0]),
                      unrealised_at=unrealised, unrealised_now=snap.unrealised_usdc)
    try:
        configured = float(accounts.configured_starting_capital())
    except ValueError:
        configured = None
    return {
        "as_of": now_s,
        "starting_capital_usdc": snap.starting_capital_usdc,
        "configured_starting_capital_usdc": configured,
        "starting_capital_note": None if configured == snap.starting_capital_usdc
        else "The account keeps the capital it was created with; a changed setting does not rewrite the ledger.",
        "cash_usdc": snap.cash_usdc,
        "realised": {"net_usdc": float(account["realised_pnl_usdc"]), "gross_usdc": float(account["gross_pnl_usdc"]),
                     "fees_usdc": float(account["fees_usdc"]), "funding_usdc": float(account["funding_usdc"]),
                     "slippage_usdc": float(account["slippage_usdc"]), "closed_positions": int(account["closed_positions"]),
                     "slippage_note": "Slippage is inside the fill prices, so gross is already after it."},
        "unrealised_usdc": snap.unrealised_usdc,
        "equity_usdc": snap.equity_usdc,
        "gross_exposure_usdc": snap.gross_exposure_usdc,
        "exposure_by_symbol": snap.exposure_by_symbol,
        "marks": [m.as_dict() for m in snap.marks],
        "oldest_mark_age_s": snap.oldest_mark_age_s(),
        "peak_equity_usdc": snap.peak_equity_usdc,
        "peak_equity_recorded_at": iso(account["peak_equity_at"]),
        "drawdown_usdc": snap.drawdown_usdc,
        "drawdown_fraction": snap.drawdown_fraction,
        "day": {"start": snap.day_start, "realised_usdc": snap.realised_today_usdc,
                "unrealised_at_start_usdc": snap.unrealised_at_day_start_usdc, "pnl_usdc": snap.day_pnl_usdc},
        "daily_pnl": daily,
        "ledger": {"last_sequence": int(account["last_sequence"]), "recent": await accounts.recent_ledger(conn, 10)},
        "booking": dict(accounts.booking_status),
        "authority": AUTHORITY,
        "note": "Paper account from received quotes, not exchange fills. Funding is the frozen scenario unless settled "
                "funding is recorded. Marks are the latest observation; nothing between observations is assumed.",
    }


async def risk_payload(conn, now_s: float) -> dict[str, Any]:
    pause = await control.pause_state(conn)
    kill = await control.kill_state(conn)
    run = await runs.latest_run(conn)
    row = await limit_store.load(conn)
    limits = check_limits(row) if row is not None else None
    snap = await view.account_snapshot(conn, now_s)
    buckets, measurement = await view.buckets(conn, limits["correlation_threshold"]) if limits else (None, None)
    blocking: list[Refusal] = []
    if pause is None or pause["entries_paused"] is not False:
        blocking.append(Refusal("ENTRIES_PAUSED", pause["reason"] if pause is not None else "Paper control missing; entries disabled"))
    blocking += [r for r in (gate.kill_refusal(kill), gate.reconciliation_refusal(run, now_s)) if r is not None]
    if limits is None:
        blocking.append(Refusal(Code.LIMITS_UNAVAILABLE, "Paper limits missing; entries disabled"))
    if snap is None:
        blocking.append(Refusal(Code.ACCOUNT_UNAVAILABLE, NO_ACCOUNT))
    if limits is not None and snap is not None:
        blocking += standing_breaches(snap, limits) + stale_marks(snap, limits, now_s)
    if buckets is None or now_s - buckets.measured_at > MAX_AGE_S:
        blocking.append(Refusal(Code.CORRELATION_UNAVAILABLE, "No current correlation measurement; correlated exposure cannot be bounded"))
    return {
        "as_of": now_s,
        "entries_allowed": not blocking,
        "entries_note": "Whether the standing checks admit a new paper entry. Each entry is still checked against its own size, planned risk and quote.",
        "blocking": [r.as_dict() for r in blocking],
        "pause": None if pause is None else {**dict(pause), "recent": await control.recent_control_events(conn, 10)},
        "kill_switch": None if kill is None else {**dict(kill), "pending_closes": list(monitor.status["kill_pending"]),
                                                  "recent": await control.recent_kill_events(conn, 10)},
        "limits": None if row is None else {"values": {k: row[k] for k in LIMIT_KEYS}, "operator": row["operator"],
                                            "reason": row["reason"], "updated_at": iso(row["updated_at"])},
        "account": None if snap is None else {"equity_usdc": snap.equity_usdc, "cash_usdc": snap.cash_usdc,
                                              "day_pnl_usdc": snap.day_pnl_usdc, "drawdown_fraction": snap.drawdown_fraction,
                                              "peak_equity_usdc": snap.peak_equity_usdc, "gross_exposure_usdc": snap.gross_exposure_usdc},
        "utilisation": utilisation(snap, limits, buckets) if snap is not None and limits is not None else None,
        "correlation": None if measurement is None else {
            "measured_at": iso(measurement["measured_at"]), "age_s": now_s - measurement["measured_at"].timestamp(),
            "max_age_s": MAX_AGE_S, "threshold": limits["correlation_threshold"] if limits else None,
            "buckets": [list(g) for g in buckets.groups] if buckets else [], "unmeasured": sorted(buckets.unmeasured) if buckets else [],
            "bar_interval": measurement["bar_interval"], "window_bars": measurement["window_bars"], "source": measurement["source"]},
        "reconciliation": None if run is None else {"status": run["status"], "finished_at": iso(run["finished_at"]),
                                                    "mismatches": len(run.get("mismatches") or []), "gaps": len(run.get("gaps") or [])},
        "loops": {"monitor": dict(monitor.status), "reconciliation": dict(runner.status), "correlation": dict(correlation_job.status)},
        "authority": AUTHORITY,
        "note": "Paper only. Limits refuse new paper entries and a loss or drawdown breach pauses them; nothing here raises a limit or places an order.",
    }


async def limits_payload(conn) -> dict[str, Any]:
    row = await limit_store.load(conn)
    if row is None:
        raise HTTPException(503, "Paper limits missing; entries disabled")
    return {"limits": {k: row[k] for k in LIMIT_KEYS}, "operator": row["operator"], "reason": row["reason"],
            "updated_at": iso(row["updated_at"]), "recent_changes": await limit_store.recent_events(conn, 20),
            "authority": AUTHORITY, "note": "Limits change only by an operator's audited request. Nothing raises a limit automatically."}


async def reconciliation_payload(conn) -> dict[str, Any]:
    run = await runs.latest_run(conn)
    last = None if run is None else {
        "id": str(run["id"]), "trigger": run["trigger"], "started_at": iso(run["started_at"]), "finished_at": iso(run["finished_at"]),
        "status": run["status"], "positions_checked": run["positions_checked"], "open_positions": run["open_positions"],
        "mismatches": run["mismatches"], "gaps": run["gaps"], "account": run["account"], "error": run.get("error")}
    return {"last_run": last, "recorded_gaps": await runs.recent_gaps(conn, 50), "loop": dict(runner.status),
            "process_started_at": paper_risk_signals.PROCESS_STARTED_AT, "authority": AUTHORITY,
            "note": "Gaps are reported with their start and end and never filled. A mismatch pauses new paper entries; "
                    "an operator resumes them after a clean run."}
