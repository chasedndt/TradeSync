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

    async def ensure_consumer_group(self, stream: str, group: str, legacy_group: str = None):
        """
        Ensures the consumer group exists, with optional migration from a legacy group.

        Migration logic:
        - If legacy_group exists and new group doesn't: creates new group, logs migration
        - If both exist: logs warning about orphan legacy group
        - If neither exists: creates new group fresh
        """
        # Check existing groups
        legacy_exists = False
        new_exists = False
        legacy_pending = 0

        try:
            groups_info = await self.client.xinfo_groups(stream)
            for g in groups_info:
                if g["name"] == group:
                    new_exists = True
                if legacy_group and g["name"] == legacy_group:
                    legacy_exists = True
                    legacy_pending = g.get("pending", 0)
        except Exception as e:
            if "no such key" not in str(e).lower():
                print(f"Error checking groups: {e}")

        # Migration scenarios
        if legacy_exists and not new_exists:
            print(f"[Migration] Found legacy group '{legacy_group}' with {legacy_pending} pending messages")
            print(f"[Migration] Creating new canonical group '{group}'")
            # Create new group starting from where legacy left off (use $ for latest, or 0 for all)
            # Using "0" to reprocess - safer for data integrity
            try:
                await self.client.xgroup_create(stream, group, id="0", mkstream=True)
                print(f"[Migration] Created consumer group '{group}' on stream {stream}")
                print(f"[Migration] Legacy group '{legacy_group}' still exists - delete manually once stable:")
                print(f"[Migration]   redis-cli XGROUP DESTROY {stream} {legacy_group}")
            except Exception as e:
                if "BUSYGROUP" not in str(e):
                    raise
            return

        if legacy_exists and new_exists:
            print(f"[Warning] Both groups exist: '{group}' (canonical) and '{legacy_group}' (legacy, {legacy_pending} pending)")
            print(f"[Warning] Consider deleting legacy group once confirmed stable:")
            print(f"[Warning]   redis-cli XGROUP DESTROY {stream} {legacy_group}")
            return

        # Standard creation
        try:
            await self.client.xgroup_create(stream, group, id="0", mkstream=True)
            print(f"Created consumer group '{group}' on stream {stream}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                print(f"Consumer group '{group}' already exists")
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
