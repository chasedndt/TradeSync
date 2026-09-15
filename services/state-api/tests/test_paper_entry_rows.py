"""Entry evidence rows from TradeSync's own tables: a liquidation cap is stated in the evidence, never hidden."""

import asyncio
import time

from app import paper_entry_rows
from paper_fakes import SYMBOL, FakeConn, utc


def liquidation(index, now):
    return {"source": "binance", "event_id": f"e{index}", "event_time": utc(now - 60 - index), "received_at": utc(now - 59 - index),
            "position_side": "long", "price": 50.0, "size": 1.0, "notional_usd": 50.0, "price_kind": "average_fill"}


def test_more_liquidations_than_the_cap_are_marked_truncated():
    now, cap, asked = time.time(), paper_entry_rows.LIQUIDATION_ROWS, {}

    def rows(symbol, since, until, limit):
        asked["limit"] = limit
        return [liquidation(i, now) for i in range(min(limit, cap + 7))]

    item = asyncio.run(paper_entry_rows.liquidations(FakeConn([("FROM market_liquidation_events", rows)]), SYMBOL, now))
    assert asked["limit"] == cap + 1
    assert len(item["records"]) == cap and item["truncated"] is True
    assert item["coverage"].startswith(f"More than {cap} liquidations were received")


def test_an_hour_under_the_cap_keeps_every_row_unmarked():
    now = time.time()
    conn = FakeConn([("FROM market_liquidation_events", lambda *args: [liquidation(i, now) for i in range(3)])])
    item = asyncio.run(paper_entry_rows.liquidations(conn, SYMBOL, now))
    assert item["truncated"] is False and len(item["records"]) == 3
    assert not item["coverage"].startswith("More than")
