"""Paper account storage: the account row, its append-only ledger and recorded equity peaks.

A closed position is booked inside the transaction that stores its state, under a
savepoint (``book_position_safely``): its realised entry once, from the state its
``closed`` event recorded, then a funding adjustment for any funding settled since the
ledger last charged it. Booking is idempotent per position, so repeating it with the
same state appends nothing. If booking fails the close still stands, and reconciliation
reports what is missing, which keeps new entries paused. The account is created on
first need with the configured starting capital as its first ledger row.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app import paper_risk_signals
from app.paper_json import decode
from tradesync_core.paper_account import AccountSnapshot, mark
from tradesync_core.paper_account_ledger import REALISED, ZERO, LedgerEntry, capital_entry, funding_adjustment, money, realised_entry
from tradesync_core.paper_reconciliation import event_state, latest_state

ACCOUNT_INIT_LOCK_KEY = 230915
STARTING_CAPITAL_ENV = "PAPER_STARTING_CAPITAL_USDC"
DEFAULT_STARTING_CAPITAL = "10000"

# Statements tools/qa_paper_risk_sql.py prepares against PostgreSQL as they are.
POSITION_ENTRIES_SQL = "SELECT kind, funding_usdc FROM paper_account_ledger WHERE position_id = $1"
CLOSE_STATE_SQL = ("SELECT payload->'position' FROM managed_paper_events WHERE position_id = $1 AND kind = 'closed' "
                   "ORDER BY created_at LIMIT 1")
INSERT_ENTRY_SQL = (
    "INSERT INTO paper_account_ledger (id, kind, position_id, occurred_at, amount_usdc, gross_pnl_usdc, fees_usdc, funding_usdc, "
    "slippage_usdc, balance_after_usdc, detail) VALUES ($1, $2, $3, to_timestamp($4::float8), $5, $6, $7, $8, $9, $10, $11::jsonb) "
    "RETURNING sequence")
UPDATE_BALANCES_SQL = (
    "UPDATE paper_account SET cash_usdc = $1, realised_pnl_usdc = realised_pnl_usdc + $2, gross_pnl_usdc = gross_pnl_usdc + $3, "
    "fees_usdc = fees_usdc + $4, funding_usdc = funding_usdc + $5, slippage_usdc = slippage_usdc + $6, "
    "closed_positions = closed_positions + $7, last_sequence = $8, updated_at = clock_timestamp() "
    "WHERE singleton AND last_sequence = $9")

booking_status: dict[str, Any] = {"last_error": None, "last_error_at": None}


def as_uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def configured_starting_capital() -> Decimal:
    raw = os.getenv(STARTING_CAPITAL_ENV, DEFAULT_STARTING_CAPITAL).strip()
    try:
        amount = money(Decimal(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{STARTING_CAPITAL_ENV} is not a number") from exc
    if amount <= 0:
        raise ValueError(f"{STARTING_CAPITAL_ENV} must be positive")
    return amount


async def load_account(conn, *, lock: str | None = None):
    suffix = {None: "", "share": " FOR SHARE", "update": " FOR UPDATE"}[lock]
    return await conn.fetchrow("SELECT * FROM paper_account WHERE singleton" + suffix)


async def ensure_account(conn, starting_capital: Any = None):
    """The account row, locked for update; created with its capital entry if it does not exist."""
    row = await load_account(conn, lock="update")
    if row is not None:
        return row
    await conn.execute("SELECT pg_advisory_xact_lock($1)", ACCOUNT_INIT_LOCK_KEY)
    row = await load_account(conn, lock="update")
    if row is not None:
        return row
    entry = capital_entry(configured_starting_capital() if starting_capital is None else starting_capital, time.time())
    sequence = await conn.fetchval(
        "INSERT INTO paper_account_ledger (id, kind, occurred_at, amount_usdc, balance_after_usdc, detail) "
        "VALUES ($1, 'capital', clock_timestamp(), $2, $2, $3::jsonb) RETURNING sequence",
        uuid.uuid4(), entry.amount_usdc, json.dumps(dict(entry.detail)),
    )
    return await conn.fetchrow(
        "INSERT INTO paper_account (starting_capital_usdc, cash_usdc, last_sequence, peak_equity_usdc, peak_equity_at) "
        "VALUES ($1, $1, $2, $1, clock_timestamp()) RETURNING *",
        entry.amount_usdc, sequence,
    )


async def _append(conn, account: Any, entry: LedgerEntry) -> tuple[dict[str, Any], int]:
    """Append one entry and move the balances with it; the account must not have moved since it was read."""
    balance = account["cash_usdc"] + entry.amount_usdc
    sequence = await conn.fetchval(
        INSERT_ENTRY_SQL, uuid.uuid4(), entry.kind, as_uuid(entry.position_id), entry.occurred_at, entry.amount_usdc,
        entry.gross_pnl_usdc, entry.fees_usdc, entry.funding_usdc, entry.slippage_usdc, balance, json.dumps(dict(entry.detail), default=str),
    )
    updated = await conn.execute(
        UPDATE_BALANCES_SQL, balance, entry.amount_usdc, entry.gross_pnl_usdc, entry.fees_usdc, entry.funding_usdc,
        entry.slippage_usdc, int(entry.kind == REALISED), sequence, account["last_sequence"],
    )
    if updated != "UPDATE 1":
        raise RuntimeError("Paper account moved while a position was being booked")
    return {**dict(account), "cash_usdc": balance, "last_sequence": sequence}, sequence


async def book_position(conn, position_id: Any, state: dict[str, Any], *, starting_capital: Any = None) -> list[int]:
    """Bring the ledger in line with one closed position; return the sequences appended, none when already in line."""
    if state.get("status") != "closed":
        return []
    identity = as_uuid(position_id)
    account = await ensure_account(conn, starting_capital)
    booked = await conn.fetch(POSITION_ENTRIES_SQL, identity)
    charged = sum((Decimal(str(row["funding_usdc"])) for row in booked), ZERO)
    appended: list[int] = []
    if not any(row["kind"] == REALISED for row in booked):
        recorded = decode(await conn.fetchval(CLOSE_STATE_SQL, identity))
        entry = realised_entry(identity, recorded if isinstance(recorded, dict) else state)
        account, sequence = await _append(conn, account, entry)
        appended.append(sequence)
        charged += entry.funding_usdc
    adjustment = funding_adjustment(identity, charged, state, time.time())
    if adjustment is not None:
        account, sequence = await _append(conn, account, adjustment)
        appended.append(sequence)
    return appended


async def book_position_safely(conn, position_id: Any, state: dict[str, Any]) -> list[int]:
    """Book under a savepoint; never let accounting undo a close or a funding settlement."""
    try:
        async with conn.transaction():
            return await book_position(conn, position_id, state)
    except Exception as exc:  # reconciliation reports what is missing and keeps entries paused
        booking_status.update(last_error=f"{type(exc).__name__} booking {position_id}", last_error_at=time.time())
        print(f"[PaperRisk] position {position_id} not booked: {type(exc).__name__}")
        paper_risk_signals.request("reconcile")
        return []


async def ledger_rows(conn) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT sequence, kind, position_id, occurred_at, amount_usdc, gross_pnl_usdc, fees_usdc, funding_usdc, "
        "slippage_usdc, balance_after_usdc FROM paper_account_ledger ORDER BY sequence"
    )
    return [dict(r) for r in rows]


async def recent_ledger(conn, limit: int = 20) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT sequence, kind, position_id, occurred_at, recorded_at, amount_usdc, gross_pnl_usdc, fees_usdc, funding_usdc, "
        "slippage_usdc, balance_after_usdc, detail FROM paper_account_ledger ORDER BY sequence DESC LIMIT $1", limit)
    return [{**dict(r), "detail": decode(r["detail"])} for r in rows]


async def peaks(conn) -> list[Decimal]:
    return [r["equity_usdc"] for r in await conn.fetch("SELECT equity_usdc FROM paper_equity_peaks")]


async def record_peak(conn, snapshot: AccountSnapshot) -> bool:
    """Record a new equity high. Call inside a transaction whose snapshot was taken after locking the account."""
    account = await load_account(conn, lock="update")
    equity = money(snapshot.equity_usdc)
    if account is None or equity <= account["peak_equity_usdc"]:
        return False
    await conn.execute(
        "INSERT INTO paper_equity_peaks (id, equity_usdc, cash_usdc, unrealised_usdc, marks) VALUES ($1, $2, $3, $4, $5::jsonb)",
        uuid.uuid4(), equity, money(snapshot.cash_usdc), money(snapshot.unrealised_usdc),
        json.dumps([m.as_dict() for m in snapshot.marks]),
    )
    await conn.execute(
        "UPDATE paper_account SET peak_equity_usdc = $1, peak_equity_at = clock_timestamp(), updated_at = clock_timestamp() WHERE singleton",
        equity,
    )
    return True


async def open_positions(conn) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT id, symbol, position_state FROM managed_paper_positions WHERE position_state->>'status' = 'open' ORDER BY created_at"
    )
    return [{"id": r["id"], "symbol": r["symbol"], "position_state": decode(r["position_state"])} for r in rows]


async def realised_since(conn, start_s: float) -> list[tuple[float, float]]:
    """Realised results and funding adjustments booked since ``start_s``, as (time, amount)."""
    rows = await conn.fetch(
        "SELECT extract(epoch FROM occurred_at)::float8 AS at, amount_usdc FROM paper_account_ledger "
        "WHERE kind <> 'capital' AND occurred_at >= to_timestamp($1::float8)", start_s)
    return [(float(r["at"]), float(r["amount_usdc"])) for r in rows]


# The latest few events of each position open at the boundary, by write time. The
# lifecycle-latest among them is chosen in Python (``latest_state``), so one
# ordering rule serves reconciliation and marks alike.
STATES_AT_SQL = """
SELECT p.id, p.symbol, e.kind, e.payload
FROM managed_paper_positions p
CROSS JOIN LATERAL (
  SELECT kind, payload FROM managed_paper_events
  WHERE position_id = p.id AND created_at <= $1 AND (kind = 'opened' OR payload ? 'position')
  ORDER BY created_at DESC LIMIT 5
) e
WHERE p.created_at <= $1
  AND (p.position_state->>'status' = 'open' OR (p.position_state->>'exit_time')::float8 >= $2)
"""


async def unrealised_at(conn, boundary_s: float) -> float:
    """Total unrealised result, at their latest observation by the boundary, of positions open at it."""
    rows = await conn.fetch(STATES_AT_SQL, datetime.fromtimestamp(boundary_s, timezone.utc), boundary_s)
    grouped: dict[Any, tuple[str, list[dict[str, Any]]]] = {}
    for row in rows:
        state = event_state(row["kind"], decode(row["payload"]))
        if state is not None:
            grouped.setdefault(row["id"], (row["symbol"], []))[1].append(state)
    total = 0.0
    for identity, (symbol, states) in grouped.items():
        latest = latest_state(states)
        if latest is not None and latest.get("status") == "open":
            total += mark(identity, symbol, latest).unrealised_usdc
    return total
