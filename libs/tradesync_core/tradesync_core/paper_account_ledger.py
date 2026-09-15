"""Managed-paper account ledger: realised entries, late funding adjustments and the balance identity.

Not the Step 9C fixture ledger in ``paper_ledger``. This ledger is the append-only
table ``paper_account_ledger`` (``ops/migrations/031``). Its first row is the
configured starting capital. Each closed managed paper position then has one
``realised`` entry, taken from the state its ``closed`` event recorded, and a
``funding_adjustment`` entry whenever Hyperliquid funding for an hour it held settles
after the close (a ``funding_settled`` event). The stored balances on ``paper_account``
must equal the sum of the ledger, and the ledger must equal what the lifecycle events
imply. ``compare`` reports every way those can disagree.

Amounts are quantised to 1e-8 USDC before they are added, so a recomputation agrees
with the stored balances exactly. Adjustments telescope: however many were booked,
they sum to the latest funding less the funding at the close.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Iterable, Mapping

QUANTUM = Decimal("0.00000001")
ZERO = Decimal("0")
REALISED, FUNDING_ADJUSTMENT = "realised", "funding_adjustment"
TOTALS = ("cash_usdc", "realised_pnl_usdc", "gross_pnl_usdc", "fees_usdc", "funding_usdc", "slippage_usdc")
COMPONENTS = ("amount_usdc", "gross_pnl_usdc", "fees_usdc", "funding_usdc", "slippage_usdc")

# The one place that knows which lifecycle field holds funding. Managed paper
# positions record settled Hyperliquid funding as ``funding_usdc`` beside a
# ``funding`` summary whose status is "awaiting_rows" while an hour's rate is not
# yet published; older states carry only the frozen scenario, charged as such.
# Update this tuple, not the callers, if the field changes.
FUNDING_FIELDS = (("funding_usdc", "settled"), ("funding_scenario_usdc", "scenario"))


def money(value: Any) -> Decimal:
    """A finite amount as a Decimal quantised to 1e-8 USDC."""
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, str):
        amount = Decimal(value)
    elif isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Money value must be a number")
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Money value must be finite")
        amount = Decimal(repr(value))
    else:
        amount = Decimal(value)
    if not amount.is_finite():
        raise ValueError("Money value must be finite")
    return amount.quantize(QUANTUM, rounding=ROUND_HALF_EVEN)


def _number(state: Mapping[str, Any], key: str) -> float:
    value = state.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Closed paper position lacks a finite {key}")
    return float(value)


def funding(state: Mapping[str, Any]) -> tuple[float, str]:
    """Funding charged to a closed position, and whether it was settled, settled in part, or the scenario."""
    for key, source in FUNDING_FIELDS:
        if state.get(key) is not None:
            summary = state.get("funding")
            if source == "settled" and isinstance(summary, Mapping) and summary.get("status") == "awaiting_rows":
                source = "settled_partial"
            return _number(state, key), source
    raise ValueError("Closed paper position records no funding figure")


def _cost(fill: Any) -> float:
    value = fill.get("cost_usdc") if isinstance(fill, Mapping) else None
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else 0.0


def slippage(state: Mapping[str, Any]) -> float:
    """Cost against the mid at both fills, in USDC: reported beside gross, never subtracted again.

    Fills walk the observed book and record their own cost (``slippage.entry`` and
    ``slippage.exit``, each with ``cost_usdc``), already inside the fill prices. Older
    states carry a flat ``slippage_bps`` instead.
    """
    if state.get("slippage_usdc") is not None:
        return _number(state, "slippage_usdc")
    fills = state.get("slippage")
    if isinstance(fills, Mapping):
        return math.fsum(_cost(fills.get(leg)) for leg in ("entry", "exit"))
    sign = {"long": 1, "short": -1}.get(state.get("side"))
    if sign is None:
        raise ValueError("Closed paper position has no side")
    rate = _number(state, "slippage_bps") / 10000
    quantity = _number(state, "quantity")
    entry, exit_price = _number(state, "entry_price"), _number(state, "exit_price")
    return quantity * (abs(entry - entry / (1 + sign * rate)) + abs(exit_price / (1 - sign * rate) - exit_price))


@dataclass(frozen=True)
class LedgerEntry:
    kind: str  # capital | realised | funding_adjustment
    position_id: str | None
    amount_usdc: Decimal
    occurred_at: float
    gross_pnl_usdc: Decimal = ZERO
    fees_usdc: Decimal = ZERO
    funding_usdc: Decimal = ZERO
    slippage_usdc: Decimal = ZERO
    detail: Mapping[str, Any] = field(default_factory=dict)


def capital_entry(starting_capital: Any, occurred_at: float) -> LedgerEntry:
    amount = money(starting_capital)
    if amount <= 0:
        raise ValueError("Starting capital must be positive")
    return LedgerEntry("capital", None, amount, occurred_at, detail={"source": "configured starting capital"})


def realised_entry(position_id: Any, state: Mapping[str, Any]) -> LedgerEntry:
    """One closed position's realised result at its close: gross after fill costs, less fees and funding."""
    if state.get("status") != "closed":
        raise ValueError("Only a closed paper position has a realised result")
    gross, fees = money(_number(state, "gross_pnl_usdc")), money(_number(state, "fees_usdc"))
    funding_value, funding_source = funding(state)
    charged = money(funding_value)
    return LedgerEntry(
        REALISED, str(position_id), gross - fees - charged, _number(state, "exit_time"),
        gross_pnl_usdc=gross, fees_usdc=fees, funding_usdc=charged, slippage_usdc=money(slippage(state)),
        detail={"exit_reason": state.get("exit_reason"), "side": state.get("side"), "style": state.get("style"),
                "entry_price": state.get("entry_price"), "exit_price": state.get("exit_price"),
                "quantity": state.get("quantity"), "funding_source": funding_source,
                "slippage": "inside fill prices; not subtracted again"},
    )


def funding_adjustment(position_id: Any, booked_funding: Decimal, state: Mapping[str, Any], occurred_at: float) -> LedgerEntry | None:
    """Funding settled for a closed position since the ledger last charged it; None when nothing changed.

    The amount is the negative of the change: a payment reduces cash, a receipt adds to it.
    """
    if state.get("status") != "closed":
        raise ValueError("Only a closed paper position takes a funding adjustment")
    total, source = funding(state)
    change = money(total) - booked_funding
    if change == 0:
        return None
    summary = state.get("funding") if isinstance(state.get("funding"), Mapping) else {}
    return LedgerEntry(
        FUNDING_ADJUSTMENT, str(position_id), -change, occurred_at, funding_usdc=change,
        detail={"funding_source": source, "settled_hours": summary.get("settled_hours"), "expected_hours": summary.get("expected_hours"),
                "missing_hours": summary.get("missing_hours"), "funding_before_usdc": str(booked_funding), "funding_after_usdc": str(money(total))},
    )


def position_entries(position_id: Any, close_state: Mapping[str, Any], latest_state: Mapping[str, Any] | None = None) -> list[LedgerEntry]:
    """What one closed position contributes: its realised entry, and any funding settled since as one adjustment."""
    entry = realised_entry(position_id, close_state)
    adjustment = funding_adjustment(position_id, entry.funding_usdc, latest_state or close_state, entry.occurred_at)
    return [entry] if adjustment is None else [entry, adjustment]


def balances(entries: Iterable[LedgerEntry]) -> dict[str, Any]:
    """The balances a ledger implies."""
    totals = {key: ZERO for key in TOTALS}
    closed = 0
    for entry in entries:
        totals["cash_usdc"] += entry.amount_usdc
        if entry.kind == "capital":
            continue
        closed += entry.kind == REALISED
        totals["realised_pnl_usdc"] += entry.amount_usdc
        for key in ("gross_pnl_usdc", "fees_usdc", "funding_usdc", "slippage_usdc"):
            totals[key] += getattr(entry, key)
    return {**totals, "closed_positions": closed}


def expected_entries(starting_capital: Any, created_at: float,
                     closed: Iterable[tuple[Any, Mapping[str, Any], Mapping[str, Any] | None]]) -> list[LedgerEntry]:
    """The ledger the lifecycle events imply: capital, then each closed position's entries by time."""
    entries = [entry for pid, close_state, latest in closed for entry in position_entries(pid, close_state, latest)]
    entries.sort(key=lambda e: (e.occurred_at, e.position_id or "", e.kind))
    return [capital_entry(starting_capital, created_at), *entries]


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def entry_from_row(row: Mapping[str, Any]) -> LedgerEntry:
    occurred = row.get("occurred_at")
    return LedgerEntry(
        row["kind"],
        str(row["position_id"]) if row.get("position_id") is not None else None,
        _decimal(row["amount_usdc"]),
        occurred.timestamp() if hasattr(occurred, "timestamp") else float(occurred or 0),
        **{key: _decimal(row.get(key, 0)) for key in COMPONENTS[1:]},
    )


def _adjusted_funding(entries: Iterable[LedgerEntry]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for entry in entries:
        if entry.kind == FUNDING_ADJUSTMENT:
            totals[entry.position_id] += entry.funding_usdc
    return dict(totals)


def compare(stored_rows: Iterable[Mapping[str, Any]], account: Mapping[str, Any] | None, expected: list[LedgerEntry]) -> list[dict[str, Any]]:
    """Every disagreement between the stored ledger, the stored balances and the events."""
    issues: list[dict[str, Any]] = []

    def add(code: str, detail: str, position_id: str | None = None) -> None:
        issues.append({"code": code, "detail": detail, **({"position_id": position_id} if position_id else {})})

    if account is None:
        add("ACCOUNT_MISSING", "No paper account row; balances cannot be checked")
        return issues
    rows = sorted(stored_rows, key=lambda r: r["sequence"])
    capital = [r for r in rows if r["kind"] == "capital"]
    if len(capital) != 1 or rows[0]["kind"] != "capital":
        add("LEDGER_CAPITAL_ENTRY", f"Expected exactly one capital entry first; found {len(capital)}")
    elif _decimal(capital[0]["amount_usdc"]) != money(account["starting_capital_usdc"]):
        add("LEDGER_CAPITAL_AMOUNT", f"Capital entry {capital[0]['amount_usdc']} differs from starting capital {account['starting_capital_usdc']}")
    running = ZERO
    for row in rows:
        running += _decimal(row["amount_usdc"])
        if _decimal(row["balance_after_usdc"]) != running:
            add("LEDGER_RUNNING_BALANCE", f"Sequence {row['sequence']} records balance {row['balance_after_usdc']} but the entries sum to {running}")
            break
    if rows and int(account["last_sequence"]) != int(rows[-1]["sequence"]):
        add("ACCOUNT_LAST_SEQUENCE", f"Account last sequence {account['last_sequence']} but the ledger ends at {rows[-1]['sequence']}")
    stored = [entry_from_row(r) for r in rows]
    totals = balances(stored)
    for key in TOTALS:
        if _decimal(account[key]) != totals[key]:
            add("ACCOUNT_BALANCE", f"{key} stored {account[key]} but the ledger sums to {totals[key]}")
    if int(account["closed_positions"]) != totals["closed_positions"]:
        add("ACCOUNT_BALANCE", f"closed_positions stored {account['closed_positions']} but the ledger holds {totals['closed_positions']}")

    wanted = {e.position_id: e for e in expected if e.kind == REALISED}
    booked = {e.position_id: e for e in stored if e.kind == REALISED}
    for pid in sorted(set(wanted) - set(booked)):
        add("LEDGER_MISSING_ENTRY", "Closed paper position has no realised ledger entry", pid)
    for pid in sorted(set(booked) - set(wanted)):
        add("LEDGER_UNEXPECTED_ENTRY", "Ledger entry for a position its events do not show closed", pid)
    for pid in sorted(set(wanted) & set(booked)):
        differs = [key for key in COMPONENTS if getattr(booked[pid], key) != getattr(wanted[pid], key)]
        if differs:
            add("LEDGER_ENTRY_DIFFERS", "Differs from the closing event: " + ", ".join(differs), pid)
    wanted_funding, booked_funding = _adjusted_funding(expected), _adjusted_funding(stored)
    for pid in sorted(set(wanted_funding) | set(booked_funding)):
        if wanted_funding.get(pid, ZERO) != booked_funding.get(pid, ZERO):
            add("LEDGER_FUNDING_ADJUSTMENT_DIFFERS", f"Funding settled after the close is booked as {booked_funding.get(pid, ZERO)} "
                                                     f"but the funding events imply {wanted_funding.get(pid, ZERO)}", pid)
    return issues
