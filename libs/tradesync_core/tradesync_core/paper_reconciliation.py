"""Restart reconciliation for managed paper positions and the paper account.

Every stored position must equal the latest state its own lifecycle events recorded.
The ledger and stored balances must equal what the events imply
(``paper_account_ledger.compare``): each closed position's realised entry from the
state its ``closed`` event recorded, and funding settled after the close from its
lifecycle-latest state, which late ``funding_settled`` events rewrite. A pause between
consecutive observations of a position longer than the lifecycle's own gap latch
(``COMMON.observation_gap_s``) is reported with its start and end; an open position not
observed for that long is an ongoing gap with no end yet. Nothing here writes an
observation, so a gap is never filled in.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from tradesync_core.paper_account_ledger import capital_entry, compare, money, position_entries
from tradesync_core.paper_lifecycle_rules import COMMON

GAP_THRESHOLD_S = COMMON.observation_gap_s


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def event_state(kind: str, payload: Any) -> Mapping[str, Any] | None:
    """The position state an event recorded: the plan itself for ``opened``, ``payload.position`` otherwise."""
    if not isinstance(payload, Mapping):
        return None
    if kind == "opened":
        return payload
    position = payload.get("position")
    return position if isinstance(position, Mapping) else None


def lifecycle_order(state: Mapping[str, Any]) -> tuple[float, int, int, int]:
    """The lifecycle's own order for states of one position.

    Time evaluated through (quotes and closed candles both advance it), then
    observations counted, then closed after open, then funding hours settled, which
    grow when late funding rewrites a closed position. The write clock is not trusted:
    two transactions can record ``created_at`` in the opposite order to the one in
    which they held the row.
    """
    summary = state.get("funding") if isinstance(state.get("funding"), Mapping) else {}
    return (float(state.get("evaluated_through") or state.get("last_quote_time") or 0.0),
            int(state.get("observations") or 0) + int(state.get("candles") or 0),
            1 if state.get("status") == "closed" else 0,
            int(summary.get("settled_hours") or 0))


def latest_state(states: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return max(states, key=lifecycle_order, default=None)


def position_mismatches(stored: Iterable[Mapping[str, Any]], latest: Mapping[str, Mapping[str, Any] | None],
                        opened: Iterable[Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    opened_ids = {str(identity) for identity in opened}
    for row in stored:
        pid, state = str(row["id"]), row["position_state"]
        if pid not in opened_ids:
            issues.append({"code": "POSITION_WITHOUT_OPENED_EVENT", "position_id": pid, "detail": "No opened event for this position"})
        recorded = latest.get(pid)
        if recorded is None:
            issues.append({"code": "POSITION_WITHOUT_EVENTS", "position_id": pid, "detail": "No lifecycle event records a state for this position"})
            continue
        if canonical(recorded) != canonical(state):
            keys = sorted(k for k in set(recorded) | set(state) if canonical(recorded.get(k)) != canonical(state.get(k)))
            issues.append({"code": "POSITION_STATE_DIFFERS", "position_id": pid,
                           "detail": "Stored state differs from its latest event in: " + ", ".join(keys[:12])})
    return issues


def gaps(pairs: Iterable[tuple[Any, str, float, float]], open_last_seen: Iterable[tuple[Any, str, float]],
         now_s: float, threshold: float = GAP_THRESHOLD_S) -> list[dict[str, Any]]:
    """Observation gaps: closed ones between consecutive events, ongoing ones for open positions."""
    found = []
    for position_id, symbol, started, ended in pairs:
        if ended - started > threshold:
            found.append({"position_id": str(position_id), "symbol": symbol, "started_at": started, "ended_at": ended,
                          "seconds": ended - started, "ongoing": False})
    for position_id, symbol, last_at in open_last_seen:
        if now_s - last_at > threshold:
            found.append({"position_id": str(position_id), "symbol": symbol, "started_at": last_at, "ended_at": None,
                          "seconds": None, "ongoing": True})
    return sorted(found, key=lambda g: (g["started_at"], g["position_id"]))


def peak_mismatch(account: Mapping[str, Any], peaks: Iterable[Any]) -> dict[str, Any] | None:
    """The stored peak must equal the highest recorded peak, or starting capital if none."""
    expected = max([money(account["starting_capital_usdc"]), *(money(p) for p in peaks)])
    stored = money(account["peak_equity_usdc"])
    if stored != expected:
        return {"code": "PEAK_EQUITY_DIFFERS", "detail": f"Stored peak equity {stored} but the recorded peaks give {expected}"}
    return None


def account_mismatches(account: Mapping[str, Any] | None, ledger_rows: Iterable[Mapping[str, Any]],
                       closed: Iterable[tuple[Any, Mapping[str, Any] | None, Mapping[str, Any]]], peaks: Iterable[Any]) -> list[dict[str, Any]]:
    """The account against the events, for closed positions given as (id, state at the close event, latest state)."""
    if account is None:
        return [{"code": "ACCOUNT_MISSING", "detail": "No paper account row; balances cannot be checked"}]
    issues: list[dict[str, Any]] = []
    expected = [capital_entry(account["starting_capital_usdc"], 0.0)]
    skipped: set[str] = set()
    for position_id, close_state, latest in closed:
        pid = str(position_id)
        if close_state is None:
            issues.append({"code": "CLOSED_POSITION_WITHOUT_CLOSE_EVENT", "position_id": pid,
                           "detail": "Closed paper position has no closed event to book its result from"})
            skipped.add(pid)
            continue
        try:
            expected += position_entries(position_id, close_state, latest)
        except ValueError as exc:
            issues.append({"code": "CLOSED_POSITION_UNREADABLE", "position_id": pid, "detail": str(exc)})
            skipped.add(pid)
    issues += [i for i in compare(ledger_rows, account, expected)
               if not (i.get("position_id") in skipped and i["code"] in ("LEDGER_UNEXPECTED_ENTRY", "LEDGER_FUNDING_ADJUSTMENT_DIFFERS"))]
    peak = peak_mismatch(account, peaks)
    if peak:
        issues.append(peak)
    return issues
