"""Slow statistics are served from memory, measured behind the request, one at a time."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app import background
from app import statistics_cache as sc


class Clock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def make_cache(compute, clock, name="demo", **kw):
    return sc.StatisticsCache(name, "The demo reading", compute, "demo_v1", clock=clock, **kw)


def test_a_cold_market_answers_computing_and_is_measured_behind_the_request():
    clock, calls = Clock(), []

    async def compute(pool, symbol):
        calls.append(symbol)
        return {"symbol": symbol, "value": 1}

    async def scenario():
        cache = make_cache(compute, clock)
        status, body = cache.read("pool", "BTC-PERP")
        assert status == 202 and body["status"] == "computing" and body["computed_at"] is None
        assert body["cache"]["refreshing"] is True and "being measured now" in body["note"]
        await cache.ensure_measuring("pool", "BTC-PERP")
        clock.now += 5
        status, body = cache.read("pool", "BTC-PERP")
        assert status == 200 and body["status"] == "ready" and body["value"] == 1
        assert body["computed_at"] == "1970-01-12T13:46:40+00:00" and body["cache"]["age_s"] == 5.0
        assert body["cache"]["stale"] is False and body["cache"]["refreshing"] is False

    asyncio.run(scenario())
    assert calls == ["BTC-PERP"]


def test_concurrent_cold_reads_measure_once():
    clock, calls = Clock(), []

    async def compute(pool, symbol):
        calls.append(symbol)
        await asyncio.sleep(0.01)
        return {"v": 1}

    async def scenario():
        cache = make_cache(compute, clock)
        assert cache.read("pool", None)[0] == 202
        assert cache.read("pool", None)[0] == 202
        await asyncio.gather(*cache._tasks.values())

    asyncio.run(scenario())
    assert calls == [None]


def test_an_expired_entry_is_served_stale_while_it_is_measured_again():
    clock, values = Clock(), iter([1, 2])

    async def compute(pool, symbol):
        return {"v": next(values)}

    async def scenario():
        cache = make_cache(compute, clock, ttl_s=600)
        await cache.refresh("pool", None)
        clock.now += 601
        status, body = cache.read("pool", None)
        assert status == 200 and body["v"] == 1
        assert body["cache"]["stale"] is True and body["cache"]["refreshing"] is True
        await cache.ensure_measuring("pool", None)
        status, body = cache.read("pool", None)
        assert body["v"] == 2 and body["cache"]["stale"] is False

    asyncio.run(scenario())


def test_a_failed_first_measurement_is_a_503_naming_the_error_and_waits_before_retrying():
    clock = Clock()

    async def compute(pool, symbol):
        raise RuntimeError("connection refused")

    async def scenario():
        cache = make_cache(compute, clock)
        assert cache.read("pool", "ETH-PERP")[0] == 202
        await cache.ensure_measuring("pool", "ETH-PERP")
        with pytest.raises(HTTPException) as refused:
            cache.read("pool", "ETH-PERP")
        assert refused.value.status_code == 503 and "connection refused" in refused.value.detail
        clock.now += sc.RETRY_AFTER_S
        assert cache.read("pool", "ETH-PERP")[0] == 202
        await cache.ensure_measuring("pool", "ETH-PERP")

    asyncio.run(scenario())


def test_a_failed_refresh_keeps_the_previous_reading_and_reports_the_error():
    clock, outcomes = Clock(), [{"v": 1}, RuntimeError("timeout")]

    async def compute(pool, symbol):
        item = outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def scenario():
        cache = make_cache(compute, clock)
        await cache.refresh("pool", None)
        clock.now += 700
        await cache.refresh("pool", None)
        status, body = cache.read("pool", None)
        assert status == 200 and body["v"] == 1 and body["cache"]["stale"] is True
        assert "timeout" in body["cache"]["last_error"] and body["cache"]["refreshing"] is False

    asyncio.run(scenario())


def test_the_refresh_loop_keeps_only_recently_requested_markets_warm():
    clock = Clock()

    async def compute(pool, symbol):
        return {"v": symbol}

    async def scenario():
        cache = make_cache(compute, clock, ttl_s=600, keep_warm_s=1800)
        for symbol in ("BTC-PERP", "SOL-PERP"):
            await cache.refresh("pool", symbol)
        cache.entries["BTC-PERP"].requested_at = clock.now
        cache.entries["SOL-PERP"].requested_at = clock.now - 3600
        clock.now += 500
        assert cache.due() == []
        clock.now += 60  # within one refresh period of expiry
        assert cache.due() == ["BTC-PERP"]

    asyncio.run(scenario())


def test_refresh_due_measures_every_due_reading(monkeypatch):
    clock, calls = Clock(), []

    async def compute(pool, symbol):
        calls.append(symbol)
        return {}

    first, second = make_cache(compute, clock), make_cache(compute, clock, name="other")
    first._entry("BTC-PERP").requested_at = clock.now
    second._entry(None).requested_at = clock.now
    monkeypatch.setattr(sc, "_caches", [first, second])
    assert asyncio.run(sc.refresh_due(None)) == []
    assert asyncio.run(sc.refresh_due("pool")) == ["demo:BTC-PERP", "other:all"]
    assert calls == ["BTC-PERP", None]


def test_only_one_measurement_runs_at_a_time_across_readings():
    clock, running, peak = Clock(), [0], [0]

    async def compute(pool, symbol):
        running[0] += 1
        peak[0] = max(peak[0], running[0])
        await asyncio.sleep(0.01)
        running[0] -= 1
        return {}

    async def scenario():
        first, second = make_cache(compute, clock), make_cache(compute, clock, name="other")
        first.read("pool", None)
        second.read("pool", None)
        first.read("pool", "BTC-PERP")
        await asyncio.gather(*first._tasks.values(), *second._tasks.values())

    asyncio.run(scenario())
    assert peak[0] == 1


def test_symbols_are_checked_before_they_become_cache_keys():
    assert sc.checked_symbol(None) is None and sc.checked_symbol("  ") is None
    assert sc.checked_symbol(" btc-perp ") == "BTC-PERP"
    with pytest.raises(HTTPException) as refused:
        sc.checked_symbol("BTC'; drop table")
    assert refused.value.status_code == 400


def test_entries_are_capped_by_dropping_the_least_recently_requested(monkeypatch):
    monkeypatch.setattr(sc, "MAX_ENTRIES", 2)
    clock = Clock()
    cache = make_cache(MagicMock(), clock)
    cache._entry("BTC-PERP").requested_at = clock.now - 10
    cache._entry("ETH-PERP").requested_at = clock.now
    cache._entry("SOL-PERP")
    assert set(cache.entries) == {"ETH-PERP", "SOL-PERP"}


def test_every_reading_shares_one_registered_refresh_loop(monkeypatch):
    monkeypatch.setattr(background, "_factories", [])
    monkeypatch.setattr(sc, "_caches", [])
    state, clock = MagicMock(), Clock()
    sc.register(make_cache(MagicMock(), clock), state)
    sc.register(make_cache(MagicMock(), clock, name="other"), state)
    assert background.registered() == ["outcome_statistics_refresh"]
    assert len(sc._caches) == 2
