"""The timeframe routes measure short-term and daily history on their own clocks, serve charts per horizon, and start Hermes readings."""

from __future__ import annotations

import asyncio
import math
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app import horizon_reading, horizons
from app.main import app

client = TestClient(app)
DAY = 86400


def series(n, step, drift, now=None):
    end = int(now or time.time()) // step * step
    return [{"time": end - (n - 1 - i) * step, "open": c, "high": c * 1.002, "low": c * 0.998, "close": c, "volume": 1000.0}
            for i, c in enumerate(100 * math.exp(drift * i) * (1 + 0.01 * math.sin(i / 5)) for i in range(n))]


def candles_for(url, symbol, part):
    if part == "long":
        return {"1d": series(700, DAY, 0.002)}
    return {"15m": series(900, 900, 0.0003), "1h": series(900, 3600, 0.0006)}


def fresh():
    return patch.multiple(horizons, _cache={}, _candles={}, _backfilled=set(), _locks={}, _refreshing={}, _errors={})


def test_the_page_merges_short_term_and_daily_measurements() -> None:
    fetch = AsyncMock(side_effect=candles_for)
    with fresh(), patch.object(horizons, "fetch_part", fetch), patch.object(horizon_reading, "_memory", {}):
        first = client.get("/state/market/horizons?symbol=btc-perp")
        again = client.get("/state/market/horizons?symbol=BTC-PERP")
    body = first.json()
    assert first.status_code == 200 and body["symbol"] == "BTC-PERP" and body["outlook"]["available"]
    assert [h["key"] for h in body["outlook"]["horizons"]] == ["1h", "4h", "8h", "1d", "3d", "1w", "2w", "1m", "3m", "6m"]
    assert set(body["evaluation"]) == {"1h", "4h", "8h", "1d", "3d", "1w", "2w", "1m", "3m", "6m"}
    assert set(body["computed_at"]) == {"short", "long"} and set(body["outlook"]["history"]) == {"15m", "1h", "1d"}
    assert [b["band"] for b in body["outlook"]["bands"]] == ["short", "lower", "medium", "higher"]
    assert body["readings"]["short"]["status"] == "none" and "weight" in body["evaluation"]["4h"]["features"][0]
    assert again.status_code == 200 and fetch.await_count == 2  # each part measured once, then served from its cache


def test_charts_come_per_horizon_on_its_own_bars_and_bad_input_is_refused() -> None:
    with fresh(), patch.object(horizons, "fetch_part", AsyncMock(side_effect=candles_for)):
        short = client.get("/state/market/horizons/chart?symbol=ETH-PERP&horizon=4h")
        week = client.get("/state/market/horizons/chart?symbol=ETH-PERP&horizon=1w")
        bad_horizon = client.get("/state/market/horizons/chart?symbol=ETH-PERP&horizon=2y")
        bad_symbol = client.get("/state/market/horizons?symbol=../etc")
    assert short.status_code == 200 and short.json()["interval"] == "15m" and len(short.json()["candles"]) == 384
    assert week.status_code == 200 and len(week.json()["candles"]) == 180 and week.json()["projection"]["lines"]
    assert bad_horizon.status_code == 422 and bad_symbol.status_code == 400


def test_an_unreachable_market_data_service_is_a_502_not_a_crash() -> None:
    with fresh(), patch.object(horizons, "fetch_part", AsyncMock(side_effect=httpx.ConnectError("down"))):
        resp = client.get("/state/market/horizons?symbol=SOL-PERP")
    assert resp.status_code == 502 and "ConnectError" in resp.json()["detail"]


def test_refresh_measures_both_parts_now() -> None:
    fetch = AsyncMock(side_effect=candles_for)
    with fresh(), patch.object(horizons, "fetch_part", fetch):
        client.get("/state/market/horizons?symbol=BTC-PERP")
        resp = client.post("/state/market/horizons/refresh?symbol=BTC-PERP")
    assert resp.status_code == 200 and set(resp.json()["computed_at"]) == {"short", "long"} and resp.json()["errors"] == {}
    assert fetch.await_count == 4


def test_a_reading_starts_for_one_band_and_is_kept_with_its_times() -> None:
    with fresh(), patch.object(horizons, "fetch_part", AsyncMock(side_effect=candles_for)), patch.object(horizon_reading, "_memory", {}):
        started = client.post("/state/market/horizons/reading?symbol=BTC-PERP&scope=short")
        page = client.get("/state/market/horizons?symbol=BTC-PERP")
        bad_scope = client.post("/state/market/horizons/reading?symbol=BTC-PERP&scope=weekly")
    assert started.status_code == 200 and started.json()["status"] == "started"
    short = page.json()["readings"]["short"]
    assert short["attempt"]["started_at"] and short["status"] in ("running", "not_configured")
    assert page.json()["readings"]["lower"]["status"] == "none" and bad_scope.status_code == 422


def test_a_chart_is_drawn_once_per_measurement() -> None:
    drawn = MagicMock(wraps=horizons.chart_payload)
    with fresh(), patch.object(horizons, "fetch_part", AsyncMock(side_effect=candles_for)), patch.object(horizons, "chart_payload", drawn):
        first = client.get("/state/market/horizons/chart?symbol=BTC-PERP&horizon=1m")
        again = client.get("/state/market/horizons/chart?symbol=BTC-PERP&horizon=1m")
        other = client.get("/state/market/horizons/chart?symbol=BTC-PERP&horizon=3d")
    assert first.status_code == again.status_code == other.status_code == 200
    assert first.json() == again.json() and drawn.call_count == 2


def measured_after(entry: dict, fetched: list) -> tuple[dict, dict]:
    async def run() -> tuple[dict, dict]:
        served = await horizons.measured("http://market-data", "BTC-PERP", "long")
        for _ in range(100):
            if horizons._cache[("BTC-PERP", "long")].get("tag") == "new":
                break
            await asyncio.sleep(0.01)
        return served, horizons._cache[("BTC-PERP", "long")]

    async def fetch(url, symbol, part):
        fetched.append((symbol, part))
        return {}

    with patch.multiple(horizons, _cache={("BTC-PERP", "long"): entry}, _locks={}, _refreshing={}, _errors={}), \
            patch.object(horizons, "fetch_part", fetch), \
            patch.object(horizons, "_measure", lambda symbol, part, candles: {"at": time.time(), "tag": "new"}):
        return asyncio.run(run())


def test_a_stale_hour_is_served_at_once_and_measured_again_behind_it() -> None:
    fetched: list = []
    served, later = measured_after({"at": time.time() - horizons.PART_TTL_S["long"] - 60, "tag": "old"}, fetched)
    assert served["tag"] == "old" and later["tag"] == "new" and fetched == [("BTC-PERP", "long")]


def test_a_measurement_older_than_its_stale_limit_is_not_served() -> None:
    fetched: list = []
    served, _ = measured_after({"at": time.time() - horizons.SERVE_STALE_S["long"] - 60, "tag": "old"}, fetched)
    assert served["tag"] == "new" and fetched == [("BTC-PERP", "long")]


def test_candles_are_backfilled_once_then_topped_up_with_the_newest_bars() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        start, end = int(request.url.params["start_ms"]) // 1000, int(request.url.params["end_ms"]) // 1000
        step = horizons.INTERVAL_SECONDS[request.url.params["interval"]]
        rows = [{"time": t, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1} for t in range(start // step * step, end, step)]
        return httpx.Response(200, json={"candles": rows})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            now = 1_789_000_200
            first = await horizons.fetch_interval(http, "http://md", "BTC-PERP", "15m", now)
            backfill_requests = len(requests)
            second = await horizons.fetch_interval(http, "http://md", "BTC-PERP", "15m", now + 900)
            return first, second, backfill_requests

    with fresh():
        first, second, backfill_requests = asyncio.run(run())
    assert backfill_requests == math.ceil(horizons.INTRADAY_BARS / horizons.CHUNK_BARS)
    assert len(requests) == backfill_requests + 1 and len(second) >= len(first)
