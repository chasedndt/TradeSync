"""The integration pipeline carries feed heartbeats from market-data and state-api, and still answers when market-data does not."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app import pipeline_feeds
from app.main import app

client = TestClient(app)

REMOTE = {
    "schema_version": "feed_heartbeats_v1", "service": "market-data", "counting_since": "2026-09-15T00:00:00+00:00",
    "feeds": [
        {"id": "bybit_liquidations", "label": "Bybit liquidations stream", "state": "connected", "scoring_influence": False},
        {"id": "a_feed_added_later", "label": "Later", "state": "ok", "scoring_influence": False},
        {"id": "hyperliquid_l2book_2", "label": "Hyperliquid l2Book depth, 2 significant figures", "state": "connected",
         "scoring_influence": False},
        {"label": "no id: dropped"},
    ],
}


def market_data(handler):
    real = httpx.AsyncClient
    return patch.object(pipeline_feeds.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_feeds_are_listed_in_page_order_with_state_api_loops_after_market_data_feeds() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=REMOTE)

    with market_data(handler):
        out = asyncio.run(pipeline_feeds.collect("http://market-data:8080/"))
    assert seen == ["http://market-data:8080/feeds/status"]
    assert [f["id"] for f in out["feeds"]] == ["hyperliquid_l2book_2", "bybit_liquidations", "market_recorder", "horizons_warm",
                                               "a_feed_added_later"]
    assert out["sources"]["market-data"] == {"ok": True, "counting_since": "2026-09-15T00:00:00+00:00", "reason": None}
    assert out["sources"]["state-api"]["ok"] and out["sources"]["state-api"]["counting_since"]
    assert out["schema_version"] == "pipeline_feeds_v1" and all(f["scoring_influence"] is False for f in out["feeds"])


def test_an_unreachable_market_data_leaves_its_feeds_out_and_says_why() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with market_data(refuse):
        out = asyncio.run(pipeline_feeds.collect("http://market-data:8080"))
    source = out["sources"]["market-data"]
    assert source["ok"] is False and source["reason"] == "market-data feed status unavailable (ConnectError)"
    assert [f["id"] for f in out["feeds"]] == ["market_recorder", "horizons_warm"]


def test_the_pipeline_endpoint_carries_the_feeds_beside_its_stages() -> None:
    payload = {"schema_version": "integration_pipeline_status_v1", "execution_authority": False, "nodes": []}
    feeds = {"schema_version": "pipeline_feeds_v1", "generated_at": "2026-09-15T01:00:00+00:00", "sources": {}, "feeds": [], "note": ""}
    with patch("app.main.collect_integration_pipeline", new=AsyncMock(return_value=payload)), \
            patch.object(pipeline_feeds, "collect", new=AsyncMock(return_value=feeds)) as collect:
        response = client.get("/state/integration-pipeline")
    body = response.json()
    assert response.status_code == 200 and body["feeds"] == feeds
    assert body["schema_version"] == "integration_pipeline_status_v1" and body["execution_authority"] is False
    collect.assert_awaited_once()
