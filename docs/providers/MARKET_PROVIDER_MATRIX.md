# Market Provider Matrix

> **Purpose**: Single source of truth for what market data is available from each provider.
> **Last Updated**: 2026-01-21

---

## Overview

| Venue | API Base URL | Auth Required | Rate Limits |
|-------|-------------|---------------|-------------|
| Hyperliquid | `https://api.hyperliquid.xyz/info` | No (public) | ~120 req/min (observed) |
| Drift | `https://data.api.drift.trade` | No (public) | ~60 req/min (observed) |

---

## Metric Availability Matrix

| Metric | Hyperliquid | Drift | Notes |
|--------|-------------|-------|-------|
| **Funding Rate (current)** | REAL | REAL | Both provide current rate |
| **Funding Rate (historical)** | REAL | REAL | HL: `fundingHistory`, Drift: `/fundingRates` |
| **Funding Rate (predicted)** | REAL | NO | HL: `predictedFundings` endpoint |
| **Open Interest** | REAL | REAL | Both in main context endpoints |
| **Orderbook (L2)** | REAL | REAL | HL: 20 levels/side, Drift: via DLOB |
| **Orderbook (spread)** | REAL | REAL | Derived from L2 |
| **Volume (24h)** | REAL | REAL | `dayNtlVlm` / daily volume |
| **Volume (historical)** | REAL | PROXY | HL via candles, Drift limited |
| **CVD (Cumulative Vol Delta)** | PROXY | PROXY | Must compute from trade flow |
| **Liquidations (real-time)** | NO | NO | No public feed |
| **Liquidations (historical)** | NO | PROXY | Drift has some historical data |
| **Mark Price** | REAL | REAL | Both provide |
| **Oracle Price** | REAL | REAL | Both provide |

---

## 1. Hyperliquid

### 1.1 Endpoints

| Endpoint | Type | Request | Cadence | Notes |
|----------|------|---------|---------|-------|
| `metaAndAssetCtxs` | POST | `{"type": "metaAndAssetCtxs"}` | 5s | Main snapshot with funding, OI, volume, mark, oracle |
| `fundingHistory` | POST | `{"type": "fundingHistory", "coin": "BTC", "startTime": <ms>}` | On-demand | Historical funding rates |
| `predictedFundings` | POST | `{"type": "predictedFundings"}` | 30s | Predicted cross-venue funding |
| `l2Book` | POST | `{"type": "l2Book", "coin": "BTC"}` | 2s | 20 levels per side |
| `candle` | POST | `{"type": "candleSnapshot", "req": {"coin": "BTC", "interval": "1h", "startTime": <ms>}}` | On-demand | OHLCV data (last 5000 candles) |

### 1.2 Rate Limits

| Limit Type | Value | Source |
|------------|-------|--------|
| Requests/minute | ~120 | Observed (conservative) |
| Burst | Unknown | Use 10 req/s max |
| Backoff | Exponential | On 429 response |

### 1.3 Symbol Format

| Raw Format | Example | Normalization |
|------------|---------|---------------|
| Base only | `BTC` | `BTC` → `BTC-PERP` |
| With quote | `BTC/USD` | Rare, handle in normalizer |

### 1.4 Response Fields (metaAndAssetCtxs)

```json
[
  {
    "universe": [
      {"name": "BTC", "szDecimals": 5, "maxLeverage": 50}
    ]
  },
  [
    {
      "funding": "0.00003",
      "openInterest": "12500.5",
      "dayNtlVlm": "1500000000",
      "markPx": "105000.50",
      "oraclePx": "105010.00",
      "premium": "0.00005",
      "impactPxs": ["105000.40", "105000.60"]
    }
  ]
]
```

### 1.5 Data Quality Notes

- **Funding**: Updated hourly, rate capped at 4%/hour
- **OI**: Real-time, denominated in asset units
- **Volume**: 24h rolling, in notional USD
- **Orderbook**: Snapshot, not streaming (use WS for real-time)
- **Liquidations**: NOT available via public API

---

## 2. Drift Protocol

### 2.1 Endpoints

| Endpoint | Type | URL | Cadence | Notes |
|----------|------|-----|---------|-------|
| Contracts | GET | `/contracts` | 10s | Main snapshot with all perps |
| Funding Rates | GET | `/fundingRates` | On-demand | Historical funding |
| L2 Book | GET | `/l2?marketIndex=0` | 2s | Via DLOB server |
| DLOB WS | WS | `wss://dlob.drift.trade` | Real-time | Streaming orderbook |

### 2.2 Rate Limits

| Limit Type | Value | Source |
|------------|-------|--------|
| Requests/minute | ~60 | Conservative estimate |
| DLOB specific | Higher | Separate infrastructure |

### 2.3 Symbol Format

| Raw Format | Example | Normalization |
|------------|---------|---------------|
| Canonical | `BTC-PERP` | Already normalized |
| Market Index | `0` | Map via contracts endpoint |

### 2.4 Response Fields (/contracts)

```json
[
  {
    "ticker_id": "BTC-PERP",
    "base_currency": "BTC",
    "quote_currency": "USDC",
    "last_price": "105050.25",
    "funding_rate": "0.00005",
    "open_interest": "5000000",
    "index_price": "105045.00",
    "24h_volume": "250000000"
  }
]
```

### 2.5 Data Quality Notes

- **Funding**: Continuous funding, not fixed intervals
- **OI**: In USD notional
- **Volume**: 24h in USD
- **Orderbook**: Via DLOB server (separate infra)
- **Liquidations**: Some historical via external sources (toirt.com)

---

## 3. Liquidation Proxy Strategy

Since neither venue provides real-time liquidation feeds, we use a **PROXY** approach:

### 3.1 OI Delta Method

When OI drops sharply without corresponding trade volume, it indicates forced liquidations.

```python
def estimate_liquidations(oi_prev: float, oi_current: float, volume: float) -> dict:
    """
    Estimate liquidation activity from OI deltas.

    If OI drops significantly without matching volume increase,
    the difference is likely liquidations.
    """
    oi_delta = oi_current - oi_prev

    if oi_delta < 0:  # OI decreased
        # Rough heuristic: OI reduction without volume = liqs
        estimated_liqs = abs(oi_delta) * 0.5  # Conservative multiplier
        return {
            "estimated_usd": estimated_liqs,
            "confidence": "low",
            "method": "oi_delta_proxy"
        }
    return {"estimated_usd": 0, "confidence": "low", "method": "oi_delta_proxy"}
```

### 3.2 UI Labeling

When displaying proxy liquidations:
- Label: "LIQ PROXY"
- Tooltip: "Estimated from OI changes. Real liquidation feed unavailable."
- Visual: Dashed border or different color than REAL metrics

---

## 4. CVD Proxy Strategy

Neither venue provides CVD directly. Must compute from trade flow.

### 4.1 Trade-Based CVD

```python
def compute_cvd(trades: list) -> float:
    """
    Compute CVD from individual trades.
    Buy = positive, Sell = negative.
    """
    cvd = 0.0
    for trade in trades:
        if trade["side"] == "buy":
            cvd += trade["size_usd"]
        else:
            cvd -= trade["size_usd"]
    return cvd
```

### 4.2 Candle-Based CVD Proxy

If trades unavailable, estimate from candle close vs open:

```python
def estimate_cvd_from_candles(candles: list) -> float:
    """
    Rough CVD estimate: if close > open, net buying.
    """
    cvd = 0.0
    for c in candles:
        delta = c["close"] - c["open"]
        direction = 1 if delta > 0 else -1
        cvd += direction * c["volume"] * 0.5  # Assume 50% directional
    return cvd
```

### 4.3 UI Labeling

- Label: "CVD PROXY"
- Tooltip: "Estimated from price action. Direct trade flow unavailable."

---

## 5. Polling Cadence Recommendations

| Metric | Cadence | Rationale |
|--------|---------|-----------|
| Funding (current) | 30s | Hourly settlement, no need for faster |
| Funding (historical) | 5m | Batch historical aggregation |
| OI | 5s | Sensitive to market moves |
| Orderbook | 2s | Need fresh spread data |
| Volume | 30s | Less time-sensitive |
| Mark/Oracle | 5s | For regime detection |

---

## 6. Backoff & Jitter Strategy

```python
import random
import asyncio

class ProviderRateLimiter:
    def __init__(self, venue: str, rpm: int):
        self.venue = venue
        self.rpm = rpm
        self.min_interval = 60 / rpm
        self.backoff = 1.0
        self.last_request = 0

    async def acquire(self):
        elapsed = time.time() - self.last_request
        wait = max(0, self.min_interval * self.backoff - elapsed)
        jitter = random.uniform(0, 0.2 * self.min_interval)
        await asyncio.sleep(wait + jitter)
        self.last_request = time.time()

    def on_success(self):
        self.backoff = max(1.0, self.backoff * 0.9)

    def on_rate_limit(self):
        self.backoff = min(10.0, self.backoff * 2.0)
```

---

## 7. Sample Payloads

See `docs/samples/market/` for raw API response samples:
- `hyperliquid_metaAndAssetCtxs.json`
- `hyperliquid_fundingHistory.json`
- `hyperliquid_l2Book.json`
- `drift_contracts.json`
- `drift_fundingRates.json`

---

## 8. Future Providers (Placeholder)

| Provider | Status | Notes |
|----------|--------|-------|
| Binance Futures | Planned | Requires API key for some endpoints |
| Bybit | Planned | Good liquidation data |
| OKX | Planned | Good OI breakdown |

---

*Last updated: 2026-01-21*
*Phase: 3B — Market Data Expansion*
