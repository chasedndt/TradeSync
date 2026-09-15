"""Kill switch: stop new entries and close every open paper position through the managed-paper close.

Engaging takes the entry lock, records the kill and switches the persistent pause on in
one transaction, so no entry can be admitted after it commits. Positions then close one
by one the way the observer closes them (``managed_paper.update``): funding settled so
far is stored and netted, the exit walks a fresh observed book for the position's
quantity and pays the taker fee at that fill, and the close is booked by the same hook
(``paper_risk_hooks.record_position_event``). The recorded rule is ``kill_switch``
(``tradesync_core.paper_kill``).

A position without a fresh usable book stays open and the monitor retries it every
tick. One whose book cannot take its whole quantity keeps the kill-switch exit owed
until an observation can fill it. No price is assumed. Resuming clears the kill only
when nothing is left open, and leaves new entries paused until the operator resumes
them separately.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import HTTPException

from app import paper_account_store as accounts
from app import paper_control_store as control
from app import paper_funding_store as funding_store
from app import paper_risk_hooks as hooks
from app import paper_risk_signals
from app.paper_json import decode, serial
from app.paper_market import Market
from tradesync_core.paper_kill import kill_close

MISSING = "Kill switch state missing; entries disabled"


async def engage(pool, market: Market, *, operator: str, reason: str) -> dict[str, Any]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await control.take_entry_lock(conn)
            current = await control.kill_state(conn, lock=True)
            if current is None:
                raise HTTPException(503, MISSING)
            already = bool(current["active"])
            if already:
                operator, reason = current["operator"], current["reason"]
            else:
                current = await control.set_kill(conn, active=True, operator=operator, reason=reason)
                await control.kill_event(conn, action="kill", operator=operator, reason=reason)
                paused = await control.pause_state(conn, lock=True)
                if paused is not None and paused["entries_paused"] is not True:
                    await control.set_pause(conn, paused=True, operator=operator, reason=f"Kill switch engaged: {reason}"[:240])
    result = await close_open_positions(pool, market, operator=operator, reason=reason)
    return {"kill_switch": dict(current), "already_engaged": already, **result}


def _open(row: Any) -> dict[str, Any] | None:
    state = decode(row["position_state"]) if row is not None else None
    return state if isinstance(state, dict) and state.get("status") == "open" else None


async def close_one(pool, market: Market, position_id: Any, *, operator: str, reason: str) -> dict[str, Any] | None:
    """Advance one open position for the kill switch; raises ValueError, writing nothing, without a usable book."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT symbol, position_state FROM managed_paper_positions WHERE id = $1", position_id)
        state = _open(row)
        if state is None:
            return None
        try:
            hours = await funding_store.outstanding(conn, position_id, state, time.time())
        except Exception:
            hours = []
    symbol = row["symbol"]
    book = await market.book(symbol)
    try:
        rates, received = await market.funding(symbol, hours) if hours else ({}, None)
    except Exception:  # funding stays listed as missing; a close never waits for it
        rates, received = {}, None
    async with pool.acquire() as conn:
        async with conn.transaction():
            state = _open(await conn.fetchrow("SELECT position_state FROM managed_paper_positions WHERE id = $1 FOR UPDATE", position_id))
            if state is None:
                return None
            now = time.time()
            added, settled = await funding_store.settle_rows(conn, position_id, symbol, state, rates, received, now)
            result = kill_close(state, book, now, funding_rows=settled)
            kind = "closed" if result["status"] == "closed" else "observed"
            await conn.execute("UPDATE managed_paper_positions SET position_state = $2::jsonb, updated_at = now() WHERE id = $1",
                               position_id, serial(result))
            await conn.execute(
                "INSERT INTO managed_paper_events (id, position_id, kind, payload) VALUES ($1, $2, $3, $4::jsonb)",
                uuid.uuid4(), position_id, kind, serial({"position": result, "book": book, "funding_rows_added": added,
                                                        "kill_switch": {"operator": operator, "reason": reason}}),
            )
            if kind == "closed":
                await hooks.record_position_event(conn, position_id, result)
                await control.kill_event(conn, action="close", operator=operator, reason=reason, position_id=position_id,
                                         detail={"symbol": symbol, "exit_price": result.get("exit_price"), "exit_time": result.get("exit_time"),
                                                 "coincided_rule": result["exit"].get("coincided_rule")})
    return result


async def close_open_positions(pool, market: Market, *, operator: str, reason: str) -> dict[str, list[dict[str, Any]]]:
    async with pool.acquire() as conn:
        positions = await accounts.open_positions(conn)
    closed: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for position in positions:
        identity, symbol = position["id"], position["symbol"]
        try:
            result = await close_one(pool, market, identity, operator=operator, reason=reason)
        except ValueError as exc:
            pending.append({"position_id": str(identity), "symbol": symbol, "reason": str(exc)})
            continue
        except Exception as exc:  # market data or database unavailable: retried next tick
            pending.append({"position_id": str(identity), "symbol": symbol, "reason": type(exc).__name__})
            continue
        if result is None:
            continue
        if result["status"] == "closed":
            closed.append({"position_id": str(identity), "symbol": symbol, "exit_price": result.get("exit_price"),
                           "exit_reason": result.get("exit_reason")})
        else:
            owed = (result.get("pending_exit") or {}).get("unfilled") or "waiting for displayed depth"
            pending.append({"position_id": str(identity), "symbol": symbol, "reason": f"Kill-switch exit owed: {owed}"})
    if closed:
        paper_risk_signals.request("evaluate")
    return {"closed": closed, "pending": pending}


async def resume(pool, *, operator: str, reason: str) -> dict[str, Any]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await control.take_entry_lock(conn)
            current = await control.kill_state(conn, lock=True)
            if current is None:
                raise HTTPException(503, MISSING)
            if not current["active"]:
                raise HTTPException(409, "Kill switch is not engaged; nothing to resume")
            still_open = await conn.fetchval("SELECT count(*) FROM managed_paper_positions WHERE position_state->>'status' = 'open'")
            if still_open:
                raise HTTPException(409, f"{still_open} paper position(s) still open under the kill switch; they close at their next fresh quote")
            state = await control.set_kill(conn, active=False, operator=operator, reason=reason)
            await control.kill_event(conn, action="resume", operator=operator, reason=reason)
            paused = await control.pause_state(conn)
    return {"kill_switch": dict(state), "entries_paused": None if paused is None else paused["entries_paused"],
            "note": "Kill switch cleared. New paper entries stay paused until they are resumed separately."}
