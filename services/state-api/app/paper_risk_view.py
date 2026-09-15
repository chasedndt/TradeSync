"""The paper account and correlation buckets as the gate, the monitor and the read routes see them."""

from __future__ import annotations

from typing import Any

from app import paper_account_store as accounts
from app import paper_correlation_store as correlations
from tradesync_core.paper_account import AccountSnapshot, mark, snapshot, utc_day_start
from tradesync_core.paper_correlation import BucketView, bucket_view


async def account_snapshot(conn, now_s: float, *, lock: str | None = None) -> AccountSnapshot | None:
    """Stored balances plus open positions at their latest marks; None before the account exists."""
    account = await accounts.load_account(conn, lock=lock)
    if account is None:
        return None
    positions = await accounts.open_positions(conn)
    marks = [mark(p["id"], p["symbol"], p["position_state"]) for p in positions]
    day_start = utc_day_start(now_s)
    realised_today = sum(amount for _, amount in await accounts.realised_since(conn, day_start))
    return snapshot(
        now_s=now_s,
        starting_capital=account["starting_capital_usdc"],
        cash=account["cash_usdc"],
        stored_peak=account["peak_equity_usdc"],
        marks=marks,
        realised_today=realised_today,
        unrealised_at_day_start=await accounts.unrealised_at(conn, day_start),
    )


async def buckets(conn, threshold: float) -> tuple[BucketView | None, dict[str, Any] | None]:
    """Buckets from the latest stored measurement at the operator's current threshold."""
    measurement = await correlations.latest(conn)
    if measurement is None:
        return None, None
    return bucket_view(measurement, measurement["measured_at"].timestamp(), threshold), measurement
