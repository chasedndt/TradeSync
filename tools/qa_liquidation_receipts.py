"""Real Redis receipt/dedupe test in unique expiring task keys; no feed mutation."""
import asyncio
import json
import os
import time
import uuid
from redis.asyncio import Redis
from app import liquidation_context as module


async def main():
    redis = Redis.from_url(os.environ.get('REDIS_URL', 'redis://redis:6379/0'))
    module.PREFIX = 'qa:tradesync:receipt:'+uuid.uuid4().hex+':'
    key = module.PREFIX+'BTC-PERP'
    now = time.time()
    event = {'id':'fixture', 'symbol':'BTC-PERP', 'event_time':now-1, 'received_at':now}
    try:
        assert await module.store_receipt(redis, event, now) == 1
        assert await module.store_receipt(redis, {**event, 'received_at':now+5}, now+5) == 0
        stored = json.loads(await redis.hget(key+':payloads', 'fixture'))
        assert stored['received_at'] == now
        for i in range(1002):
            await module.store_receipt(redis, {**event, 'id':str(i), 'event_time':now+i/10000}, now)
        assert await redis.zcard(key) == 1000
        assert await redis.hlen(key+':payloads') == 1000
        await module.store_receipt(redis, {**event, 'id':'later', 'event_time':now+4000, 'received_at':now+4000}, now+4000)
        assert await redis.zcard(key) == await redis.hlen(key+':payloads') == 1
        print('PASS: first receipt immutable under replay; ZSET/hash bounded together at 1000; old events pruned together.')
    finally:
        # Retain isolated QA evidence briefly; Redis expires only these exact keys.
        await redis.expire(key, 60)
        await redis.expire(key+':payloads', 60)
        await redis.aclose()


asyncio.run(main())
