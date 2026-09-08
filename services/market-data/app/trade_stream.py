"""Hyperliquid trade websocket subscriber.

Kept apart from ``trade_flow`` so the accumulation mathematics stays pure and
testable, and only the transport lives here.

The subscriber is deliberately quiet about its own failures in one respect: a
dropped connection is retried with backoff and does not take the service down,
because CVD is one feature among many and market-data must keep serving the
rest. What it must never do is present a stale window as current, so the
tracker reports None until trades are actually observed again.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Iterable

import websockets

from .trade_flow import HYPERLIQUID_WS_URL, TradeFlowTracker

logger = logging.getLogger(__name__)

RECONNECT_MIN_SECONDS = 2
RECONNECT_MAX_SECONDS = 60
RECEIVE_TIMEOUT_SECONDS = 45


async def run_trade_stream(
    tracker: TradeFlowTracker,
    coins: Iterable[str],
    url: str = HYPERLIQUID_WS_URL,
) -> None:
    """Subscribe to taker trades and feed the tracker until cancelled."""

    coin_list = list(coins)
    delay = RECONNECT_MIN_SECONDS

    while True:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                for coin in coin_list:
                    await ws.send(
                        json.dumps(
                            {
                                "method": "subscribe",
                                "subscription": {"type": "trades", "coin": coin},
                            }
                        )
                    )
                logger.info(f"Trade stream subscribed: {', '.join(coin_list)}")
                delay = RECONNECT_MIN_SECONDS

                while True:
                    raw = await asyncio.wait_for(
                        ws.recv(), timeout=RECEIVE_TIMEOUT_SECONDS
                    )
                    try:
                        message = json.loads(raw)
                    except ValueError:
                        continue
                    if message.get("channel") != "trades":
                        continue
                    data = message.get("data")
                    if isinstance(data, list):
                        tracker.ingest(data)

        except asyncio.CancelledError:
            logger.info("Trade stream stopping")
            raise
        except Exception as exc:
            # Backoff rather than a tight reconnect loop: the venue rate-limits,
            # and a hot loop would turn a brief outage into a ban.
            logger.warning(f"Trade stream disconnected ({exc}); retrying in {delay}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_SECONDS)
