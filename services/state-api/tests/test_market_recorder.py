"""One recording pass copies books, open interest and liquidations into Postgres, idempotently."""

from __future__ import annotations

import asyncio

import httpx

from app import market_recorder

T = 1_789_384_697_871


class Conn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list]] = []

    async def executemany(self, sql, rows):
        self.calls.append((sql, list(rows)))

    async def execute(self, sql):
        self.calls.append((sql, []))


class Pool:
    def __init__(self) -> None:
        self.conn = Conn()

    def acquire(self):
        pool = self

        class Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *exc):
                return False

        return Ctx()


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.startswith("/depth-books/"):
        return httpx.Response(200, json={"books": {"2": {"n_sig_figs": 2, "time_ms": T, "stale": False,
                                                           "bids": [[77000.0, 5.0]], "asks": [[78000.0, 2.0]]}}})
    if path.startswith("/liquidation-events/"):
        return httpx.Response(200, json={"events": [{"id": "e1", "source": "bybit", "symbol": "BTC-PERP", "event_time": 100.0,
                                                    "received_at": 100.2, "position_side": "short", "price": 77100.0, "size": 1.0,
                                                    "notional_usd": 77100.0, "price_kind": "bankruptcy"}]})
    if path == "/snapshots":
        return httpx.Response(200, json={"snapshots": [
            {"symbol": "BTC-PERP", "ts": T, "price": {"mark_price_usd": 77743.0}, "oi": {"current_usd": 2.9e9}},
            {"symbol": "DOGE-PERP", "ts": T, "price": {"mark_price_usd": 0.1}, "oi": {"current_usd": 1e6}},
        ]})
    return httpx.Response(404)


def test_a_pass_writes_every_table_with_conflict_guards() -> None:
    pool = Pool()

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://md") as client:
            return await market_recorder.record_once(pool, client, "http://md", ["BTC-PERP"])

    counts = asyncio.run(run())
    assert counts == {"depth": 1, "open_interest": 1, "liquidations": 1}
    tables = [sql.split()[2] for sql, _ in pool.conn.calls]
    assert tables == ["market_depth_snapshots", "market_open_interest", "market_liquidation_events"]
    assert all("ON CONFLICT DO NOTHING" in sql for sql, _ in pool.conn.calls)
    depth_row = pool.conn.calls[0][1][0]
    assert depth_row[4] == "[[77000.0, 5.0]]" and depth_row[5] == "[[78000.0, 2.0]]"


def test_a_market_data_outage_writes_nothing_and_does_not_raise() -> None:
    pool = Pool()

    async def run():
        transport = httpx.MockTransport(lambda request: httpx.Response(503))
        async with httpx.AsyncClient(transport=transport) as client:
            return await market_recorder.record_once(pool, client, "http://md", ["BTC-PERP"])

    assert asyncio.run(run()) == {"depth": 0, "open_interest": 0, "liquidations": 0}
    assert pool.conn.calls == []
