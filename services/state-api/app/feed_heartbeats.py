"""State-api's own feed heartbeats: the market history recorder and the Timeframes warm loop.

Each loop declares its heartbeat beside its code (``market_recorder``,
``horizons_warm``); this module only holds them, for ``pipeline_feeds``.
Counts are in memory and restart with the service.
"""

from __future__ import annotations

from tradesync_core.feed_heartbeat import Registry

REGISTRY = Registry("state-api")
feed = REGISTRY.feed
