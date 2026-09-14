"""The liquidity routes build the heatmap from recorded books, estimate the liquidation map from open interest, and refuse bad input."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import liquidity
from app.main import app, state

client = TestClient(app)


class Pool:
    """Stands in for the asyncpg pool; the routes only need acquire()."""

    def acquire(self):
        class Ctx:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, *exc):
                return False

        return Ctx()


def test_the_heatmap_is_built_from_recorded_books() -> None:
    now = int(time.time())
    rows = [{"observed_at": datetime.fromtimestamp(now - 120, timezone.utc), "mid_price": 100.0,
             "bids": [[99.0, 10.0], [96.0, 50.0]], "asks": [[101.0, 5.0]]}]
    with patch.object(state, "pool", Pool()), \
            patch.object(liquidity, "depth_rows", AsyncMock(return_value=(rows, datetime.fromtimestamp(now - 3600, timezone.utc)))):
        resp = client.get("/state/market/liquidity-heatmap?symbol=btc-perp&window=6h")
        bad = client.get("/state/market/liquidity-heatmap?symbol=BTC-PERP&window=2y")
    body = resp.json()
    assert resp.status_code == 200 and body["symbol"] == "BTC-PERP" and body["n_sig_figs"] == 3
    assert body["bids"] and body["asks"] and body["latest"]["walls"]["below"]["price"] == 96.0
    assert body["recording_since"] and bad.status_code == 422


def test_the_liquidation_map_needs_open_interest_history() -> None:
    from tradesync_core.liquidation_map import Bar

    bars = [Bar(i * 3600, 101 + (i % 3), 99 - (i % 2), 100, 1_000_000 + 50_000 * i) for i in range(60)]
    with patch.object(liquidity, "_map_cache", {}), patch.object(liquidity, "map_bars", AsyncMock(return_value=bars)):
        resp = client.get("/state/market/liquidation-map?symbol=ETH-PERP&window=7d")
    body = resp.json()
    assert resp.status_code == 200 and body["interval"] == "1h" and body["cells"] and body["profile"]["long"]
    assert body["authority"] == "context_only" and "estimate" in body["note"].lower()
    with patch.object(liquidity, "_map_cache", {}), patch.object(liquidity, "map_bars", AsyncMock(return_value=bars[:5])):
        thin = client.get("/state/market/liquidation-map?symbol=PUMP-PERP&window=7d")
    assert thin.status_code == 409
