"""The timeframe routes measure daily candles once per hour, serve charts per horizon, and start a Hermes reading."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

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
