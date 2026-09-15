"""The market history recorder and the Timeframes warm loop keep what each pass did on their heartbeats."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx

from app import editions, horizons, horizons_warm, market_recorder
from tradesync_core.feed_heartbeat import Heartbeat


def fresh(declared: Heartbeat) -> Heartbeat:
    return Heartbeat(declared.id, label=declared.label, kind=declared.kind, service=declared.service,
                     authority=declared.authority, influence=declared.influence, counts=tuple(declared.snapshot()["counts_1h"]))


def test_a_recording_pass_counts_its_rows_and_waits_without_a_database() -> None:
    heartbeat = fresh(market_recorder.HEARTBEAT)
    rows = {"depth": 20, "open_interest": 10, "liquidations": 3}
    with patch.object(market_recorder, "HEARTBEAT", heartbeat), \
            patch.object(editions, "tracked_symbols", AsyncMock(return_value=["BTC-PERP", "ETH-PERP"])), \
            patch.object(market_recorder, "record_once", AsyncMock(return_value=rows)):
        assert asyncio.run(market_recorder.record_pass(object(), None, "http://md")) == rows
    snap = heartbeat.snapshot()
    assert snap["state"] == "ok" and snap["counts_1h"] == {"passes": 1, "rows": 33}
    assert snap["detail"] == {"markets": 2, "rows_last_pass": rows} and snap["last_success_at"]

    with patch.object(market_recorder, "HEARTBEAT", heartbeat):
        assert asyncio.run(market_recorder.record_pass(None, None, "http://md")) is None
    snap = heartbeat.snapshot()
    assert snap["state"] == "waiting" and snap["last_error"] == "the database pool is not ready" and not snap["connected"]


def test_a_pass_with_no_tracked_markets_is_not_reported_as_recording() -> None:
    heartbeat = fresh(market_recorder.HEARTBEAT)
    empty = {"depth": 0, "open_interest": 0, "liquidations": 0}
    with patch.object(market_recorder, "HEARTBEAT", heartbeat), \
            patch.object(editions, "tracked_symbols", AsyncMock(return_value=[])), \
            patch.object(market_recorder, "record_once", AsyncMock(return_value=empty)):
        asyncio.run(market_recorder.record_pass(object(), None, "http://md"))
    snap = heartbeat.snapshot()
    assert snap["state"] == "waiting" and snap["counts_1h"] == {"passes": 0, "rows": 0}
    assert snap["last_error"] == "market-data listed no markets to record"


def test_a_warm_pass_measures_only_expiring_parts_and_keeps_their_times() -> None:
    heartbeat = fresh(horizons_warm.HEARTBEAT)
    calls: list[tuple[str, str]] = []

    async def measured(url, symbol, part, force=False):
        calls.append((symbol, part))
        if (symbol, part) == ("ETH-PERP", "long"):
            raise httpx.ConnectError("market-data unreachable")
        horizons._cache[(symbol, part)] = {"at": time.time()}
        return horizons._cache[(symbol, part)]

    with patch.multiple(horizons, _cache={}), patch.object(horizons, "measured", measured), \
            patch.object(horizons_warm, "HEARTBEAT", heartbeat):
        asyncio.run(horizons_warm.warm_pass("http://md"))
        first = heartbeat.snapshot()
        asyncio.run(horizons_warm.warm_pass("http://md"))  # only the part that failed is due again
        second = heartbeat.snapshot()
    assert calls == [("BTC-PERP", "short"), ("BTC-PERP", "long"), ("ETH-PERP", "short"), ("ETH-PERP", "long"), ("ETH-PERP", "long")]
    assert first["state"] == "ok" and first["counts_1h"] == {"passes": 1, "measurements": 3}
    assert first["last_error"] == "ETH-PERP long: ConnectError"
    assert set(first["detail"]["measured_at"]) == {"BTC-PERP short", "BTC-PERP long", "ETH-PERP short"}
    assert second["state"] == "failed" and second["counts_1h"] == {"passes": 1, "measurements": 3}
