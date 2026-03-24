"""
MarketStore - Pluggable persistence layer for market data.

Phase 3B uses Redis as the primary store. This interface allows
future migration to TimescaleDB without breaking contracts.

See docs/architecture/market_storage.md for design rationale.
"""

import os
import json
import time
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from redis import asyncio as aioredis

from .models import MarketSnapshot

logger = logging.getLogger(__name__)

# Configuration
MARKET_STORE_BACKEND = os.getenv("MARKET_STORE_BACKEND", "redis")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")


class MarketStore(ABC):
    """
    Abstract interface for market data persistence.

    Implementations:
    - RedisStore: Current V1 implementation
    - TimescaleStore: Future implementation (scaffolded)
    """

    @abstractmethod
    async def connect(self):
        """Connect to the storage backend."""
        pass

    @abstractmethod
    async def disconnect(self):
        """Disconnect from the storage backend."""
        pass

    @abstractmethod
    async def put_snapshot(
        self,
        venue: str,
        symbol: str,
        snapshot: MarketSnapshot
    ):
        """Store a snapshot."""
        pass

    @abstractmethod
    async def get_snapshot(
        self,
        venue: str,
        symbol: str
    ) -> Optional[MarketSnapshot]:
        """Get the latest snapshot for venue/symbol."""
        pass

    @abstractmethod
    async def get_all_snapshots(self) -> List[MarketSnapshot]:
        """Get all current snapshots."""
        pass

    @abstractmethod
    async def append_timeseries(
        self,
        venue: str,
        symbol: str,
        metric: str,
        value: float,
        ts: int
    ):
        """Append a value to the timeseries for a metric."""
        pass

    @abstractmethod
    async def get_timeseries(
        self,
        venue: str,
        symbol: str,
        metric: str,
        start_ts: int,
        end_ts: int
    ) -> List[Dict[str, Any]]:
        """Get timeseries data for a metric within a time range."""
        pass


class RedisStore(MarketStore):
    """
    Redis implementation of MarketStore.

    Storage format:
    - Snapshots: Hash at market:snapshot:{venue}:{symbol}
    - Timeseries: Sorted set at market:ts:{venue}:{symbol}:{metric}

    TTLs:
    - Snapshots: 1 hour (should be refreshed every few seconds)
    - Timeseries: 25 hours (keeps last 24h of data)
    """

    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self.client: Optional[aioredis.Redis] = None
        self._connected = False

        # Configuration
        self.snapshot_ttl = 3600  # 1 hour
        self.timeseries_ttl = 90000  # 25 hours
        self.timeseries_max_age = 86400 * 1000  # 24 hours in ms

    async def connect(self):
        """Connect to Redis."""
        if self._connected:
            return

        logger.info(f"Connecting RedisStore to {self.redis_url}")
        self.client = aioredis.from_url(self.redis_url, decode_responses=True)
        self._connected = True

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            self._connected = False
            logger.info("RedisStore disconnected")

    async def put_snapshot(
        self,
        venue: str,
        symbol: str,
        snapshot: MarketSnapshot
    ):
        """Store snapshot in Redis hash."""
        key = f"market:snapshot:{venue}:{symbol}"
        data = snapshot.model_dump_json()

        await self.client.hset(key, mapping={
            "data": data,
            "ts": str(snapshot.ts),
            "updated_at": str(int(time.time() * 1000))
        })
        await self.client.expire(key, self.snapshot_ttl)

        logger.debug(f"Stored snapshot for {venue}:{symbol}")

    async def get_snapshot(
        self,
        venue: str,
        symbol: str
    ) -> Optional[MarketSnapshot]:
        """Get latest snapshot from Redis."""
        key = f"market:snapshot:{venue}:{symbol}"
        data = await self.client.hget(key, "data")

        if not data:
            return None

        try:
            return MarketSnapshot.model_validate_json(data)
        except Exception as e:
            logger.error(f"Error parsing snapshot: {e}")
            return None

    async def get_all_snapshots(self) -> List[MarketSnapshot]:
        """Get all current snapshots."""
        keys = await self.client.keys("market:snapshot:*")
        snapshots = []

        for key in keys:
            data = await self.client.hget(key, "data")
            if data:
                try:
                    snapshots.append(MarketSnapshot.model_validate_json(data))
                except Exception as e:
                    logger.error(f"Error parsing snapshot from {key}: {e}")

        return snapshots

    async def append_timeseries(
        self,
        venue: str,
        symbol: str,
        metric: str,
        value: float,
        ts: int
    ):
        """Append to timeseries using sorted set."""
        key = f"market:ts:{venue}:{symbol}:{metric}"

        # Add with timestamp as score
        member = f"{ts}:{value}"
        await self.client.zadd(key, {member: ts})

        # Prune old entries
        cutoff = ts - self.timeseries_max_age
        await self.client.zremrangebyscore(key, 0, cutoff)

        # Set TTL
        await self.client.expire(key, self.timeseries_ttl)

    async def get_timeseries(
        self,
        venue: str,
        symbol: str,
        metric: str,
        start_ts: int,
        end_ts: int
    ) -> List[Dict[str, Any]]:
        """Get timeseries data within range."""
        key = f"market:ts:{venue}:{symbol}:{metric}"

        entries = await self.client.zrangebyscore(key, start_ts, end_ts)
        result = []

        for entry in entries:
            parts = entry.split(":")
            if len(parts) == 2:
                result.append({
                    "ts": int(parts[0]),
                    "value": float(parts[1])
                })

        return result


class TimescaleStore(MarketStore):
    """
    TimescaleDB implementation of MarketStore.

    NOTE: This is a placeholder/scaffold for future implementation.
    The interface is defined to ensure the Redis implementation
    can be swapped out without breaking contracts.

    Tables (future):
    - market_snapshots: Hypertable with (venue, symbol, ts) key
    - market_timeseries: Hypertable with (venue, symbol, metric, ts) key
    """

    def __init__(self, dsn: str = None):
        self.dsn = dsn or os.getenv("TIMESCALE_DSN")
        self._connected = False
        logger.warning("TimescaleStore is a placeholder - use RedisStore for V1")

    async def connect(self):
        """Connect to TimescaleDB."""
        raise NotImplementedError("TimescaleStore not implemented in V1")

    async def disconnect(self):
        """Disconnect from TimescaleDB."""
        pass

    async def put_snapshot(self, venue: str, symbol: str, snapshot: MarketSnapshot):
        raise NotImplementedError("TimescaleStore not implemented in V1")

    async def get_snapshot(self, venue: str, symbol: str) -> Optional[MarketSnapshot]:
        raise NotImplementedError("TimescaleStore not implemented in V1")

    async def get_all_snapshots(self) -> List[MarketSnapshot]:
        raise NotImplementedError("TimescaleStore not implemented in V1")

    async def append_timeseries(
        self, venue: str, symbol: str, metric: str, value: float, ts: int
    ):
        raise NotImplementedError("TimescaleStore not implemented in V1")

    async def get_timeseries(
        self, venue: str, symbol: str, metric: str, start_ts: int, end_ts: int
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError("TimescaleStore not implemented in V1")


def create_store() -> MarketStore:
    """
    Factory function to create the appropriate store.

    Uses MARKET_STORE_BACKEND env var:
    - "redis" (default): RedisStore
    - "timescale": TimescaleStore (not implemented)
    """
    backend = MARKET_STORE_BACKEND.lower()

    if backend == "redis":
        return RedisStore()
    elif backend == "timescale":
        return TimescaleStore()
    else:
        logger.warning(f"Unknown backend '{backend}', defaulting to Redis")
        return RedisStore()
