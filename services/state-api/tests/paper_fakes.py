"""In-memory stand-ins for the paper position routes: a database connection and market-data over HTTP.

``FakeConn`` answers SQL by the first handler whose needle appears in the statement
and keeps a small funding table, so settlements inserted by a route can be read back.
``FakeMarket`` replaces ``httpx.AsyncClient`` and answers by URL substring.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx

H = 3600
SYMBOL = "HYPE-PERP"
UNIVERSE = ["BTC-PERP", SYMBOL, "ZEC-PERP"]


def utc(seconds: float) -> datetime:
    return datetime.fromtimestamp(seconds, timezone.utc)


class FakeConn:
    def __init__(self, handlers):
        self.handlers = list(handlers)
        self.executed: list[tuple[str, tuple]] = []
        self.funding: list[dict] = []

    def _answer(self, sql, args):
        for needle, handler in self.handlers:
            if needle in sql:
                return handler(*args) if callable(handler) else handler
        raise AssertionError(f"unexpected statement: {sql[:120]}")

    async def fetchval(self, sql, *args, timeout=None):
        return self._answer(sql, args)

    async def fetchrow(self, sql, *args, timeout=None):
        return self._answer(sql, args)

    async def fetch(self, sql, *args, timeout=None):
        if "extract(epoch FROM settled_at)::bigint AS hour FROM managed_paper_funding" in sql:
            return [{"hour": int(row["settled_at"].timestamp())} for row in self.funding if row["position_id"] == args[0]]
        if "FROM managed_paper_funding WHERE position_id" in sql:
            return [{k: v for k, v in row.items() if k != "position_id"} for row in self.funding if row["position_id"] == args[0]]
        return self._answer(sql, args)

    async def execute(self, sql, *args, timeout=None):
        self.executed.append((sql, args))
        if "INSERT INTO managed_paper_funding" in sql:
            keys = ("position_id", "settled_at", "funding_rate", "premium", "side", "quantity", "price", "price_source",
                    "price_observed_at", "payment_usdc", "received_at")
            row = dict(zip(keys, args))
            for key in ("settled_at", "price_observed_at", "received_at"):
                row[key] = utc(row[key])
            if any(r["position_id"] == row["position_id"] and r["settled_at"] == row["settled_at"] for r in self.funding):
                return "INSERT 0 0"
            self.funding.append({**row, "source": "hyperliquid_funding_history", "recorded_at": utc(time.time())})
            return "INSERT 0 1"
        return "OK"

    def transaction(self):
        conn = self

        class Transaction:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return Transaction()

    def statements(self, needle):
        return [args for sql, args in self.executed if needle in sql]


def pool_of(conn):
    @asynccontextmanager
    async def acquire():
        yield conn

    return SimpleNamespace(acquire=acquire)


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://fake")
            raise httpx.HTTPStatusError("fake", request=request, response=httpx.Response(self.status_code, request=request))


class FakeMarket:
    """Replaces ``httpx.AsyncClient``; ``routes`` maps a URL substring to ``answer(url, params) -> (status, body)``."""

    routes: list = []
    requested: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, timeout=None):
        FakeMarket.requested.append(url)
        for needle, answer in FakeMarket.routes:
            if needle in url:
                return FakeResponse(*answer(url, params))
        return FakeResponse(404, {"error": "not_found"})


def book(now, bid=49.99, ask=50.01, size=400.0):
    step = 0.01
    return {"venue": "hyperliquid", "symbol": SYMBOL, "poll_ts": int(now * 1000), "best_bid": bid, "best_ask": ask,
            "mid_price": (bid + ask) / 2, "spread_bps": (ask - bid) / ((ask + bid) / 2) * 1e4, "imbalance_1pct": 0.1,
            "depth": {"bid_1pct_usd": 100000.0, "ask_1pct_usd": 90000.0},
            "bids": [{"price": round(bid - i * step, 2), "size": size} for i in range(10)],
            "asks": [{"price": round(ask + i * step, 2), "size": size} for i in range(10)],
            "walls": [{"side": "bid", "price": 49.9, "notional_usd": 20000.0, "share_of_side": 0.2}], "authority": "display_only"}


def hourly_candles(now, count=100, price=50.0, half_range=0.25):
    last = int(now // H) * H - H
    return {"candles": [{"time": last - (count - 1 - i) * H, "open": price, "high": price + half_range, "low": price - half_range,
                         "close": price, "volume": 10.0} for i in range(count)], "count": count}


def market_routes(clock=time.time):
    """market-data answers for ``SYMBOL``: a tight book, quiet hourly candles and three settled funding hours."""
    def funding_rows(url, params):
        now = clock()
        return 200, {"rows": [[int(now // H) * H - k * H, 1.25e-05, -1e-4] for k in (2, 1, 0)]}

    return [
        ("/snapshots", lambda url, params: (200, {"snapshots": [{"symbol": s, "venue": "hyperliquid"} for s in UNIVERSE]})),
        (f"/depth/hyperliquid/{SYMBOL}", lambda url, params: (200, book(clock()))),
        (f"/candles/hyperliquid/{SYMBOL}", lambda url, params: (200, hourly_candles(clock()))),
        (f"/features/hyperliquid/{SYMBOL}", lambda url, params: (200, {"observations": [
            {"feature_id": "hl_spread_bps", "value": 4.0, "timeframe": "snapshot", "observed_at_ms": int((clock() - 30) * 1000),
             "source_event_id": "snapshot:spread"},
            {"feature_id": "hl_return_1h_pct", "value": -0.4, "timeframe": "snapshot", "observed_at_ms": int((clock() + 60) * 1000),
             "source_event_id": "snapshot:return"}]})),
        (f"/funding-history/hyperliquid/{SYMBOL}", funding_rows),
        (f"/liquidation-context/{SYMBOL}", lambda url, params: (200, {"symbol": SYMBOL, "venue": "bybit", "receipt_schema": "first-received-v2", "events": []})),
        (f"/book-history/{SYMBOL}", lambda url, params: (200, {"venue": "hyperliquid", "symbol": SYMBOL, "samples": []})),
        ("/state/market/horizons", lambda url, params: (503, {"detail": "measuring"})),
    ]
