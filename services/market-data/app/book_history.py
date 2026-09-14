"""Bounded observed top-of-book history; never synthetic liquidation levels."""
import json
import math
import time

PREFIX = 'market:book-history:'


def snapshot(book):
    levels = []
    for side in ('bids', 'asks'):
        for row in book.get(side, [])[:10]:
            try:
                price, size = float(row['price']), float(row['size'])
            except (KeyError, TypeError, ValueError):
                continue
            if all(math.isfinite(v) and v > 0 for v in (price, size, price*size)):
                levels.append({'side': side, 'price': price, 'notional_usd': price*size})
    return {'time': int(time.time()), 'levels': levels} if levels else None


async def capture(redis, symbol, book):
    item = snapshot(book)
    if item is None:
        return
    key = PREFIX + symbol
    # Fifteen-second buckets; bounded to 240 snapshots and one hour retention.
    bucket = item['time']//15*15
    async with redis.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(key, bucket, bucket)
        pipe.zadd(key, {json.dumps(item): bucket})
        pipe.zremrangebyscore(key, '-inf', item['time']-3600)
        pipe.zremrangebyrank(key, 0, -241)
        pipe.expire(key, 3600)
        await pipe.execute()


async def history(redis, symbol):
    rows = await redis.zrange(PREFIX + symbol, 0, -1)
    now = time.time()
    items = sorted((json.loads(r) for r in rows), key=lambda r: r['time'])
    items = [r for r in items if 0 <= now-r['time'] <= 3600][-240:]
    age = now-items[-1]['time'] if items else None
    return {'venue': 'hyperliquid', 'symbol': symbol, 'samples': items,
            'status': 'collecting' if not items else 'stale' if age > 30 else 'live',
            'age_seconds': age, 'retention_seconds': 3600, 'sample_bucket_seconds': 15,
            'authority': 'display_only',
            'note': 'Observed top 10 bid and ask levels, sampled into 15-second buckets by local receipt time. Gaps are not filled. Displayed orders can be cancelled; this is not a liquidation heatmap, full-depth history or executable liquidity guarantee. Collection starts with this service version; Redis history is bounded, not a durable research archive.'}
