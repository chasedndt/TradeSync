"""Every market-data feed keeps a heartbeat: streams count messages and reconnects, fetches count rows, /feeds/status lists them."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import binance_liquidations, depth_stream, funding_history_route, liquidation_context, liquidity_context, open_interest_history
from app.depth_books import DepthBooks
from app.feed_status_route import router as feed_status_router
from tradesync_core.feed_heartbeat import Heartbeat


class Stop(BaseException):
    """Ends a feed loop from inside its retry sleep."""


async def stop_on_sleep(_seconds):
    raise Stop


def fresh(declared: Heartbeat) -> Heartbeat:
    return Heartbeat(declared.id, label=declared.label, kind=declared.kind, service=declared.service,
                     authority=declared.authority, influence=declared.influence, counts=tuple(declared.snapshot()["counts_1h"]))


class FakeSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent: list[str] = []

    async def send(self, data):
        self.sent.append(data)

    async def recv(self):
        if self.messages:
            return self.messages.pop(0)
        raise ConnectionResetError("closed by peer")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key, value, ex=None):
        self.values[key] = value

    async def eval(self, *args):
        return 1


def test_the_status_route_lists_every_declared_feed_with_no_scoring_influence() -> None:
    app = FastAPI()
    app.include_router(feed_status_router)
    body = TestClient(app).get("/feeds/status").json()
    ids = [f["id"] for f in body["feeds"]]
    assert {"hyperliquid_l2book_2", "hyperliquid_l2book_3", "binance_liquidations", "bybit_liquidations",
            "binance_open_interest_history", "hyperliquid_funding_history", "liquidity_context"} <= set(ids)
    assert len(ids) == len(set(ids)) and all(f["scoring_influence"] is False and f["influence"] for f in body["feeds"])
    assert body["service"] == "market-data" and body["counting_since"] and body["window_seconds"] == 3600


def test_the_depth_stream_counts_stored_books_and_every_reconnect() -> None:
    book = json.dumps({"channel": "l2Book", "data": {"coin": "BTC", "time": 1,
                                                     "levels": [[{"px": "100", "sz": "1", "n": 1}], [{"px": "101", "sz": "2", "n": 1}]]}})
    sockets = [FakeSocket([book, "not json", book]), FakeSocket([book])]
    heartbeat = fresh(depth_stream.HEARTBEATS[3])
    sleeps: list[float] = []

    async def sleep_then_stop(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise Stop

    with patch.dict(depth_stream.HEARTBEATS, {3: heartbeat}), \
            patch.object(depth_stream.websockets, "connect", side_effect=lambda *a, **k: sockets.pop(0)), \
            patch.object(depth_stream.asyncio, "sleep", sleep_then_stop):
        with pytest.raises(Stop):
            asyncio.run(depth_stream.run_depth_stream(DepthBooks(), ["BTC"], 3))
    snap = heartbeat.snapshot()
    assert snap["counts_1h"] == {"messages": 3} and snap["attempts"] == 2 and snap["reconnects"] == 1
    assert snap["state"] == "disconnected" and snap["last_error"] == "ConnectionResetError" and snap["detail"] == {"markets": 1}


def test_the_binance_stream_counts_messages_and_events_and_stops_when_access_is_denied() -> None:
    now_ms = int(time.time() * 1000)
    order = {"e": "forceOrder", "E": now_ms, "o": {"s": "BTCUSDT", "S": "SELL", "ap": "100", "z": "2", "T": now_ms}}
    other = {"e": "forceOrder", "E": now_ms, "o": {"s": "DOGEUSDT", "S": "BUY", "ap": "0.1", "z": "5", "T": now_ms}}
    heartbeat = fresh(binance_liquidations.HEARTBEAT)
    with patch.object(binance_liquidations, "HEARTBEAT", heartbeat), \
            patch.object(binance_liquidations.websockets, "connect", return_value=FakeSocket([json.dumps(order), json.dumps(other)])), \
            patch.object(binance_liquidations.asyncio, "sleep", stop_on_sleep):
        with pytest.raises(Stop):
            asyncio.run(binance_liquidations.run(FakeRedis(), ["BTC-PERP"]))
    snap = heartbeat.snapshot()
    assert snap["counts_1h"] == {"messages": 2, "events": 1} and snap["state"] == "disconnected"

    denied = Exception("HTTP 451")
    denied.response = SimpleNamespace(status_code=451)  # type: ignore[attr-defined]
    heartbeat = fresh(binance_liquidations.HEARTBEAT)
    with patch.object(binance_liquidations, "HEARTBEAT", heartbeat), \
            patch.object(binance_liquidations.websockets, "connect", side_effect=denied):
        asyncio.run(binance_liquidations.run(FakeRedis(), ["BTC-PERP"]))  # returns: never works around a restriction
    assert heartbeat.snapshot()["state"] == "provider_access_denied"


def test_a_rejected_bybit_subscription_is_recorded_and_not_retried() -> None:
    heartbeat = fresh(liquidation_context.HEARTBEAT)
    with patch.object(liquidation_context, "HEARTBEAT", heartbeat), \
            patch.object(liquidation_context.websockets, "connect", return_value=FakeSocket([json.dumps({"op": "subscribe", "success": False})])):
        asyncio.run(liquidation_context.run(FakeRedis()))
    snap = heartbeat.snapshot()
    assert snap["state"] == "subscription_rejected" and snap["counts_1h"]["messages"] == 1 and snap["attempts"] == 1


def test_open_interest_fetches_count_rows_and_record_a_failure_without_its_url() -> None:
    rows = [{"timestamp": 1_789_380_000_000 + i * 3_600_000, "sumOpenInterest": "10", "sumOpenInterestValue": "1000"} for i in range(3)]
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=rows) if "BTCUSDT" in str(request.url) else httpx.Response(503))
    real_client = httpx.AsyncClient
    heartbeat = fresh(open_interest_history.HEARTBEAT)
    with patch.object(open_interest_history, "HEARTBEAT", heartbeat), \
            patch.object(open_interest_history.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw)):
        history = open_interest_history.OpenInterestHistory()
        asyncio.run(history.get("BTC-PERP", "1h"))
        asyncio.run(history.get("BTC-PERP", "1h"))  # served from the cache: not a fetch
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(history.get("ETH-PERP", "1h"))
    snap = heartbeat.snapshot()
    assert snap["counts_1h"] == {"fetches": 1, "rows": 3} and snap["last_success_at"]
    assert snap["state"] == "failed" and snap["last_error"] == "HTTPStatusError (HTTP 503)"


def test_the_funding_route_counts_requests_and_rows_and_names_the_newest_hour() -> None:
    class Provider:
        venue, enabled = "hyperliquid", True

        async def fetch_funding_history(self, symbol, start_ms, end_ms):
            return [{"ts": 1_789_380_000_000, "rate": 0.00001, "premium": -0.0003}, {"ts": 1_789_383_600_000, "rate": 0.00002}]

    providers = [Provider()]
    app = FastAPI()
    app.include_router(funding_history_route.router_for(providers, ["BTC-PERP"]))
    heartbeat = fresh(funding_history_route.HEARTBEAT)
    with patch.object(funding_history_route, "HEARTBEAT", heartbeat):
        client = TestClient(app)
        ok = client.get("/funding-history/hyperliquid/BTC-PERP?start_ms=0")
        providers.clear()
        missing = client.get("/funding-history/hyperliquid/BTC-PERP?start_ms=0")
    assert ok.status_code == 200 and len(ok.json()["rows"]) == 2 and missing.status_code == 503
    snap = heartbeat.snapshot()
    assert snap["counts_1h"] == {"requests": 1, "rows": 2} and snap["detail"]["newest_row_at"] == "2026-09-14T11:00:00+00:00"
    assert snap["state"] == "unavailable" and snap["last_success_at"]


def test_the_liquidity_context_loop_counts_passes_and_keeps_a_partial_failure() -> None:
    async def history(redis, symbol):
        if symbol == "ETH-PERP":
            raise ConnectionError("redis unavailable")
        return {"events": [], "connection": {"state": "connected"}}

    async def no_bars(symbol):
        return []

    heartbeat = fresh(liquidity_context.HEARTBEAT)
    with patch.object(liquidity_context, "HEARTBEAT", heartbeat), \
            patch.object(liquidity_context.liquidation_context, "history", history), \
            patch.object(liquidity_context.binance_liquidations, "history", history), \
            patch.object(liquidity_context.asyncio, "sleep", stop_on_sleep):
        with pytest.raises(Stop):
            asyncio.run(liquidity_context.run(None, ["BTC-PERP", "ETH-PERP"], no_bars))
    snap = heartbeat.snapshot()
    assert snap["state"] == "ok" and snap["counts_1h"] == {"passes": 1, "map_passes": 1}
    assert snap["last_error"] == "ETH-PERP: ConnectionError" and snap["detail"] == {"markets": 2}
