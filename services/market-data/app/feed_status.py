"""Market-data's feed heartbeats, served at ``GET /feeds/status`` for the integration pipeline page.

Each feed declares its heartbeat beside the code that runs it (``depth_stream``,
``binance_liquidations``, ``liquidation_context``, ``open_interest_history``,
``funding_history_route`` and ``liquidity_context``); this module only holds
them. Counts are in memory and restart with the service.
"""

from __future__ import annotations

from tradesync_core.feed_heartbeat import Registry

REGISTRY = Registry("market-data")
feed = REGISTRY.feed
