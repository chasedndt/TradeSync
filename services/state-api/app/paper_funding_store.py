"""Settled funding for managed paper positions: fetched, valued, stored append-only, read back.

Rates come from market-data's Hyperliquid funding history. Each settlement is valued
at the oracle price recorded in ``market_open_interest`` nearest the settlement
(from five minutes before to one minute after), at the mark price from that row when
it recorded no oracle price, and otherwise not at all: an hour without a recorded
price stays missing rather than being settled at a guess. A row is stored once per
position and hour (``ops/migrations/032``) and never updated.

``GET /state/paper-positions/{id}/funding`` serves the rows behind a position's
funding total.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

import asyncpg
import httpx
from fastapi import HTTPException

from tradesync_core import paper_funding as funding

PRICE_BEFORE_S = 300
PRICE_AFTER_S = 60
TIMEOUT_S = 8.0
STORE_NOTE = ("Hyperliquid settles funding hourly: quantity x oracle price x published rate, longs paying when the rate is "
              "positive. Each row is valued at the oracle price recorded nearest the settlement. An hour whose rate or price "
              "is not recorded yet stays listed as missing.")


def until(state: Mapping[str, Any], now_s: float) -> float:
    """The last instant a position can have settled funding: its exit, or now while it is open."""
    return state["exit_time"] if state["status"] == "closed" else now_s


async def recorded_hours(conn, position_id: uuid.UUID) -> set[int]:
    rows = await conn.fetch("SELECT extract(epoch FROM settled_at)::bigint AS hour FROM managed_paper_funding WHERE position_id=$1", position_id)
    return {int(row["hour"]) for row in rows}


async def outstanding(conn, position_id: uuid.UUID, state: Mapping[str, Any], now_s: float) -> list[int]:
    """Settlement hours the position took part in that have no stored row yet."""
    expected = funding.settlement_hours(state["entry_time"], until(state, now_s))
    if not expected:
        return []
    have = await recorded_hours(conn, position_id)
    return [hour for hour in expected if hour not in have]


async def settle_rows(conn, position_id: uuid.UUID, symbol: str, state: Mapping[str, Any],
                      rates: Mapping[int, Mapping[str, Any]], received_at: float | None, now_s: float) -> tuple[int, list[dict[str, Any]] | None]:
    """Store what can be settled and read every row back, inside a savepoint.

    A database failure here (the table missing before migration 032, say) returns no
    rows instead of raising, so quotes are still observed and exits still fire; the
    position's funding then lists every hour as missing.
    """
    try:
        async with conn.transaction():
            added = await store(conn, position_id, symbol, state, rates, received_at, now_s) if rates else 0
            return added, await rows(conn, position_id)
    except asyncpg.PostgresError:
        return 0, None


async def published(market_data_url: str, symbol: str, hours: list[int]) -> tuple[dict[int, dict[str, Any]], float]:
    """Published rates covering ``hours``, and when they were received."""
    async with httpx.AsyncClient(timeout=TIMEOUT_S, trust_env=False) as client:
        response = await client.get(f"{market_data_url}/funding-history/hyperliquid/{symbol}",
                                    params={"start_ms": (min(hours) - 60) * 1000, "end_ms": (max(hours) + 60) * 1000})
    received = time.time()
    response.raise_for_status()
    return funding.published_rates(response.json().get("rows") or []), received


async def price_at(conn, symbol: str, hour: int) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        "SELECT observed_at, oracle_price, mark_price FROM market_open_interest WHERE symbol=$1 "
        "AND observed_at BETWEEN to_timestamp($2) AND to_timestamp($3) "
        "ORDER BY abs(extract(epoch FROM observed_at) - $4) LIMIT 1",
        symbol, hour - PRICE_BEFORE_S, hour + PRICE_AFTER_S, hour)
    if row is None:
        return None
    if row["oracle_price"]:
        return {"value": row["oracle_price"], "source": "market_open_interest.oracle_price", "observed_at": row["observed_at"].timestamp()}
    return {"value": row["mark_price"], "source": "market_open_interest.mark_price", "observed_at": row["observed_at"].timestamp()}


async def store(conn, position_id: uuid.UUID, symbol: str, state: Mapping[str, Any], rates: Mapping[int, Mapping[str, Any]],
                received_at: float, now_s: float) -> int:
    """Insert each settlement not yet stored whose rate and price are recorded; return how many were added."""
    added = 0
    for hour in await outstanding(conn, position_id, state, now_s):
        price = await price_at(conn, symbol, hour) if hour in rates else None
        if price is None:
            continue
        row = funding.settle(state["side"], state["quantity"], hour, rates[hour], price)
        status = await conn.execute(
            "INSERT INTO managed_paper_funding (position_id, settled_at, funding_rate, premium, side, quantity, price, price_source, "
            "price_observed_at, payment_usdc, received_at) VALUES ($1, to_timestamp($2), $3, $4, $5, $6, $7, $8, to_timestamp($9), $10, "
            "to_timestamp($11)) ON CONFLICT DO NOTHING",
            position_id, hour, row["funding_rate"], row["premium"], row["side"], row["quantity"], row["price"], row["price_source"],
            row["price_observed_at"], row["payment_usdc"], received_at)
        added += status.endswith(" 1")
    return added


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).timestamp()
    return value


async def rows(conn, position_id: uuid.UUID) -> list[dict[str, Any]]:
    records = await conn.fetch(
        "SELECT settled_at, funding_rate, premium, side, quantity, price, price_source, price_observed_at, payment_usdc, source, "
        "received_at, recorded_at FROM managed_paper_funding WHERE position_id=$1 ORDER BY settled_at", position_id)
    return [{key: _plain(value) for key, value in dict(record).items()} for record in records]


def register(app, pool) -> None:
    @app.get("/state/paper-positions/{identity}/funding")
    async def position_funding(identity: uuid.UUID):
        async with pool().acquire() as conn:
            state = await conn.fetchval("SELECT position_state FROM managed_paper_positions WHERE id=$1", identity)
            if state is None:
                raise HTTPException(404, "Paper position not found")
            settled = await rows(conn, identity)
        return {"position_id": str(identity), "model": funding.MODEL, "rows": settled, "note": STORE_NOTE}
