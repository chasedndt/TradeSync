"""Feed heartbeats for the integration pipeline page: the streams, fetches and loops added on 14 September.

Market-data counts its own feeds in memory and serves them at ``/feeds/status``:
Hyperliquid l2Book depth at 2 and 3 significant figures, the Binance USD-M and
Bybit liquidation streams, the Binance open-interest history fetch, the
Hyperliquid funding-history route and the liquidity context loop. State-api
adds its own two loops, the market history recorder and the Timeframes warm
loop. Each feed says whether it is connected, when it last delivered, what it
counted in the last hour, how often it reconnected, its last error, and what its
data is used for. A heartbeat is evidence about transport: it changes no
pipeline stage's status and no Tier A readiness.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.feed_heartbeats import REGISTRY
from tradesync_core.feed_heartbeat import describe_error, iso

# The order the page lists them in; a feed market-data adds later is listed after these.
ORDER = ("hyperliquid_l2book_2", "hyperliquid_l2book_3", "binance_liquidations", "bybit_liquidations",
         "binance_open_interest_history", "hyperliquid_funding_history", "liquidity_context", "market_recorder", "horizons_warm")
TIMEOUT_S = 3.0
NOTE = ("Counted in memory by each service since it started, so a restart resets the counts. Every feed here is context: "
        "none carries a scoring weight, and a heartbeat changes no stage's status.")


async def market_data_feeds(market_data_url: str, timeout: float = TIMEOUT_S) -> dict[str, Any]:
    """Market-data's heartbeats, or the reason they could not be read."""
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.get(f"{market_data_url.rstrip('/')}/feeds/status")
            response.raise_for_status()
            body = response.json()
        feeds = [f for f in body.get("feeds") or [] if isinstance(f, dict) and f.get("id")]
        return {"ok": True, "counting_since": body.get("counting_since"), "reason": None, "feeds": feeds}
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        return {"ok": False, "counting_since": None, "reason": f"market-data feed status unavailable ({describe_error(exc)})", "feeds": []}


def _rank(feed: dict[str, Any]) -> tuple[int, str]:
    feed_id = str(feed.get("id"))
    return (ORDER.index(feed_id) if feed_id in ORDER else len(ORDER), feed_id)


async def collect(market_data_url: str) -> dict[str, Any]:
    now = time.time()
    remote = await market_data_feeds(market_data_url)
    local = REGISTRY.snapshot(now)
    return {
        "schema_version": "pipeline_feeds_v1",
        "generated_at": iso(now),
        "sources": {
            "market-data": {"ok": remote["ok"], "counting_since": remote["counting_since"], "reason": remote["reason"]},
            "state-api": {"ok": True, "counting_since": local["counting_since"], "reason": None},
        },
        "feeds": sorted(remote["feeds"] + local["feeds"], key=_rank),
        "note": NOTE,
    }
