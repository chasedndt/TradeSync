"""
Redis client for market data streams.

Streams:
- x:market.raw      - Raw provider payloads
- x:market.norm     - Normalized events
- x:market.snapshot - Latest snapshot per venue/symbol
- x:market.alerts   - Regime changes and extreme values
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from redis import asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

# Stream names
STREAM_RAW = "x:market.raw"
STREAM_NORM = "x:market.norm"
STREAM_SNAPSHOT = "x:market.snapshot"
STREAM_ALERTS = "x:market.alerts"

# Consumer groups
GROUP_NORMALIZER = "market-normalizer"
GROUP_SNAPSHOTTER = "market-snapshotter"


class MarketRedisClient:
    """Redis client optimized for market data streams."""

    def __init__(self):
        self.client: Optional[aioredis.Redis] = None
        self._connected = False

    async def connect(self):
        """Connect to Redis."""
        if self._connected:
            return
        logger.info(f"Connecting to Redis at {REDIS_URL}")
        self.client = aioredis.from_url(REDIS_URL, decode_responses=True)
        self._connected = True
        await self._ensure_streams()

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            self._connected = False
            logger.info("Disconnected from Redis")

    async def _ensure_streams(self):
        """Ensure all streams and consumer groups exist."""
        streams_groups = [
            (STREAM_RAW, GROUP_NORMALIZER),
            (STREAM_NORM, GROUP_SNAPSHOTTER),
        ]

        for stream, group in streams_groups:
            try:
                await self.client.xgroup_create(stream, group, id="0", mkstream=True)
                logger.info(f"Created consumer group '{group}' on stream '{stream}'")
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    logger.debug(f"Consumer group '{group}' already exists on '{stream}'")
                else:
                    logger.error(f"Error creating group '{group}': {e}")

    # === Write Operations ===

    async def push_raw(self, event: Dict[str, Any]) -> str:
        """Push raw event to x:market.raw stream."""
        data = {"data": json.dumps(event)}
        msg_id = await self.client.xadd(STREAM_RAW, data)
        logger.debug(f"Pushed raw event to {STREAM_RAW}: {msg_id}")
        return msg_id

    async def push_normalized(self, event: Dict[str, Any]) -> str:
        """Push normalized event to x:market.norm stream."""
        data = {"data": json.dumps(event)}
        msg_id = await self.client.xadd(STREAM_NORM, data)
        logger.debug(f"Pushed normalized event to {STREAM_NORM}: {msg_id}")
        return msg_id

    async def push_alert(self, alert: Dict[str, Any]) -> str:
        """Push alert to x:market.alerts stream."""
        data = {"data": json.dumps(alert)}
        msg_id = await self.client.xadd(STREAM_ALERTS, data)
        logger.info(f"Pushed alert to {STREAM_ALERTS}: {msg_id}")
        return msg_id

    async def store_snapshot(self, venue: str, symbol: str, snapshot: Dict[str, Any]):
        """
        Store latest snapshot in Redis hash.
        Key format: market:snapshot:{venue}:{symbol}
        """
        key = f"market:snapshot:{venue}:{symbol}"
        await self.client.hset(key, mapping={
            "data": json.dumps(snapshot),
            "ts": str(snapshot.get("ts", 0)),
            "updated_at": str(int(__import__("time").time() * 1000))
        })
        # TTL of 1 hour - snapshots should be refreshed regularly
        await self.client.expire(key, 3600)
        logger.debug(f"Stored snapshot for {venue}:{symbol}")

    # === Read Operations ===

    async def read_raw_stream(
        self,
        consumer: str,
        count: int = 10,
        block_ms: int = 1000
    ) -> List[Dict[str, Any]]:
        """Read from raw stream as consumer."""
        try:
            messages = await self.client.xreadgroup(
                GROUP_NORMALIZER,
                consumer,
                {STREAM_RAW: ">"},
                count=count,
                block=block_ms
            )
            return self._parse_stream_messages(messages)
        except Exception as e:
            logger.error(f"Error reading raw stream: {e}")
            return []

    async def read_norm_stream(
        self,
        consumer: str,
        count: int = 10,
        block_ms: int = 1000
    ) -> List[Dict[str, Any]]:
        """Read from normalized stream as consumer."""
        try:
            messages = await self.client.xreadgroup(
                GROUP_SNAPSHOTTER,
                consumer,
                {STREAM_NORM: ">"},
                count=count,
                block=block_ms
            )
            return self._parse_stream_messages(messages)
        except Exception as e:
            logger.error(f"Error reading norm stream: {e}")
            return []

    async def ack_raw(self, msg_ids: List[str]):
        """Acknowledge messages in raw stream."""
        if msg_ids:
            await self.client.xack(STREAM_RAW, GROUP_NORMALIZER, *msg_ids)

    async def ack_norm(self, msg_ids: List[str]):
        """Acknowledge messages in norm stream."""
        if msg_ids:
            await self.client.xack(STREAM_NORM, GROUP_SNAPSHOTTER, *msg_ids)

    async def get_snapshot(self, venue: str, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest snapshot for venue/symbol."""
        key = f"market:snapshot:{venue}:{symbol}"
        data = await self.client.hget(key, "data")
        if data:
            return json.loads(data)
        return None

    async def get_all_snapshots(self) -> List[Dict[str, Any]]:
        """Get all current snapshots."""
        keys = await self.client.keys("market:snapshot:*")
        snapshots = []
        for key in keys:
            data = await self.client.hget(key, "data")
            if data:
                snapshots.append(json.loads(data))
        return snapshots

    async def get_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent alerts from stream."""
        try:
            # Read last N messages from alerts stream
            messages = await self.client.xrevrange(STREAM_ALERTS, count=limit)
            alerts = []
            for msg_id, data in messages:
                if "data" in data:
                    alert = json.loads(data["data"])
                    alert["_msg_id"] = msg_id
                    alerts.append(alert)
            return alerts
        except Exception as e:
            logger.error(f"Error reading alerts: {e}")
            return []

    # === Timeseries (rolling window) ===

    async def append_timeseries(
        self,
        venue: str,
        symbol: str,
        metric: str,
        value: float,
        ts: int
    ):
        """
        Append to rolling timeseries.
        Uses sorted set with timestamp as score.
        Key: market:ts:{venue}:{symbol}:{metric}
        """
        key = f"market:ts:{venue}:{symbol}:{metric}"
        await self.client.zadd(key, {f"{ts}:{value}": ts})
        # Keep last 24 hours (86400 seconds * 1000 ms)
        cutoff = ts - (86400 * 1000)
        await self.client.zremrangebyscore(key, 0, cutoff)
        # TTL of 25 hours
        await self.client.expire(key, 90000)

    async def get_timeseries(
        self,
        venue: str,
        symbol: str,
        metric: str,
        window_ms: int = 3600000  # 1 hour default
    ) -> List[Dict[str, Any]]:
        """Get timeseries data for metric."""
        key = f"market:ts:{venue}:{symbol}:{metric}"
        now = int(__import__("time").time() * 1000)
        start = now - window_ms

        entries = await self.client.zrangebyscore(key, start, now)
        result = []
        for entry in entries:
            parts = entry.split(":")
            if len(parts) == 2:
                result.append({
                    "ts": int(parts[0]),
                    "value": float(parts[1])
                })
        return result

    # === Helpers ===

    def _parse_stream_messages(self, messages) -> List[Dict[str, Any]]:
        """Parse stream messages into list of dicts."""
        if not messages:
            return []

        result = []
        for stream_name, stream_messages in messages:
            for msg_id, data in stream_messages:
                if "data" in data:
                    parsed = json.loads(data["data"])
                    parsed["_msg_id"] = msg_id
                    result.append(parsed)
        return result


# Singleton instance
redis_client = MarketRedisClient()
