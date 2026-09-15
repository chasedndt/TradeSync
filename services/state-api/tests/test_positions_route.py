"""GET /state/positions accepts its own default venue, "all", and refuses an unknown venue as the caller's error.

On 15 September the Cockpit's Positions page asked for venue=all and received 500:
the venue was normalised before "all" was recognised.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class FakeExecClient:
    calls: list[str] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def get(self, url, timeout=None):
        FakeExecClient.calls.append(url)
        return httpx.Response(200, json=[], request=httpx.Request("GET", url))


def test_all_venues_default_and_short_name_read_hyperliquid_positions() -> None:
    FakeExecClient.calls = []
    with patch("app.main.httpx.AsyncClient", FakeExecClient):
        for path in ("/state/positions?venue=all", "/state/positions", "/state/positions?venue=hl"):
            response = client.get(path)
            assert response.status_code == 200 and response.json() == [], path
    assert FakeExecClient.calls == ["http://exec-hl-svc:8004/exec/hl/positions"] * 3


def test_an_unknown_venue_is_refused_as_a_bad_request() -> None:
    with patch("app.main.httpx.AsyncClient", FakeExecClient):
        response = client.get("/state/positions?venue=binance")
    assert response.status_code == 400 and "Unsupported venue" in response.json()["detail"]
