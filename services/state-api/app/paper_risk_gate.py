"""Entry admission against the paper risk engine, inside managed_paper's entry transaction.

Runs after the persistent pause check, under the same advisory lock. Refusal
order: kill switch, reconciliation, limits and account availability, then every
limit (``tradesync_core.paper_limits``). The 409 detail leads with the first
refusal's code and lists the rest. A standing daily-loss or drawdown breach also
asks the monitor to switch the pause on, outside this transaction, because the
refusal rolls this one back.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from fastapi import HTTPException

from app import paper_control_store as control
from app import paper_limits_store as limit_store
from app import paper_reconciliation_store as runs
from app import paper_risk_signals
from app import paper_risk_view as view
from tradesync_core.paper_limits import PAUSING, Code, Entry, Refusal, check_limits, evaluate_entry

RECONCILIATION_MAX_AGE_S = 900  # periodic runs every five minutes; three missed runs refuse entries


def kill_refusal(kill: Mapping[str, Any] | None) -> Refusal | None:
    if kill is None:
        return Refusal(Code.KILL_SWITCH_ACTIVE, "Kill switch state missing; entries disabled")
    if kill["active"]:
        return Refusal(Code.KILL_SWITCH_ACTIVE, f"Kill switch engaged by {kill['operator']}: {kill['reason']}")
    return None


def reconciliation_refusal(run: Mapping[str, Any] | None, now_s: float) -> Refusal | None:
    if run is None or run["started_at"].timestamp() < paper_risk_signals.PROCESS_STARTED_AT:
        return Refusal(Code.RECONCILIATION_PENDING, "No reconciliation has completed since the state API started")
    if now_s - run["finished_at"].timestamp() > RECONCILIATION_MAX_AGE_S:
        return Refusal(Code.RECONCILIATION_PENDING, "The last reconciliation is more than 15 minutes old")
    if run["status"] != "clean":
        first = (run.get("mismatches") or [{}])[0]
        return Refusal(Code.RECONCILIATION_MISMATCH,
                       f"Last reconciliation {run['status']}: {first.get('detail') or run.get('error') or 'see /state/paper-reconciliation'}")
    return None


async def refusals(conn, *, symbol: str, plan: Mapping[str, Any], now_s: float) -> list[Refusal]:
    blocked = kill_refusal(await control.kill_state(conn)) or reconciliation_refusal(await runs.latest_run(conn), now_s)
    if blocked is not None:
        return [blocked]
    row = await limit_store.load(conn)
    if row is None:
        return [Refusal(Code.LIMITS_UNAVAILABLE, "Paper limits missing; entries disabled")]
    try:
        limits = check_limits(row)
        account = await view.account_snapshot(conn, now_s, lock="share")
    except ValueError as exc:
        return [Refusal(Code.ACCOUNT_UNAVAILABLE, f"Paper account figures unavailable: {exc}")]
    if account is None:
        return [Refusal(Code.ACCOUNT_UNAVAILABLE, "Paper account not created yet; reconciliation creates it")]
    buckets, _ = await view.buckets(conn, limits["correlation_threshold"])
    entry = Entry(symbol, float(plan["notional"]), float(plan["planned_risk_usdc"]), float(plan["entry_quote_time"]))
    return evaluate_entry(entry, account, limits, buckets=buckets, now_s=now_s)


def refusal_detail(found: list[Refusal]) -> str:
    lead, others = found[0], found[1:]
    also = f" Also refused by: {', '.join(r.code for r in others)}." if others else ""
    return f"Paper entry refused [{lead.code}]: {lead.message}.{also}"


async def admit(conn, *, symbol: str, plan: Mapping[str, Any], now_s: float | None = None) -> None:
    """Return when every paper risk check admits the entry; otherwise raise 409 naming the refusal."""
    now_s = time.time() if now_s is None else now_s
    try:
        found = await refusals(conn, symbol=symbol, plan=plan, now_s=now_s)
    except Exception as exc:  # unknown state refuses; the entry transaction rolls back
        found = [Refusal(Code.ACCOUNT_UNAVAILABLE, f"Paper risk state unavailable ({type(exc).__name__})")]
    if not found:
        return
    if any(r.code in PAUSING for r in found):
        paper_risk_signals.request("evaluate")
    raise HTTPException(409, refusal_detail(found))
