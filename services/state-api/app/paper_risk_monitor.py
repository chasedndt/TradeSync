"""Paper risk monitor: every observation tick, and whenever something asks.

Closes what the kill switch still holds open, records a new equity peak, and
switches the persistent entry pause on for a standing daily-loss or drawdown
breach, recording the reason and the figures that tripped it. It reads limits
and never writes one, and it never switches a pause off.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app import paper_account_store as accounts
from app import paper_control_store as control
from app import paper_kill_switch
from app import paper_limits_store as limit_store
from app import paper_risk_signals
from app import paper_risk_view as view
from app.paper_market import Market
from tradesync_core.paper_limits import PAUSING, check_limits, standing_breaches

TICK_S = 15.0

status: dict[str, Any] = {"last_tick": None, "last_error": None, "breaches": [], "kill_pending": [],
                          "last_peak_at": None, "last_automatic_pause": None}


async def close_for_kill(pool, market: Market) -> None:
    async with pool.acquire() as conn:
        kill = await control.kill_state(conn)
    if kill is None or not kill["active"]:
        status["kill_pending"] = []
        return
    result = await paper_kill_switch.close_open_positions(pool, market, operator=kill["operator"], reason=kill["reason"])
    status["kill_pending"] = result["pending"]


async def record_peak(pool, now_s: float):
    """Lock the account, take the snapshot, record a new high; return the snapshot."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            if await accounts.load_account(conn, lock="update") is None:
                return None
            snap = await view.account_snapshot(conn, now_s)
            if await accounts.record_peak(conn, snap):
                status["last_peak_at"] = now_s
            return snap


async def pause_on_breach(pool, now_s: float) -> list[dict[str, str]]:
    """Re-evaluate under the entry lock and switch the pause on for a standing breach."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await control.take_entry_lock(conn)
            row = await limit_store.load(conn)
            snap = await view.account_snapshot(conn, now_s)
            if row is None or snap is None:
                return []
            found = [b for b in standing_breaches(snap, check_limits(row)) if b.code in PAUSING]
            if found and await control.pause_automatically(conn, f"Automatic pause [{found[0].code}]: {found[0].message}"):
                status["last_automatic_pause"] = {"at": now_s, **found[0].as_dict()}
            return [b.as_dict() for b in found]


async def tick(pool, market: Market, now_s: float | None = None) -> None:
    now_s = time.time() if now_s is None else now_s
    await close_for_kill(pool, market)
    snap = await record_peak(pool, now_s)
    breaches: list[dict[str, str]] = []
    if snap is not None:
        async with pool.acquire() as conn:
            row = await limit_store.load(conn)
        if row is not None and standing_breaches(snap, check_limits(row)):
            breaches = await pause_on_breach(pool, now_s)
    status.update(last_tick=now_s, last_error=None, breaches=breaches)


def loop(state, market: Market):
    async def run() -> None:
        await asyncio.sleep(5)  # the startup reconciliation goes first
        while True:
            if state.pool is not None:
                try:
                    await tick(state.pool, market)
                except Exception as exc:  # keep monitoring; the gate refuses entries meanwhile
                    status.update(last_tick=time.time(), last_error=type(exc).__name__)
            await paper_risk_signals.sleep_unless_requested("evaluate", TICK_S)

    return run
