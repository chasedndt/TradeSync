"""Record market history once a minute: aggregated order books, open interest, received liquidations.

Market-data holds these in memory or a bounded Redis window; the liquidity
heatmap, the estimated liquidation map and the timeframe records need weeks of
them, so this loop copies them into Postgres (``ops/migrations/029``). Every
row is keyed by minute, so a repeated pass inserts nothing twice, and an hourly
pass downsamples older rows (``tradesync_core.market_history``).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from app import background, editions
from tradesync_core.market_history import RETENTION_SQL, depth_rows, liquidation_rows, open_interest_row

RECORD_EVERY_S = 60
RETENTION_EVERY_S = 3600

_status: dict[str, Any] = {"passes": 0, "last_pass_at": None, "last_error": None, "rows": {}}


def status() -> dict[str, Any]:
    return dict(_status)


async def _get(client: httpx.AsyncClient, url: str) -> Any:
    response = await client.get(url)
    response.raise_for_status()
    return response.json()


async def record_once(pool, client: httpx.AsyncClient, market_data_url: str, symbols: list[str]) -> dict[str, int]:
    depth: list[tuple[Any, ...]] = []
    liquidations: list[tuple[Any, ...]] = []
    for symbol in symbols:
        try:
            depth += depth_rows(symbol, (await _get(client, f"{market_data_url}/depth-books/{symbol}")).get("books") or {})
        except (httpx.HTTPError, ValueError):
            pass
        try:
            liquidations += liquidation_rows((await _get(client, f"{market_data_url}/liquidation-events/{symbol}")).get("events") or [])
        except (httpx.HTTPError, ValueError):
            pass
    open_interest: list[tuple[Any, ...]] = []
    try:
        payload = await _get(client, f"{market_data_url}/snapshots")
        snapshots = payload.get("snapshots") if isinstance(payload, dict) else payload
        open_interest = [row for row in (open_interest_row(s) for s in snapshots or [] if s.get("symbol") in symbols) if row]
    except (httpx.HTTPError, ValueError, AttributeError):
        pass

    async with pool.acquire() as conn:
        if depth:
            await conn.executemany(
                "INSERT INTO market_depth_snapshots (symbol, n_sig_figs, observed_at, mid_price, bids, asks) "
                "VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb) ON CONFLICT DO NOTHING",
                [(s, n, at, mid, json.dumps(b), json.dumps(a)) for s, n, at, mid, b, a in depth],
            )
        if open_interest:
            await conn.executemany(
                "INSERT INTO market_open_interest (symbol, observed_at, open_interest_usd, mark_price, oracle_price, "
                "funding_rate, oracle_premium_bps, volume_24h_usd) VALUES ($1, $2, $3, $4, $5, $6, $7, $8) ON CONFLICT DO NOTHING",
                open_interest,
            )
        if liquidations:
            await conn.executemany(
                "INSERT INTO market_liquidation_events (source, event_id, symbol, event_time, position_side, price, size, "
                "notional_usd, price_kind, received_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) ON CONFLICT DO NOTHING",
                liquidations,
            )
    return {"depth": len(depth), "open_interest": len(open_interest), "liquidations": len(liquidations)}


async def apply_retention(pool) -> None:
    async with pool.acquire() as conn:
        for statement in RETENTION_SQL:
            await conn.execute(statement)


def register(app, state, *, market_data_url: str) -> None:
    async def run() -> None:
        await asyncio.sleep(30)  # let market-data's streams fill first
        last_retention = 0.0
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            while True:
                started = time.monotonic()
                try:
                    if state.pool:
                        symbols = await editions.tracked_symbols(market_data_url)
                        _status["rows"] = await record_once(state.pool, client, market_data_url, symbols)
                        _status.update(passes=_status["passes"] + 1, last_pass_at=time.time(), last_error=None)
                        if time.time() - last_retention > RETENTION_EVERY_S:
                            await apply_retention(state.pool)
                            last_retention = time.time()
                except Exception as exc:  # the next pass tries again
                    _status["last_error"] = type(exc).__name__
                    print(f"[MarketRecorder] pass failed: {type(exc).__name__}")
                await asyncio.sleep(max(5.0, RECORD_EVERY_S - (time.monotonic() - started)))

    background.add("market_recorder", run)
