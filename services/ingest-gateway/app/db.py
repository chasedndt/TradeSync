import os
import json
import asyncpg
import redis.asyncio as redis
from .models import NormalizedEvent

# Env vars
PG_DSN = os.getenv("PG_DSN", "postgresql://tradesync:CHANGE_ME@localhost:5432/tradesync")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

redis_client = None

async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    return redis_client

async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None

async def insert_event(event: NormalizedEvent):
    """
    Insert a normalized event into the database and push to Redis stream.
    Returns the event ID if successful, or None if duplicate.
    Raises Exception on other DB errors.
    """
    try:
        # 1. Postgres Insert
        conn = await asyncpg.connect(PG_DSN)
        try:
            await conn.execute("""
                INSERT INTO events (id, ts, source, kind, symbol, timeframe, payload, provenance, hash)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, 
                event.id, 
                event.ts, 
                event.source, 
                event.kind, 
                event.symbol, 
                event.timeframe, 
                json.dumps(event.payload), 
                json.dumps(event.provenance),
                event.hash
            )
        except asyncpg.UniqueViolationError:
            await conn.close()
            return None
        finally:
            await conn.close()

        # 2. Redis Stream Push & Source Mirror
        try:
            r = await get_redis()
            # Push JSON payload to stream
            await r.xadd("x:events.norm", {"data": event.model_dump_json()})

            # --- Source Mirroring (Health Rail) ---
            # Track the latest event for each source to monitor freshness and allow "mirroring"
            mirror_key = f"ingest:source_mirror:{event.source}"
            mirror_data = {
                "last_seen": event.ts.isoformat(),
                "kind": event.kind,
                "symbol": event.symbol,
                "payload": json.dumps(event.payload)
            }
            await r.hset(mirror_key, mapping=mirror_data)
            # Set a TTL for the mirror entry (e.g., 24h) to keep Redis clean
            await r.expire(mirror_key, 86400)

        except Exception as e:
            print(f"Redis Push/Mirror Error: {e}")
            # We don't block ingestion if Redis fails, but we log it.
            
        return event.id

    except Exception as e:
        print(f"DB Error: {e}")
        raise e
