# Drift Provider Runtime Audit

**Date:** 2026-03-29
**Service:** `services/market-data/app/providers/drift.py`
**Symptom:** `Error fetching Drift context: ...` in market-data logs; context data missing for Drift venue

---

## Root Cause

The `fetch_context` method called `https://data.api.drift.trade/contracts`, which has been removed from the Drift Data API. All requests to `/contracts` return HTTP 404. The exception is caught silently and `{}` is returned, leaving context data for Drift missing (no funding rate, OI, volume, or price from Drift side).

The `/fundingRates` and DLOB `/l2` endpoints were unaffected — only `fetch_context` was broken.

## Live Confirmation (2026-03-29)

Confirmed in market-data container logs during live runtime investigation:
```
INFO:  HTTP Request: GET https://data.api.drift.trade/contracts "HTTP/1.1 404 Not Found"
ERROR: Error fetching Drift context: Client error '404 Not Found' for url 'https://data.api.drift.trade/contracts'
```
This error was repeating every ~6 seconds. The `/stats/markets` fix is in code but the container has not been rebuilt yet.

**Second instance found:** `services/ingest-gateway/sources/drift.py` independently hardcoded the same broken URL. Fixed in the same pass — see Files Changed.

---

## API Endpoint Change

| Endpoint | Status | Notes |
|----------|--------|-------|
| `/contracts` | **REMOVED (404)** | Old endpoint; no longer exists |
| `/markets` | 404 | Does not exist either |
| `/stats/markets` | **LIVE (200)** | Current replacement |

`/stats/markets` returns the same logical data under different field names:

| Old field (`/contracts`) | New field (`/stats/markets`) |
|--------------------------|------------------------------|
| `ticker_id` | `symbol` |
| `funding_rate` (scalar) | `fundingRate` (scalar or `{long, short}`) |
| `open_interest` (scalar USD) | `openInterest` (scalar or `{long, short}`) |
| `24h_volume` | `baseVolume` |
| `mark_price` | `markPrice` |
| `index_price` | `oraclePrice` |
| `last_price` | `price` |
| `max_leverage` | `limits.maxLeverage` |
| `market_index` | Not present — resolved from `_market_index` dict |

The new endpoint wraps the list: `{"success": true, "markets": [...]}`. The fix handles both the wrapped and bare-list formats.

---

## Fix Applied

**File:** `services/market-data/app/providers/drift.py`

Changed `fetch_context` to:
1. Call `/stats/markets` instead of `/contracts`
2. Extract markets from `data.get("markets", [])` or treat as bare list
3. Filter `marketType != "perp"` to skip spot markets
4. Map new field names with graceful fallbacks for both scalar and `{long, short}` dict formats
5. Resolve `market_index` from local `_market_index` dict (hardcoded: BTC-PERP=0, ETH-PERP=1, SOL-PERP=2)
6. Output structure unchanged — downstream MarketNormalizer sees identical keys

The output contract for callers is unchanged:
```python
{
    "funding": {"rate": float, "source": "stats/markets"},
    "oi": {"value": float, "unit": "usd", "source": "stats/markets"},
    "volume": {"value_24h": float, "unit": "usd", "source": "stats/markets"},
    "price": {"mark": float, "index": float, "last": float},
    "meta": {"max_leverage": int, "market_index": int}
}
```

---

## Endpoints NOT Changed

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `fetch_orderbook` | `GET /l2` via `dlob.drift.trade` | Unaffected | DLOB server separate; returns 200 |
| `fetch_funding_history` | `GET /fundingRates` via `data.api.drift.trade` | Unaffected | Still active; returns funding history |

---

## Known Limitations

1. **Market index not in `/stats/markets` response** — `market_index` is resolved from the hardcoded `_market_index` dict (BTC-PERP=0, ETH-PERP=1, SOL-PERP=2). If Drift renumbers markets (which it does for new listings), this could silently map to the wrong index. Mitigation: add a symbol→marketIndex fetch from a dedicated markets metadata endpoint if this becomes a problem.

2. **`fundingRate` field shape** — The `/stats/markets` API may return either a scalar or `{"long": x, "short": y}`. The fix reads the `long` side when it's a dict. Spot-check against live data if funding rates appear wrong.

3. **`openInterest` field shape** — When returned as `{"long": x, "short": y}`, the fix sums both sides. True perp OI in standard terminology is typically the larger of the two. This may overstate OI slightly if long/short are both non-zero.

4. **Live log confirmation** — The `/contracts` 404 was confirmed in live market-data container logs on 2026-03-29. The `/stats/markets` fix is in code but the container was not yet rebuilt during this session.

5. **Second instance in ingest-gateway** — `services/ingest-gateway/sources/drift.py` also hardcoded the broken `/contracts` URL. This was fixed in the same pass. The ingest-gateway Drift poller has never successfully ingested Drift market events.

---

## Verification Steps

After deploying:
```bash
docker compose -f ops/compose.full.yml logs -f market-data | grep -i drift
```

Expected: `Fetched context for N symbols from Drift` (not `Error fetching Drift context`)

Also check the aggregate endpoint:
```bash
curl -s http://localhost:8005/market/aggregate/BTC-PERP | jq '.drift.funding'
```

Should return a non-null funding rate instead of empty object.
