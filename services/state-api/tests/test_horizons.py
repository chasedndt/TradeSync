"""The timeframe routes measure daily candles once per hour, serve charts per horizon, and start a Hermes reading."""

from __future__ import annotations

import asyncio
import math
import time
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import horizon_reading, horizons
from app.main import app

client = TestClient(app)
DAY = 86400


def daily(n=700):
    return [{"time": 1_600_000_000 + i * DAY, "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1000.0}
            for i, c in enumerate(100 * math.exp(0.002 * i) * (1 + 0.03 * math.sin(i / 5)) for i in range(n))]


def fresh_cache():
    return patch.object(horizons, "_cache", {})


def test_the_page_payload_carries_outlook_evaluation_and_feature_list() -> None:
    fetch = AsyncMock(return_value=daily())
    with fresh_cache(), patch.object(horizons, "fetch_daily", fetch):
        first = client.get("/state/market/horizons?symbol=btc-perp")
        again = client.get("/state/market/horizons?symbol=BTC-PERP")
    body = first.json()
    assert first.status_code == 200 and body["symbol"] == "BTC-PERP" and body["outlook"]["available"]
    assert set(body["evaluation"]) == {"3d", "1w", "2w", "1m", "3m", "6m"}
    assert [f["key"] for f in body["features"]][:2] == ["trend", "momentum"] and body["reading"]["status"] == "none"
    assert again.status_code == 200 and fetch.await_count == 1  # measured once, then served from the hour's cache


def test_charts_come_per_horizon_and_bad_input_is_refused() -> None:
    with fresh_cache(), patch.object(horizons, "fetch_daily", AsyncMock(return_value=daily())):
        chart = client.get("/state/market/horizons/chart?symbol=ETH-PERP&horizon=1w")
        bad_horizon = client.get("/state/market/horizons/chart?symbol=ETH-PERP&horizon=2y")
        bad_symbol = client.get("/state/market/horizons?symbol=../etc")
    assert chart.status_code == 200 and len(chart.json()["candles"]) == 180 and chart.json()["projection"]["lines"]
    assert bad_horizon.status_code == 422 and bad_symbol.status_code == 400


def test_an_unreachable_market_data_service_is_a_502_not_a_crash() -> None:
    import httpx

    with fresh_cache(), patch.object(horizons, "fetch_daily", AsyncMock(side_effect=httpx.ConnectError("down"))):
        resp = client.get("/state/market/horizons?symbol=SOL-PERP")
    assert resp.status_code == 502 and "ConnectError" in resp.json()["detail"]


def test_a_reading_starts_in_the_background() -> None:
    run = AsyncMock()
    with fresh_cache(), patch.object(horizons, "fetch_daily", AsyncMock(return_value=daily())), \
            patch.object(horizon_reading, "run_reading", run), patch.object(horizon_reading, "_jobs", {}):
        resp = client.post("/state/market/horizons/reading?symbol=BTC-PERP")
    assert resp.status_code == 200 and resp.json()["status"] == "started"
    assert run.await_count == 1 and run.await_args.args[0] == "BTC-PERP"


def test_a_chart_is_drawn_once_per_measurement() -> None:
    drawn = MagicMock(wraps=horizons.chart_payload)
    with fresh_cache(), patch.object(horizons, "fetch_daily", AsyncMock(return_value=daily())), \
            patch.object(horizons, "chart_payload", drawn):
        first = client.get("/state/market/horizons/chart?symbol=BTC-PERP&horizon=1m")
        again = client.get("/state/market/horizons/chart?symbol=BTC-PERP&horizon=1m")
        other = client.get("/state/market/horizons/chart?symbol=BTC-PERP&horizon=3d")
    assert first.status_code == again.status_code == other.status_code == 200
    assert first.json() == again.json() and drawn.call_count == 2


def measured_after(entry: dict, fetched: list) -> tuple[dict, dict]:
    async def run() -> tuple[dict, dict]:
        served = await horizons.measured("http://market-data", "BTC-PERP")
        for _ in range(100):
            if horizons._cache["BTC-PERP"].get("tag") == "new":
                break
            await asyncio.sleep(0.01)
        return served, horizons._cache["BTC-PERP"]

    async def fetch(url, symbol):
        fetched.append(symbol)
        return []

    with patch.object(horizons, "_cache", {"BTC-PERP": entry}), patch.object(horizons, "_locks", {}), \
            patch.object(horizons, "_refreshing", {}), patch.object(horizons, "fetch_daily", fetch), \
            patch.object(horizons, "_measure", lambda symbol, candles: {"at": time.time(), "tag": "new"}):
        return asyncio.run(run())


def test_a_stale_hour_is_served_at_once_and_measured_again_behind_it() -> None:
    fetched: list = []
    served, later = measured_after({"at": time.time() - horizons.CACHE_TTL_S - 60, "tag": "old"}, fetched)
    assert served["tag"] == "old" and later["tag"] == "new" and fetched == ["BTC-PERP"]


def test_a_measurement_older_than_six_hours_is_not_served() -> None:
    fetched: list = []
    served, _ = measured_after({"at": time.time() - horizons.SERVE_STALE_S - 60, "tag": "old"}, fetched)
    assert served["tag"] == "new" and fetched == ["BTC-PERP"]
