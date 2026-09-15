"""The two calls managed_paper.py makes into the paper risk engine, and nothing else.

``admit_entry`` runs inside the entry transaction, after the persistent pause check
and under the same advisory lock, and raises a 409 naming the refusing limit.
``record_position_event`` runs in the transaction that stores a closed position's
state, both at the close and when funding settles after it: it books the realised
result once and any later funding as an adjustment, under a savepoint, so accounting
can never undo or block a close or a settlement.
"""

from __future__ import annotations

from typing import Any, Mapping

from app import paper_account_store, paper_risk_gate


async def admit_entry(conn, *, symbol: str, plan: Mapping[str, Any]) -> None:
    await paper_risk_gate.admit(conn, symbol=symbol, plan=plan)


async def record_position_event(conn, position_id: Any, state: Any) -> None:
    if isinstance(state, dict) and state.get("status") == "closed":
        await paper_account_store.book_position_safely(conn, position_id, state)
