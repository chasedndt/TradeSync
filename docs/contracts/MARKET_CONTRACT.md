# MarketSnapshot Contract

> **Purpose**: Single source of truth for the MarketSnapshot schema.
> **Invariant**: All market data flows through this contract.
> **Last Updated**: 2026-01-21

---

## 1. Overview

The `MarketSnapshot` is the canonical representation of market state for a single venue/symbol pair. It includes:

1. **Identification**: venue, symbol (normalized), timestamp
2. **Truthfulness**: `available_metrics[]` with REAL/PROXY/UNAVAILABLE flags
3. **Multi-horizon data**: Each metric includes multiple time windows
4. **Regime classifications**: Computed from multi-horizon context
5. **Staleness tracking**: `ts` and `data_age_ms` for freshness checks

---

## 2. TypeScript Interface

```typescript
interface MarketSnapshot {
  // === Identification ===
  venue: "hyperliquid" | "drift";
  symbol: string;           // Canonical format: "BTC-PERP"
  ts: number;               // Unix timestamp (ms) when snapshot was created
  data_age_ms: number;      // Age of oldest data in this snapshot

  // === Truthfulness ===
  available_metrics: MetricAvailability[];

  // === Market Data ===
  funding?: FundingData;
  oi?: OpenInterestData;
  liquidations?: LiquidationData;
  volume?: VolumeData;
  orderbook?: OrderbookData;

  // === Computed Regimes ===
  regimes: RegimeSummary;

  // === Truthfulness ===
  available_metrics: MetricAvailability[];

  // === Source Metadata ===
  sources: SourceMetadata[];
}

// === Metric Availability ===
type MetricStatus = "REAL" | "PROXY" | "UNAVAILABLE" | "STALE" | "DERIVED";

interface MetricAvailability {
  metric: "funding" | "oi" | "liquidations" | "volume" | "orderbook" | "microstructure";
  status: MetricStatus;
  source?: string;          // Provider name if available
  last_updated?: number;    // Unix timestamp (ms)
  note?: string;            // Explanation if PROXY or UNAVAILABLE
}
```

---

## 3. Funding Data Schema

```typescript
interface FundingData {
  // === Multi-horizon windows ===
  horizons: {
    now: number;            // Current/next funding rate
    "8h": number;           // Last 8-hour average (1 funding period for HL)
    "24h": number;          // Last 24-hour average
    "3d": number;           // 3-day average
    "7d": number;           // 7-day average
  };

  // === Derived ===
  annualized_24h: number;   // horizons["24h"] * 365

  // === Regime ===
  regime: FundingRegime;

  // === Source ===
  source: {
    provider: string;
    endpoint: string;
    raw_rate: number;       // Unprocessed rate from API
  };
}

type FundingRegime =
  | "extreme_positive"      // > 50% APR
  | "elevated_positive"     // 20-50% APR
  | "neutral"               // -20% to 20% APR
  | "elevated_negative"     // -50% to -20% APR
  | "extreme_negative";     // < -50% APR
```

---

## 4. Open Interest Data Schema

```typescript
interface OpenInterestData {
  // === Multi-horizon windows ===
  horizons: {
    "5m": HorizonValue;
    "15m": HorizonValue;
    "1h": HorizonValue;
    "4h": HorizonValue;
    "24h": HorizonValue;
    "7d": HorizonValue;
  };

  // === Current ===
  current_usd: number;      // Current OI in USD

  // === Regime ===
  regime: OIRegime;
}

interface HorizonValue {
  value: number;            // Absolute value at horizon start
  delta_pct: number;        // % change over horizon
  delta_usd: number;        // Absolute change in USD
}

type OIRegime =
  | "build"                 // OI increasing with momentum
  | "unwind"                // OI decreasing with momentum
  | "flat";                 // Consolidation
```

---

## 5. Liquidation Data Schema

```typescript
interface LiquidationData {
  // === Multi-horizon windows ===
  horizons: {
    "5m": LiquidationWindow;
    "1h": LiquidationWindow;
    "4h": LiquidationWindow;
    "24h": LiquidationWindow;
    "7d"?: LiquidationWindow;   // Optional, aggregated
  };

  // === Source note (important for PROXY) ===
  source_note?: string;     // E.g., "PROXY: estimated from OI deltas"
  method: "real" | "oi_delta_proxy";
}

interface LiquidationWindow {
  longs_usd: number;        // Long liquidations in USD
  shorts_usd: number;       // Short liquidations in USD
  total_usd: number;        // Total liquidations
  dominant_side: "longs" | "shorts" | "balanced";
}
```

---

## 6. Volume Data Schema

```typescript
interface VolumeData {
  // === Multi-horizon windows ===
  horizons: {
    "5m": number;           // USD volume
    "15m": number;
    "1h": number;
    "4h": number;
    "24h": number;
    "7d": number;
  };

  // === CVD (if available) ===
  cvd?: {
    "5m": number;           // Cumulative Volume Delta
    "1h": number;
    "4h": number;
    "24h": number;
  };
  cvd_method?: "real" | "candle_proxy";

  // === 7-day average for comparison ===
  avg_7d_daily: number;

  // === Regime ===
  regime: VolumeRegime;
}

type VolumeRegime =
  | "high"                  // > 2x average
  | "normal"                // 0.5x - 2x average
  | "low";                  // < 0.5x average
```

---

## 7. Orderbook Data Schema

```typescript
interface OrderbookData {
  // === Spread ===
  spread_bps: number;       // Spread in basis points
  spread_usd: number;       // Spread in USD

  // === Depth ===
  depth: {
    bid_1pct_usd: number;   // Bid liquidity within 1% of mid
    ask_1pct_usd: number;   // Ask liquidity within 1% of mid
    bid_2pct_usd: number;   // Bid liquidity within 2% of mid
    ask_2pct_usd: number;   // Ask liquidity within 2% of mid
  };

  // === Imbalance ===
  imbalance_1pct: number;   // (bid - ask) / (bid + ask), range -1 to 1

  // === Best prices ===
  best_bid: number;
  best_ask: number;
  mid_price: number;

  // === Microstructure (Phase 3C) ===
  microstructure?: {
    spread_bps: number;
    mid_price: number;
    depth_usd: {
      "10bp": number;
      "25bp": number;
      "50bp": number;
    };
    impact_est_bps: {
      "1000": number;
      "5000": number;
      "10000": number;
    };
    liquidity_score: number; // 0..1
    book_heatmap: {
      levels: Array<{ price: number, side: "bid"|"ask", size_usd: number }>;
    };
  };

  // === Staleness ===
  book_age_ms: number;
}
```

---

## 8. Regime Summary Schema

```typescript
interface RegimeSummary {
  funding: FundingRegime;
  oi: OIRegime;
  volume: VolumeRegime;
  trend: TrendRegime;

  // === Composite ===
  market_condition: MarketCondition;

  // === Confidence ===
  confidence: "high" | "medium" | "low";
  confidence_note?: string; // E.g., "Low: missing liquidation data"
}

type TrendRegime =
  | "strong_trend"          // Clear directional move
  | "weak_trend"            // Mild directional bias
  | "range";                // Consolidation

type MarketCondition =
  | "trending_healthy"      // Good conditions for trend following
  | "squeeze_risk"          // Extreme funding + OI buildup
  | "capitulation"          // High liqs + OI unwind
  | "choppy"                // Range with low conviction
  | "unknown";              // Insufficient data
```

---

## 9. Source Metadata Schema

```typescript
interface SourceMetadata {
  provider: string;         // "hyperliquid" | "drift"
  endpoint: string;         // API endpoint used
  fetched_at: number;       // When data was fetched (ms)
  metrics_provided: string[]; // Which metrics came from this source
}
```

---

## 10. Python Pydantic Models

```python
from enum import Enum
from typing import Optional, Dict, List
from pydantic import BaseModel
from datetime import datetime

class MetricStatus(str, Enum):
    REAL = "REAL"
    PROXY = "PROXY"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"

class FundingRegime(str, Enum):
    EXTREME_POSITIVE = "extreme_positive"
    ELEVATED_POSITIVE = "elevated_positive"
    NEUTRAL = "neutral"
    ELEVATED_NEGATIVE = "elevated_negative"
    EXTREME_NEGATIVE = "extreme_negative"

class OIRegime(str, Enum):
    BUILD = "build"
    UNWIND = "unwind"
    FLAT = "flat"

class VolumeRegime(str, Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

class TrendRegime(str, Enum):
    STRONG_TREND = "strong_trend"
    WEAK_TREND = "weak_trend"
    RANGE = "range"

class MarketCondition(str, Enum):
    TRENDING_HEALTHY = "trending_healthy"
    SQUEEZE_RISK = "squeeze_risk"
    CAPITULATION = "capitulation"
    CHOPPY = "choppy"
    UNKNOWN = "unknown"

class MetricAvailability(BaseModel):
    metric: str
    status: MetricStatus
    source: Optional[str] = None
    last_updated: Optional[int] = None
    note: Optional[str] = None

class FundingHorizons(BaseModel):
    now: float
    h8: float  # "8h"
    h24: float  # "24h"
    d3: float  # "3d"
    d7: float  # "7d"

class FundingData(BaseModel):
    horizons: FundingHorizons
    annualized_24h: float
    regime: FundingRegime
    source: Dict

class HorizonValue(BaseModel):
    value: float
    delta_pct: float
    delta_usd: float

class OpenInterestData(BaseModel):
    horizons: Dict[str, HorizonValue]
    current_usd: float
    regime: OIRegime

class LiquidationWindow(BaseModel):
    longs_usd: float
    shorts_usd: float
    total_usd: float
    dominant_side: str

class LiquidationData(BaseModel):
    horizons: Dict[str, LiquidationWindow]
    source_note: Optional[str] = None
    method: str = "real"

class VolumeData(BaseModel):
    horizons: Dict[str, float]
    cvd: Optional[Dict[str, float]] = None
    cvd_method: Optional[str] = None
    avg_7d_daily: float
    regime: VolumeRegime

class OrderbookDepth(BaseModel):
    bid_1pct_usd: float
    ask_1pct_usd: float
    bid_2pct_usd: float
    ask_2pct_usd: float

class OrderbookData(BaseModel):
    spread_bps: float
    spread_usd: float
    depth: OrderbookDepth
    imbalance_1pct: float
    best_bid: float
    best_ask: float
    mid_price: float
    microstructure: Optional[Dict[str, Any]] = None
    book_age_ms: int

class RegimeSummary(BaseModel):
    funding: FundingRegime
    oi: OIRegime
    volume: VolumeRegime
    trend: TrendRegime
    market_condition: MarketCondition
    confidence: str
    confidence_note: Optional[str] = None

class SourceMetadata(BaseModel):
    provider: str
    endpoint: str
    fetched_at: int
    metrics_provided: List[str]

class MarketSnapshot(BaseModel):
    venue: str
    symbol: str
    ts: int
    data_age_ms: int
    available_metrics: List[MetricAvailability]
    funding: Optional[FundingData] = None
    oi: Optional[OpenInterestData] = None
    liquidations: Optional[LiquidationData] = None
    volume: Optional[VolumeData] = None
    orderbook: Optional[OrderbookData] = None
    regimes: RegimeSummary
    sources: List[SourceMetadata]
```

---

## 11. Example Snapshot

```json
{
  "venue": "hyperliquid",
  "symbol": "BTC-PERP",
  "ts": 1737475200000,
  "data_age_ms": 150,
  "available_metrics": [
    {"metric": "funding", "status": "REAL", "source": "hyperliquid"},
    {"metric": "oi", "status": "REAL", "source": "hyperliquid"},
    {"metric": "orderbook", "status": "REAL", "source": "hyperliquid"},
    {"metric": "liquidations", "status": "PROXY", "note": "Estimated from OI deltas"},
    {"metric": "volume", "status": "REAL", "source": "hyperliquid"}
  ],
  "funding": {
    "horizons": {
      "now": 0.00003125,
      "8h": 0.00009375,
      "24h": 0.00028125,
      "3d": 0.00084375,
      "7d": 0.00196875
    },
    "annualized_24h": 0.1027,
    "regime": "neutral",
    "source": {
      "provider": "hyperliquid",
      "endpoint": "/info",
      "raw_rate": 0.00003125
    }
  },
  "oi": {
    "horizons": {
      "5m": {"value": 1316000000, "delta_pct": 0.05, "delta_usd": 658000},
      "1h": {"value": 1310000000, "delta_pct": 0.5, "delta_usd": 6580000},
      "4h": {"value": 1300000000, "delta_pct": 1.2, "delta_usd": 15792000},
      "24h": {"value": 1280000000, "delta_pct": 2.8, "delta_usd": 36848000}
    },
    "current_usd": 1316658000,
    "regime": "build"
  },
  "liquidations": {
    "horizons": {
      "5m": {"longs_usd": 0, "shorts_usd": 0, "total_usd": 0, "dominant_side": "balanced"},
      "1h": {"longs_usd": 125000, "shorts_usd": 75000, "total_usd": 200000, "dominant_side": "longs"},
      "4h": {"longs_usd": 500000, "shorts_usd": 300000, "total_usd": 800000, "dominant_side": "longs"},
      "24h": {"longs_usd": 2500000, "shorts_usd": 1500000, "total_usd": 4000000, "dominant_side": "longs"}
    },
    "source_note": "PROXY: estimated from OI deltas",
    "method": "oi_delta_proxy"
  },
  "volume": {
    "horizons": {
      "5m": 12500000,
      "15m": 35000000,
      "1h": 125000000,
      "4h": 450000000,
      "24h": 1523456789
    },
    "cvd": {
      "5m": 250000,
      "1h": -1500000,
      "24h": 5000000
    },
    "cvd_method": "candle_proxy",
    "avg_7d_daily": 1200000000,
    "regime": "normal"
  },
  "orderbook": {
    "spread_bps": 0.38,
    "spread_usd": 4.0,
    "depth": {
      "bid_1pct_usd": 15000000,
      "ask_1pct_usd": 14500000,
      "bid_2pct_usd": 35000000,
      "ask_2pct_usd": 33000000
    },
    "imbalance_1pct": 0.017,
    "best_bid": 105248.00,
    "best_ask": 105252.00,
    "mid_price": 105250.00,
    "book_age_ms": 150
  },
  "regimes": {
    "funding": "neutral",
    "oi": "build",
    "volume": "normal",
    "trend": "weak_trend",
    "market_condition": "trending_healthy",
    "confidence": "medium",
    "confidence_note": "Liquidations are proxy-based"
  },
  "sources": [
    {
      "provider": "hyperliquid",
      "endpoint": "/info (metaAndAssetCtxs)",
      "fetched_at": 1737475199850,
      "metrics_provided": ["funding", "oi", "volume"]
    },
    {
      "provider": "hyperliquid",
      "endpoint": "/info (l2Book)",
      "fetched_at": 1737475199900,
      "metrics_provided": ["orderbook"]
    }
  ]
}
```

---

## 12. Validation Rules

### 12.1 Required Fields

- `venue`, `symbol`, `ts`, `data_age_ms`, `available_metrics`, `regimes` are always required
- Individual metric objects are optional but if present must be complete

### 12.2 Consistency Checks

1. Every metric in snapshot MUST have entry in `available_metrics`
2. If `available_metrics[x].status == "UNAVAILABLE"`, corresponding data MUST be null
3. `data_age_ms` MUST equal max age of all included metrics
4. `regimes` MUST be computed from available data only (no guessing)

### 12.3 Staleness Thresholds

| Metric | Stale After |
|--------|-------------|
| orderbook | 5,000 ms |
| oi | 30,000 ms |
| volume | 30,000 ms |
| funding | 60,000 ms |
| liquidations | 60,000 ms |

---

*Last updated: 2026-01-21*
*Phase: 3B — Market Data Expansion*
