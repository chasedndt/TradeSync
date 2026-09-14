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

from .depth_books import DepthBooks
from .trade_flow import HYPERLIQUID_WS_URL

logger = logging.getLogger(__name__)

RECONNECT_MIN_SECONDS = 2
RECONNECT_MAX_SECONDS = 60
RECEIVE_TIMEOUT_SECONDS = 45


async def run_depth_stream(books: DepthBooks, coins: Iterable[str], n_sig_figs: int, url: str = HYPERLIQUID_WS_URL) -> None:
    coin_list = list(coins)
    delay = RECONNECT_MIN_SECONDS
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, max_size=2**22) as ws:
                for coin in coin_list:
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "subscription": {"type": "l2Book", "coin": coin, "nSigFigs": n_sig_figs},
                    }))
                logger.info(f"Depth stream (nSigFigs={n_sig_figs}) subscribed: {', '.join(coin_list)}")
                delay = RECONNECT_MIN_SECONDS
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=RECEIVE_TIMEOUT_SECONDS)
                    try:
                        message = json.loads(raw)
                    except ValueError:
                        continue
                    books.ingest(n_sig_figs, message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"Depth stream (nSigFigs={n_sig_figs}) disconnected ({type(exc).__name__}); retrying in {delay}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_SECONDS)
