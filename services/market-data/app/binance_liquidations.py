"""Binance USDT-M received liquidations, context only; never Hyperliquid and never authority.

Stream: ``wss://fstream.binance.com/ws/!forceOrder@arr`` (public, no key).
Binance pushes at most the latest liquidation order per symbol each second, so
the received events undercount bursts. ``S`` is the liquidation ORDER side:
SELL closes a long, BUY closes a short. Notional is average fill price times
filled quantity.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from typing import Any, Iterable

import websockets

from .liquidation_context import STORE_RECEIPT

URL = "wss://fstream.binance.com/ws/!forceOrder@arr"
STATUS = "market:binance-liquidations:status"
PREFIX = "market:binance-liquidations:received-v1:"


def symbol_map(symbols: Iterable[str]) -> dict[str, str]:
    """``BTC-PERP`` → ``BTCUSDT``; a market Binance does not list simply never receives events."""
    return {f"{s.replace('-PERP', '')}USDT": s for s in symbols}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def normalize(message: Any, received_at: float, markets: dict[str, str]) -> list[dict[str, Any]]:
    payloads = message if isinstance(message, list) else [message]
    events: list[dict[str, Any]] = []
    for payload in payloads:
        order = payload.get("o") if isinstance(payload, dict) and payload.get("e") == "forceOrder" else None
        if not isinstance(order, dict) or order.get("S") not in ("BUY", "SELL"):
            continue
        symbol = markets.get(str(order.get("s")))
        price = _number(order.get("ap")) or _number(order.get("p"))
        size = _number(order.get("z")) or _number(order.get("q"))
        try:
            event_ms = int(order.get("T") or payload.get("E"))
        except (TypeError, ValueError):
            continue
        if symbol is None or price is None or size is None:
            continue
        if not 0 <= received_at * 1000 - event_ms <= 3_600_000:
            continue
        identity = json.dumps([order.get("s"), event_ms, order.get("S"), order.get("z"), order.get("ap")], sort_keys=True)
        events.append({
            "id": hashlib.sha256(identity.encode()).hexdigest(),
            "source": "binance", "symbol": symbol, "event_time": event_ms / 1000, "received_at": received_at,
            "position_side": "long" if order["S"] == "SELL" else "short",
            "size": size, "price": price, "notional_usd": price * size, "authority": "context_only",
        })
    return events


async def run(redis, symbols: Iterable[str]) -> None:
    markets = symbol_map(symbols)

    async def status(state: str, **extra: Any) -> None:
        await redis.set(STATUS, json.dumps({"state": state, "updated_at": time.time(), **extra}), ex=300)

    delay = 5
    while True:
        try:
            await status("connecting")
            async with websockets.connect(URL, open_timeout=10, max_size=2**20, ping_interval=60) as ws:
                await status("connected", subscribed_at=time.time())
                delay = 5
                last_status = time.monotonic()
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=120)
                    except asyncio.TimeoutError:
                        await status("connected", subscribed_at=time.time(), note="no liquidation in the last two minutes")
                        continue
                    now = time.time()
                    try:
                        message = json.loads(raw)
                    except ValueError:
                        continue
                    for event in normalize(message, now, markets):
                        key = PREFIX + event["symbol"]
                        await redis.eval(STORE_RECEIPT, 2, key, key + ":payloads", event["id"],
                                         event["event_time"], json.dumps(event, sort_keys=True), now - 3600)
                    if time.monotonic() - last_status > 30:
                        await status("connected", subscribed_at=time.time())
                        last_status = time.monotonic()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            code = getattr(getattr(exc, "response", None), "status_code", getattr(exc, "status_code", None))
            if code in (401, 403, 451):
                await redis.set(STATUS, json.dumps({"state": "provider_access_denied", "http_status": code, "updated_at": time.time()}), ex=86400)
                return  # never work around a regional or access restriction
            try:
                await status("disconnected", error_type=type(exc).__name__)
            except Exception:
                pass
            await asyncio.sleep(delay)
            delay = min(delay * 2, 300)


async def history(redis, symbol: str) -> dict[str, Any]:
    raw_status = await redis.get(STATUS)
    state = json.loads(raw_status) if raw_status else {"state": "unavailable"}
    identities = await redis.zrangebyscore(PREFIX + symbol, time.time() - 3600, "+inf")
    rows = await redis.hmget(PREFIX + symbol + ":payloads", identities) if identities else []
    events = sorted((json.loads(r) for r in rows if r), key=lambda r: r["event_time"], reverse=True)
    return {"venue": "binance", "symbol": symbol, "connection": state, "events": events}
