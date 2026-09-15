"""Hyperliquid aggregated order-book websocket subscriber: one connection per aggregation.

Only the transport lives here; ``depth_books`` holds the parsing and the state.
A dropped connection is retried with backoff and never takes the service down.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Iterable

import websockets

from .depth_books import AGGREGATIONS, DepthBooks
from .feed_status import feed
from .trade_flow import HYPERLIQUID_WS_URL

logger = logging.getLogger(__name__)

RECONNECT_MIN_SECONDS = 2
RECONNECT_MAX_SECONDS = 60
RECEIVE_TIMEOUT_SECONDS = 45

# One heartbeat per aggregation, declared at import so the pipeline page lists them before they connect.
HEARTBEATS = {
    n: feed(f"hyperliquid_l2book_{n}", label=f"Hyperliquid l2Book depth, {n} significant figures", kind="websocket",
            authority="display_only",
            influence="Display and context only: the liquidity heatmap's recorded books, and the resting-liquidity balance "
                      "and wall distances, which the feature catalog marks non-scoring.")
    for n in AGGREGATIONS
}


async def run_depth_stream(books: DepthBooks, coins: Iterable[str], n_sig_figs: int, url: str = HYPERLIQUID_WS_URL) -> None:
    coin_list = list(coins)
    heartbeat = HEARTBEATS[n_sig_figs]
    heartbeat.detail["markets"] = len(coin_list)
    delay = RECONNECT_MIN_SECONDS
    while True:
        try:
            heartbeat.connecting()
            async with websockets.connect(url, ping_interval=20, max_size=2**22) as ws:
                for coin in coin_list:
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "subscription": {"type": "l2Book", "coin": coin, "nSigFigs": n_sig_figs},
                    }))
                heartbeat.connected()
                logger.info(f"Depth stream (nSigFigs={n_sig_figs}) subscribed: {', '.join(coin_list)}")
                delay = RECONNECT_MIN_SECONDS
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=RECEIVE_TIMEOUT_SECONDS)
                    try:
                        message = json.loads(raw)
                    except ValueError:
                        continue
                    if books.ingest(n_sig_figs, message):
                        heartbeat.message()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            heartbeat.failed(exc, state="disconnected")
            logger.warning(f"Depth stream (nSigFigs={n_sig_figs}) disconnected ({type(exc).__name__}); retrying in {delay}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_SECONDS)
