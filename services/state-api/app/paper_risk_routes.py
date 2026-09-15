"""Paper risk routes: account, limits, risk state, pause, kill switch and reconciliation.

In the style of ``/state/paper-control``: paper only, a reason on every change,
and every change audited with the operator's name. Registers the reconciliation,
monitor and correlation loops with ``app.background``.
"""

from __future__ import annotations

import time

from fastapi import HTTPException

from app import background, paper_correlation_job, paper_kill_switch, paper_market
from app import paper_control_store as control
from app import paper_limits_store as limit_store
from app import paper_reconciliation_runner as runner
from app import paper_reconciliation_store as runs
from app import paper_risk_gate as gate
from app import paper_risk_monitor as monitor
from app import paper_risk_readmodel as readmodel
from app import paper_risk_signals
from app import paper_risk_view as view
from app.paper_risk_models import KillRequest, LimitsRequest, PauseRequest, ResumeAfterKillRequest
from tradesync_core.paper_limits import LIMIT_KEYS, check_limits, standing_breaches

AUTHORITY = "paper_only"


async def resume_refusal(conn, now_s: float) -> str | None:
    """Why new entries must stay paused, if they must: the kill switch, reconciliation or a standing breach."""
    blocked = gate.kill_refusal(await control.kill_state(conn)) or gate.reconciliation_refusal(await runs.latest_run(conn), now_s)
    if blocked is None:
        row = await limit_store.load(conn)
        snap = await view.account_snapshot(conn, now_s)
        breaches = standing_breaches(snap, check_limits(row)) if row is not None and snap is not None else []
        blocked = breaches[0] if breaches else None
    return None if blocked is None else f"New paper entries stay paused [{blocked.code}]: {blocked.message}"


def register(app, state, *, market_data_url: str) -> None:
    fetch_book = paper_market.book_fetcher(market_data_url)

    def pool():
        if state.pool is None:
            raise HTTPException(503, "Paper risk database unavailable; entries disabled")
        return state.pool

    @app.get("/state/paper-account")
    async def paper_account():
        async with pool().acquire() as conn:
            return await readmodel.account_payload(conn, time.time())

    @app.get("/state/paper-limits")
    async def paper_limits():
        async with pool().acquire() as conn:
            return await readmodel.limits_payload(conn)

    @app.post("/state/paper-limits")
    async def change_paper_limits(body: LimitsRequest):
        changes = body.changes()
        if not changes:
            raise HTTPException(422, "No paper limit value given")
        async with pool().acquire() as conn:
            async with conn.transaction():
                await control.take_entry_lock(conn)
                try:
                    previous, row = await limit_store.update(conn, changes=changes, operator=body.operator, reason=body.reason)
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from None
                except LookupError as exc:
                    raise HTTPException(503, str(exc)) from None
        paper_risk_signals.request("evaluate")
        return {"previous": previous, "limits": {k: row[k] for k in LIMIT_KEYS}, "operator": row["operator"],
                "reason": row["reason"], "updated_at": row["updated_at"], "authority": AUTHORITY}

    @app.get("/state/paper-risk")
    async def paper_risk():
        async with pool().acquire() as conn:
            return await readmodel.risk_payload(conn, time.time())

    @app.post("/state/paper-pause")
    async def change_paper_pause(body: PauseRequest):
        async with pool().acquire() as conn:
            async with conn.transaction():
                await control.take_entry_lock(conn)
                if not body.entries_paused:
                    refusal = await resume_refusal(conn, time.time())
                    if refusal:
                        raise HTTPException(409, refusal)
                row = await control.set_pause(conn, paused=body.entries_paused, operator=body.operator, reason=body.reason)
                if row is None:
                    raise HTTPException(503, "Paper control missing; entries disabled")
        return {**dict(row), "operator": body.operator, "authority": AUTHORITY,
                "note": "Pausing stops new paper entries only; open positions keep their observations and exits."
                if body.entries_paused else "Entries are admitted only where the kill switch, reconciliation and every limit also admit them."}

    @app.post("/state/paper-kill")
    async def engage_kill_switch(body: KillRequest):
        result = await paper_kill_switch.engage(pool(), fetch_book, operator=body.operator, reason=body.reason)
        return {**result, "authority": AUTHORITY,
                "note": "No new paper entries. Open paper positions close at their next fresh observed quote; any still open are retried every monitor tick."}

    @app.post("/state/paper-kill/resume")
    async def resume_after_kill_switch(body: ResumeAfterKillRequest):
        return {**await paper_kill_switch.resume(pool(), operator=body.operator, reason=body.reason), "authority": AUTHORITY}

    @app.get("/state/paper-reconciliation")
    async def paper_reconciliation():
        async with pool().acquire() as conn:
            return await readmodel.reconciliation_payload(conn)

    background.add("paper_reconciliation", runner.loop(state))
    background.add("paper_risk_monitor", monitor.loop(state, fetch_book))
    background.add("paper_correlation", paper_correlation_job.loop(state, market_data_url))
