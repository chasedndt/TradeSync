"""Bybit public observed liquidations, never Hyperliquid execution authority.

Reference: https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation
S denotes the liquidated POSITION side. p is bankruptcy price, NOT fill price.
"""
import asyncio
import hashlib
import json
import math
import time

import websockets

from .feed_status import feed

URL = 'wss://stream.bybit.com/v5/public/linear'
STATUS = 'market:bybit-liquidations:status'
PREFIX = 'market:bybit-liquidations:received-v2:'
SYMBOLS = {'BTCUSDT': 'BTC-PERP', 'ETHUSDT': 'ETH-PERP', 'SOLUSDT': 'SOL-PERP'}
HEARTBEAT = feed('bybit_liquidations', label='Bybit liquidations stream (BTC, ETH, SOL)', kind='websocket', authority='context_only',
                 influence="Context only: another venue's liquidations, counted into the liquidity context and the recorded "
                           'history; the feature catalog marks them non-scoring.',
                 counts=('messages', 'events'))

# Store one original receipt per stable event fingerprint. Replays must never
# replace its knowledge timestamp. Both indexes expire and are bounded together.
STORE_RECEIPT = '''
local added = redis.call('ZADD', KEYS[1], 'NX', ARGV[2], ARGV[1])
if added == 1 then redis.call('HSET', KEYS[2], ARGV[1], ARGV[3]) end
local old = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[4])
for _, id in ipairs(old) do redis.call('HDEL', KEYS[2], id) end
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[4])
local extra = redis.call('ZRANGE', KEYS[1], 0, -1001)
for _, id in ipairs(extra) do redis.call('HDEL', KEYS[2], id) end
redis.call('ZREMRANGEBYRANK', KEYS[1], 0, -1001)
redis.call('EXPIRE', KEYS[1], 3600)
redis.call('EXPIRE', KEYS[2], 3600)
return added
'''


async def store_receipt(redis, event, now):
    key = PREFIX+event['symbol']
    return await redis.eval(STORE_RECEIPT, 2, key, key+':payloads', event['id'],
                            event['event_time'], json.dumps(event, sort_keys=True), now-3600)


def normalize(message, received_at):
    events = []
    if not isinstance(message, dict) or not isinstance(message.get('data'), list):
        return events
    for index, row in enumerate(message['data']):
        try:
            symbol = SYMBOLS[row['s']]
            if message.get('topic') != 'allLiquidation.' + row['s'] or row['S'] not in ('Buy', 'Sell'):
                continue
            price, size, event_ms = float(row['p']), float(row['v']), int(row['T'])
            if not all(math.isfinite(n) and n > 0 for n in (price, size, price*size)):
                continue
            if not 0 <= received_at*1000-event_ms <= 3600000:
                continue
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        # No exchange event id is supplied. Batch fingerprint + row index retains
        # identical rows in one batch while suppressing identical batch replays.
        identity = json.dumps([message.get('ts'), index, row], sort_keys=True)
        events.append({'id': hashlib.sha256(identity.encode()).hexdigest(),
                       'source': 'bybit', 'symbol': symbol, 'event_time': event_ms/1000,
                       'received_at': received_at, 'position_side': 'long' if row['S'] == 'Buy' else 'short',
                       'size': size, 'bankruptcy_price': price,
                       'bankruptcy_notional_usdt': price*size, 'authority': 'context_only'})
    return events


async def run(redis):
    async def status(state, **extra):
        terminal = state in ('provider_access_denied', 'subscription_rejected')
        await redis.set(STATUS, json.dumps({'state': state, 'updated_at': time.time(), **extra}), ex=86400 if terminal else 60)
    while True:
        try:
            HEARTBEAT.connecting()
            await status('connecting')
            async with websockets.connect(URL, open_timeout=10, max_size=2**20, ping_interval=20) as ws:
                await ws.send(json.dumps({'op': 'subscribe', 'args': ['allLiquidation.'+s for s in SYMBOLS]}))
                subscribed_at = None
                last_received = time.monotonic()
                last_ping = time.monotonic()
                while True:
                    if time.monotonic()-last_ping >= 20:
                        await ws.send('{"op":"ping"}')
                        last_ping = time.monotonic()
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        if time.monotonic()-last_received > 45:
                            raise TimeoutError('No provider heartbeat')
                        continue
                    message = json.loads(raw)
                    last_received = time.monotonic()
                    HEARTBEAT.message()
                    if message.get('op') == 'subscribe':
                        if message.get('success') is not True:
                            HEARTBEAT.failed('subscription rejected, not retried', state='subscription_rejected')
                            await status('subscription_rejected')
                            return  # Permission / provider denial: no retry workaround.
                        subscribed_at = time.time()
                        HEARTBEAT.connected()
                    if subscribed_at is None:
                        continue
                    now = time.time()
                    await status('connected', subscribed_at=subscribed_at)
                    events = normalize(message, now)
                    for event in events:
                        await store_receipt(redis, event, now)
                    HEARTBEAT.count('events', len(events), now=now)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            response = getattr(exc, 'response', None)
            code = getattr(response, 'status_code', getattr(exc, 'status_code', None))
            if code in (401, 403, 451):
                HEARTBEAT.failed(f'HTTP {code}: access denied, not retried', state='provider_access_denied')
                await status('provider_access_denied', http_status=code)
                return  # Do not bypass regional/account/access restrictions.
            HEARTBEAT.failed(exc, state='disconnected')
            try:
                await status('disconnected', error_type=type(exc).__name__)
            except Exception:
                pass  # a full or unreachable Redis must not end the collector; the next attempt retries
            await asyncio.sleep(30)


async def history(redis, symbol):
    raw_status = await redis.get(STATUS)
    state = json.loads(raw_status) if raw_status else {'state': 'unavailable'}
    identities = await redis.zrangebyscore(PREFIX+symbol, time.time()-3600, '+inf')
    rows = await redis.hmget(PREFIX+symbol+':payloads', identities) if identities else []
    events = sorted((json.loads(r) for r in rows if r), key=lambda r: r['event_time'], reverse=True)
    return {'venue': 'bybit', 'symbol': symbol, 'supported': symbol in SYMBOLS.values(),
            'connection': state, 'events': events, 'authority': 'context_only',
            'receipt_schema': 'first-received-v2',
            'note': 'Bybit USDT contracts only, not Hyperliquid liquidations. Up to 1 hour / 1000 received events per symbol, no backfill; reconnects leave gaps. Prices are bankruptcy prices and notional is size times bankruptcy price, not verified fill value. Zero received events does not establish zero liquidations. No thesis or order authority.'}
