import os
from redis import asyncio as aioredis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

class RedisClient:
    def __init__(self):
        self.client: aioredis.Redis = None

    async def connect(self):
        print("Connecting to Redis...")
        self.client = aioredis.from_url(REDIS_URL, decode_responses=True)

    async def disconnect(self):
        if self.client:
            await self.client.close()

    async def ensure_consumer_group(self, stream: str, group: str):
        try:
            await self.client.xgroup_create(stream, group, id="0", mkstream=True)
            print(f"Created consumer group {group} on stream {stream}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                print(f"Consumer group {group} already exists")
            else:
                print(f"Error creating consumer group: {e}")
                raise

    async def claim_stale_pending(self, stream: str, group: str, consumer: str, min_idle_ms: int, count: int):
        """
        1. XPENDING to find stale messages
        2. XCLAIM to take ownership
        Returns messages in the same format as XREADGROUP
        """
        # XPENDING <stream> <group> - + <count>
        # Returns: [[id, consumer, idle_time, deliver_count], ...]
        pending = await self.client.xpending_range(stream, group, "-", "+", count)
        if not pending:
            return []

        stale_ids = [p["message_id"] for p in pending if p["time_since_delivered"] >= min_idle_ms]
        if not stale_ids:
            return []

        # XCLAIM <stream> <group> <consumer> <min_idle_ms> <id>...
        # Returns: [[id, {field: value, ...}], ...]
        claimed = await self.client.xclaim(stream, group, consumer, min_idle_ms, *stale_ids)
        
        # Format as XREADGROUP output: [[stream, [[id, {data: ...}], ...]]]
        if claimed:
            return [[stream, claimed]]
        return []

redis_client = RedisClient()
