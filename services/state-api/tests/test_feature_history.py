"""Feature histories are proxied for charts in seconds, with ids and symbols checked first."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app import feature_history
from app.main import app

client = TestClient(app)


def test_points_become_seconds_and_malformed_rows_are_skipped() -> None:
    raw = [{"ts": 1_789_000_000_000, "value": 0.5}, {"ts": "x", "value": 1}, {"value": 2}, {"ts": 1_789_000_060_999, "value": -1}]
    assert feature_history.to_points(raw) == [[1_789_000_000, 0.5], [1_789_000_060, -1.0]]


def test_the_route_returns_each_requested_series() -> None:
    fetch = AsyncMock(return_value={"hl_return_1h_pct": [{"ts": 1_789_000_000_000, "value": 0.12}]})
    with patch.object(feature_history, "fetch_series", fetch):
        resp = client.get("/state/regime-lab/feature-history?symbol=btc-perp&feature_ids=hl_return_1h_pct,hl_spread_bps")
    body = resp.json()
    assert resp.status_code == 200 and body["symbol"] == "BTC-PERP" and body["authority"] == "display_only"
    assert body["series"] == {"hl_return_1h_pct": [[1_789_000_000, 0.12]], "hl_spread_bps": []}
    assert fetch.await_args.args[2] == ["hl_return_1h_pct", "hl_spread_bps"]


def test_bad_ids_symbols_and_an_unreachable_service_are_refused_plainly() -> None:
    assert client.get("/state/regime-lab/feature-history?feature_ids=../etc").status_code == 400
    assert client.get("/state/regime-lab/feature-history?symbol=BTC&feature_ids=hl_spread_bps").status_code == 400
    with patch.object(feature_history, "fetch_series", AsyncMock(side_effect=httpx.ConnectError("down"))):
        resp = client.get("/state/regime-lab/feature-history?feature_ids=hl_spread_bps")
    assert resp.status_code == 502 and "ConnectError" in resp.json()["detail"]
