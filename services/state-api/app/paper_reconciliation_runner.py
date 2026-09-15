"""Restart reconciliation: at startup, every five minutes after, and on request.

Reads everything in one repeatable-read, read-only snapshot, so a close
committing midway cannot make positions and the ledger disagree. Writes the run
and the gaps by their exact stored start, and on any mismatch switches the
persistent entry pause on with the reason. It never repairs a position, a
balance or a gap.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from app import paper_account_store as accounts
from app import paper_control_store as control
from app import paper_reconciliation_store as store
from app import paper_risk_signals
from tradesync_core.paper_reconciliation import GAP_THRESHOLD_S, account_mismatches, gaps, position_mismatches

PERIOD_S = 300
RETRY_S = 60

status: dict[str, Any] = {"last_run_at": None, "last_status": None, "last_error": None}


async def collect(pool) -> dict[str, Any]:
    async with pool.acquire() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            return {
                "positions": await store.positions(conn),
                "latest": await store.latest_states(conn),
                "opened": await store.opened_ids(conn),
                "account": await accounts.load_account(conn),
                "ledger": await accounts.ledger_rows(conn),
                "peaks": await accounts.peaks(conn),
                "pairs": await store.gap_pairs(conn, GAP_THRESHOLD_S),
                "last_seen": await store.open_last_seen(conn),
            }


def assess(data: dict[str, Any], now_s: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Mismatches, and gap records carrying the exact stored timestamps they were measured from."""
    mismatches = position_mismatches(data["positions"], data["latest"], data["opened"])
    closed = [(pid, s) for pid, s in data["latest"].items() if s is not None and s.get("status") == "closed"]
    mismatches += account_mismatches(data["account"], data["ledger"], closed, data["peaks"])
    exact: dict[tuple[str, float], Any] = {}
    pairs, seen = [], []
    for row in data["pairs"]:
        pairs.append((row["position_id"], row["symbol"], row["started_s"], row["ended_s"]))
        exact[(str(row["position_id"]), row["started_s"])] = row["prev_at"]
        exact[(str(row["position_id"]), row["ended_s"])] = row["created_at"]
    for row in data["last_seen"]:
        seen.append((row["id"], row["symbol"], row["last_s"]))
        exact[(str(row["id"]), row["last_s"])] = row["last_at"]
    records = [{**gap, "started_at": exact[(gap["position_id"], gap["started_at"])],
                "ended_at": None if gap["ended_at"] is None else exact[(gap["position_id"], gap["ended_at"])]}
               for gap in gaps(pairs, seen, now_s)]
    return mismatches, records


def public_gap(record: dict[str, Any]) -> dict[str, Any]:
    ended = record["ended_at"]
    return {"position_id": record["position_id"], "symbol": record["symbol"], "started_at": record["started_at"].isoformat(),
            "ended_at": None if ended is None else ended.isoformat(), "seconds": record["seconds"], "ongoing": record["ongoing"]}


def account_summary(account: Any) -> dict[str, Any]:
    if account is None:
        return {}
    return {**{key: str(account[key]) for key in ("starting_capital_usdc", "cash_usdc", "realised_pnl_usdc", "peak_equity_usdc")},
            "closed_positions": int(account["closed_positions"]), "last_sequence": int(account["last_sequence"])}


async def run_once(pool, trigger: str) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    records: list[dict[str, Any]] = []
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await accounts.ensure_account(conn)
        data = await collect(pool)
        mismatches, records = assess(data, time.time())
        run = {"trigger": trigger, "started_at": started, "status": "mismatch" if mismatches else "clean",
               "positions_checked": len(data["positions"]),
               "open_positions": sum(1 for p in data["positions"] if p["position_state"].get("status") == "open"),
               "mismatches": mismatches, "gaps": [public_gap(r) for r in records], "account": account_summary(data["account"])}
    except Exception as exc:  # recorded as a failed run; entries stay refused until a clean one
        records = []
        run = {"trigger": trigger, "started_at": started, "status": "failed", "positions_checked": 0, "open_positions": 0,
               "mismatches": [], "gaps": [], "account": {}, "error": f"{type(exc).__name__}: {exc}"[:500]}
    async with pool.acquire() as conn:
        async with conn.transaction():
            if records:
                await store.upsert_gaps(conn, [{**r, "position_id": accounts.as_uuid(r["position_id"])} for r in records])
            row = await store.insert_run(conn, run)
            if run["status"] == "mismatch":
                first = run["mismatches"][0]
                await control.take_entry_lock(conn)
                await control.pause_automatically(
                    conn, f"Automatic pause [RECONCILIATION_MISMATCH]: {len(run['mismatches'])} mismatch(es); first {first['code']}: {first.get('detail', '')}")
            await store.prune_runs(conn)
    status.update(last_run_at=time.time(), last_status=run["status"], last_error=run.get("error"))
    return row


def loop(state):
    async def run() -> None:
        trigger = "startup"
        while True:
            delay = RETRY_S
            if state.pool is not None:
                try:
                    row = await run_once(state.pool, trigger)
                    trigger = "periodic"
                    delay = RETRY_S if row["status"] == "failed" else PERIOD_S
                except Exception as exc:  # the run could not even be recorded; try again soon
                    status.update(last_run_at=time.time(), last_status="failed", last_error=type(exc).__name__)
            await paper_risk_signals.sleep_unless_requested("reconcile", delay)

    return run
