"""Public-account observations only. No signer, configuration or order actions."""
import asyncio
import math
from datetime import datetime, timezone
import httpx


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def normalize(payload, kind):
    if not isinstance(payload, list):
        raise ValueError('Expected venue rows')
    rows, invalid = [], 0
    for raw in payload:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        price = number(raw.get('limitPx' if kind == 'orders' else 'px'))
        size, timestamp = number(raw.get('sz')), number(raw.get('timestamp' if kind == 'orders' else 'time'))
        if (price is None or price < 0 or size is None or size < 0 or timestamp is None or timestamp <= 0
                or not isinstance(raw.get('coin'), str) or raw.get('side') not in ('A', 'B')):
            invalid += 1
            continue
        item = {'instrument': raw['coin'], 'side': 'SELL' if raw['side'] == 'A' else 'BUY',
                'price': price, 'size': size, 'time_ms': timestamp, 'order_id': str(raw.get('oid', ''))}
        if kind == 'orders':
            item.update(order_type=raw.get('orderType'), reduce_only=raw.get('reduceOnly'),
                        is_trigger=raw.get('isTrigger'), trigger_price=number(raw.get('triggerPx')),
                        trigger_condition=raw.get('triggerCondition'))
        else:
            item.update(trade_id=str(raw.get('tid', '')), direction=raw.get('dir'),
                        closed_pnl=number(raw.get('closedPnl')), fee=number(raw.get('fee')),
                        fee_token=raw.get('feeToken'), transaction_hash=raw.get('hash'))
        rows.append(item)
    rows.sort(key=lambda r: r['time_ms'], reverse=True)
    return {'status': 'partial' if invalid else 'available', 'rows': rows[:100],
            'received_count': len(payload), 'invalid_rows': invalid,
            'display_limit': 100, 'truncated': len(rows) > 100,
            'observed_at': datetime.now(timezone.utc).isoformat()}


async def read_activity(url, address):
    async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
        async def read(kind, request_type):
            try:
                response = await client.post(url, json={'type': request_type, 'user': address})
                response.raise_for_status()
                return normalize(response.json(), kind)
            except Exception:
                return {'status': 'unavailable', 'rows': None, 'observed_at': None,
                        'detail': 'Venue response unavailable or malformed; no empty-account conclusion.'}
        orders, fills = await asyncio.gather(read('orders', 'frontendOpenOrders'), read('fills', 'userFills'))
    return {'address': address, 'authority': 'read_only', 'open_orders': orders, 'recent_fills': fills,
            'source': 'Hyperliquid frontendOpenOrders and userFills',
            'note': 'Independent reads, not an atomic account snapshot. Open orders cover the default perp dex and included spot orders; fills can include spot and other perp dexes. Raw venue instrument identifiers are retained. Latest 100 valid rows shown; userFills returns at most 2000 recent fills, not lifetime history. Closed P&L is the venue field, not a fee/funding-adjusted portfolio return. No place, amend or cancel authority.'}
