# Phase 3C Implementation Context

## Overview

This document captures the key code locations and architecture for Phase 3C implementation, which includes:
- Market Microstructure Derivation (liquidity heatmap, slippage guards)
- Scoring Upgrade (policy + structure aware)
- Risk Guardian Extensions (spread/slippage guardrails)
- Liquidity Heatmap UI
- Macro Feed MVP

---

## 1. Key Code Locations

### 1.1 Scoring Pipeline

| Component | File Path | Line Numbers | Purpose |
|-----------|-----------|--------------|---------|
| Core Scorer | `services/core-scorer/app/main.py` | 55-101 | `calculate_score()` - computes bias from events |
| Score Save | `services/core-scorer/app/main.py` | 130-168 | `save_signal()` - persists to DB + Redis |
| Fusion Worker | `services/fusion-engine/app/worker.py` | 23-77 | `process_message()` - converts signals to opportunities |
| Fusion DB | `services/fusion-engine/app/db.py` | 18-39 | `insert_opportunity()` - idempotent persistence |
| State API | `services/state-api/app/main.py` | 593-640 | `GET /state/opportunities` - retrieval endpoint |
| UI Metrics | `services/cockpit-ui/src/utils/metrics.ts` | 7-46 | `calculateBiasStrength()`, `calculateQuality()` |

### 1.2 Market Snapshot Shaping

| Component | File Path | Purpose |
|-----------|-----------|---------|
| Models | `services/market-data/app/models.py` | MarketSnapshot, RegimeSummary, OrderbookData, etc. |
| Normalizer | `services/market-data/app/processors/normalizer.py` | `MarketNormalizer` - transforms raw data |
| Snapshotter | `services/market-data/app/processors/snapshotter.py` | `MarketSnapshotter` - aggregates into snapshots |
| Store | `services/market-data/app/store.py` | `RedisStore` - persistence layer |
| Main Loop | `services/market-data/app/main.py` | Polling loops for context/orderbook/funding |
| State API | `services/state-api/app/main.py` | Lines 1092-1117: Market endpoints |
| Normalize Utils | `services/state-api/app/normalize.py` | `normalize_symbol()`, `normalize_venue()` |

### 1.3 Orderbook Ingestion

| Component | File Path | Purpose |
|-----------|-----------|---------|
| Hyperliquid Source | `services/ingest-gateway/sources/hyperliquid.py` | Polls HL API (metaAndAssetCtxs) |
| Drift Source | `services/ingest-gateway/sources/drift.py` | Polls Drift API (/contracts) |
| HL Provider | `services/market-data/app/providers/hyperliquid.py` | `fetch_orderbook()` via l2Book |
| Drift Provider | `services/market-data/app/providers/drift.py` | `fetch_orderbook()` via DLOB |
| Base Interface | `services/market-data/app/providers/base.py` | `BaseProvider` abstract class |
| DB Insert | `services/ingest-gateway/app/db.py` | `insert_event()` - Postgres + Redis |
| Normalizer | `services/market-data/app/processors/normalizer.py` | `normalize_orderbook()` |

### 1.4 Risk Guardian Enforcement

| Component | File Path | Line Numbers | Purpose |
|-----------|-----------|--------------|---------|
| Risk Engine | `services/state-api/app/risk.py` | All | `RiskGuardian`, `ReasonCode`, `RiskVerdict` |
| Preview | `services/state-api/app/main.py` | 759-853 | `POST /actions/preview` |
| Execute | `services/state-api/app/main.py` | 922-1086 | `POST /actions/execute` |
| Risk Limits | `services/state-api/app/main.py` | 887-920 | `GET /state/risk/limits` |
| Tests | `services/state-api/tests/test_main.py` | 127-155 | Risk blocking tests |

### 1.5 UI Market Page Components

| Component | File Path | Purpose |
|-----------|-----------|---------|
| Market Page | `services/cockpit-ui/src/pages/Market.tsx` | Main market dashboard with 6-panel layout |
| Overview Page | `services/cockpit-ui/src/pages/Overview.tsx` | Trading command center |
| Opportunity Detail | `services/cockpit-ui/src/pages/OpportunityDetail.tsx` | Single opportunity view + execution |
| Preview Panel | `services/cockpit-ui/src/components/PreviewPanel.tsx` | Risk verdict display |
| Risk Badge | `services/cockpit-ui/src/components/RiskBadge.tsx` | ALLOWED/BLOCKED indicator |
| Status Badge | `services/cockpit-ui/src/components/StatusBadge.tsx` | Status color indicator |
| Evidence Trail | `services/cockpit-ui/src/components/EvidenceTrail.tsx` | Audit log |

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤

INGESTION LAYER
┌─────────────────┐     ┌─────────────────┐
│   Hyperliquid   │     │      Drift      │
│ metaAndAssetCtxs│     │   /contracts    │
│ l2Book endpoint │     │  DLOB server    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌────────────────────────────────────────────┐
│           ingest-gateway                   │
│  sources/hyperliquid.py, sources/drift.py  │
│  ┌────────────────────────────────────┐    │
│  │  NormalizedEvent (market_snapshot) │    │
│  │  - mark, funding, OI, volume       │    │
│  └────────────────────────────────────┘    │
└────────────────────┬───────────────────────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│    PostgreSQL   │     │  Redis Streams  │
│  events table   │     │  x:events.norm  │
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
NORMALIZATION LAYER
┌────────────────────────────────────────────┐
│           market-data service              │
│  providers/ → processors/normalizer.py     │
│  ┌────────────────────────────────────┐    │
│  │  normalize_context()               │    │
│  │  normalize_orderbook() ─────────────────┼──► [Phase 3C: Add microstructure]
│  │  - spread_bps, depth, imbalance    │    │
│  └────────────────────────────────────┘    │
└────────────────────┬───────────────────────┘
                     │
                     ▼
SNAPSHOT LAYER
┌────────────────────────────────────────────┐
│       processors/snapshotter.py            │
│  ┌────────────────────────────────────┐    │
│  │  MarketSnapshotter.build_snapshot()│    │
│  │  - funding, OI, volume, orderbook  │    │
│  │  - regime classification           │────────► [Phase 3C: Add microstructure
│  │  - alert generation                │    │     depth_usd, impact_est,
│  └────────────────────────────────────┘    │     liquidity_score, book_heatmap]
└────────────────────┬───────────────────────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  Redis Store    │     │  Market Alerts  │
│  snapshots:*    │     │  regime changes │
└────────┬────────┘     └─────────────────┘
         │
         ▼
SCORING LAYER
┌────────────────────────────────────────────┐
│           core-scorer service              │
│  ┌────────────────────────────────────┐    │
│  │  calculate_score(events)           │    │
│  │  - TradingView bias: ±1.0          │    │
│  │  - Funding/OI regime: ±2.0         │────────► [Phase 3C: Add microstructure
│  │  - Clamp to [-10, 10]              │    │     penalties, exposure aware]
│  └────────────────────────────────────┘    │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│           fusion-engine service            │
│  ┌────────────────────────────────────┐    │
│  │  process_message()                 │    │
│  │  - Filter: |score| >= threshold    │    │
│  │  - Create opportunity with bias,   │────────► [Phase 3C: Add score_breakdown
│  │    quality, dir, links, ttl        │    │     execution_risk, warnings[]]
│  └────────────────────────────────────┘    │
└────────────────────┬───────────────────────┘
                     │
                     ▼
API LAYER
┌────────────────────────────────────────────┐
│            state-api service               │
│  ┌────────────────────────────────────┐    │
│  │  GET /state/market/snapshot        │    │
│  │  GET /state/opportunities          │    │
│  │  GET /state/evidence               │    │
│  │  POST /actions/preview ────────────────────► [Phase 3C: New block codes
│  │  POST /actions/execute             │    │     SPREAD_TOO_WIDE, etc.]
│  └────────────────────────────────────┘    │
│                                            │
│  RiskGuardian.check() ─────────────────────────► [Phase 3C: Microstructure
│  - killswitch, DNT, staleness             │     threshold enforcement]
│  - quality, leverage, positions           │
└────────────────────┬───────────────────────┘
                     │
                     ▼
UI LAYER
┌────────────────────────────────────────────┐
│            cockpit-ui (React)              │
│  ┌────────────────────────────────────┐    │
│  │  pages/Market.tsx ──────────────────────────► [Phase 3C: Liquidity panel,
│  │  - FundingPanel, OIPanel, etc.     │    │     heatmap visualization]
│  │  pages/Overview.tsx ────────────────────────► [Phase 3C: Execution strip,
│  │  - Metrics strip, HTF thesis       │    │     macro panel]
│  │  pages/OpportunityDetail.tsx ───────────────► [Phase 3C: Execution risk
│  │  - Preview, Execute controls       │    │     box, guardrail display]
│  └────────────────────────────────────┘    │
└────────────────────────────────────────────┘
```

---

## 3. Current Data Shapes

### MarketSnapshot (current)

```json
{
  "venue": "hyperliquid",
  "symbol": "BTC-PERP",
  "ts": "2025-01-22T00:00:00Z",
  "data_age_ms": 1234,
  "available_metrics": ["funding", "oi", "volume", "orderbook"],
  "funding": {
    "current": 0.0001,
    "annualized": 0.876,
    "horizons": { "8h": 0.0001, "24h": 0.00012 },
    "regime": "neutral",
    "status": "REAL"
  },
  "oi": {
    "total_usd": 1234567890,
    "deltas": { "5m": 0.1, "1h": 0.5, "4h": 1.2, "24h": 2.5 },
    "regime": "build",
    "status": "REAL"
  },
  "volume": {
    "24h_usd": 987654321,
    "regime": "normal",
    "status": "REAL"
  },
  "orderbook": {
    "spread_bps": 0.5,
    "spread_usd": 0.50,
    "depth": {
      "bid_1pct_usd": 5000000,
      "ask_1pct_usd": 4800000,
      "bid_2pct_usd": 12000000,
      "ask_2pct_usd": 11500000
    },
    "imbalance_1pct": 0.02,
    "best_bid": 99950,
    "best_ask": 100000,
    "mid_price": 99975,
    "status": "REAL"
  },
  "regimes": {
    "funding": "neutral",
    "oi": "build",
    "volume": "normal",
    "trend": "range",
    "market_condition": "choppy"
  }
}
```

### Phase 3C Additions to MarketSnapshot

```json
{
  "microstructure": {
    "spread_bps": 0.5,
    "mid_price": 99975,
    "depth_usd": {
      "10bp": 500000,
      "25bp": 1500000,
      "50bp": 5000000
    },
    "impact_est_bps": {
      "1000": 0.2,
      "5000": 1.1,
      "10000": 2.5
    },
    "liquidity_score": 0.85,
    "book_heatmap": {
      "levels": [
        { "price": 99950, "side": "bid", "size_usd": 120000 },
        { "price": 99900, "side": "bid", "size_usd": 250000 },
        { "price": 100000, "side": "ask", "size_usd": 180000 },
        { "price": 100050, "side": "ask", "size_usd": 300000 }
      ]
    }
  },
  "available_metrics": [
    "funding:real",
    "oi:real",
    "volume:real",
    "orderbook:real",
    "microstructure:derived"
  ]
}
```

---

## 4. Configuration Reference

### Environment Variables (current)

| Variable | Service | Default | Purpose |
|----------|---------|---------|---------|
| `SCORING_INTERVAL` | core-scorer | 60 | Seconds between scoring cycles |
| `SYMBOLS` | core-scorer | BTC,ETH,SOL | Symbols to score |
| `OPPORTUNITY_THRESHOLD` | fusion-engine | 2.0 | Min score to create opportunity |
| `OPPORTUNITY_TTL_SECONDS` | fusion-engine | 900 | Opportunity expiration |
| `POLL_INTERVAL_ORDERBOOK` | market-data | 3000 | Orderbook poll interval (ms) |
| `POLL_INTERVAL_CONTEXT` | market-data | 5000 | Context poll interval (ms) |
| `EXECUTION_ENABLED` | state-api | true | Global execution gate |
| `MAX_LEVERAGE` | state-api | 5.0 | Maximum allowed leverage |
| `MIN_QUALITY` | state-api | 50.0 | Minimum quality score |

### Phase 3C New Config (to add)

| Variable | Service | Default | Purpose |
|----------|---------|---------|---------|
| `MAX_SPREAD_BPS` | state-api | 50.0 | Maximum spread to allow execution |
| `MIN_DEPTH_25BP_USD` | state-api | 100000 | Minimum depth at 25bps |
| `MAX_IMPACT_BPS_5K` | state-api | 25.0 | Maximum slippage for $5k order |
| `MIN_LIQUIDITY_SCORE` | state-api | 0.3 | Minimum liquidity score |
| `MARGIN_STRESS_THRESHOLD` | state-api | 0.8 | Margin utilization warning |

---

## 5. Related Documentation

- `docs/contracts/MARKET_CONTRACT.md` - Market snapshot API contract
- `docs/contracts/PREVIEW_CONTRACT.md` - Preview endpoint contract
- `docs/contracts/RISK_LIMITS.md` - Risk configuration
- `docs/SYSTEM_DESIGN.md` - Overall system architecture
- `docs/RUNBOOKS.md` - Operational procedures

---

## 6. Phase 3C Implementation Targets

### Backend Changes

1. **Microstructure Module** (`services/market-data/app/processors/microstructure.py`)
   - Compute `mid_price` from best bid/ask
   - Compute `spread_bps` from spread / mid price
   - Compute `depth_usd` at 10/25/50 bps slices via book walk
   - Compute `impact_est_bps` for 1k/5k/10k order sizes
   - Compute `liquidity_score` from depth + spread
   - Build compact heatmap (top 50 bid + 50 ask levels)

2. **Model Extensions** (`services/market-data/app/models.py`)
   - Add `MicrostructureData` model
   - Add `BookHeatmapLevel` model
   - Extend `MarketSnapshot` with `microstructure` field
   - Update `available_metrics` to include truthfulness labels

3. **Scoring Upgrade** (`services/core-scorer/app/main.py`, `services/fusion-engine/app/worker.py`)
   - Add microstructure penalty factors
   - Add exposure-aware scoring
   - Add `score_breakdown` to opportunities
   - Add `execution_risk` object
   - Add `warnings[]` array

4. **Risk Guardian Extensions** (`services/state-api/app/risk.py`)
   - Add `SPREAD_TOO_WIDE` reason code
   - Add `SLIPPAGE_TOO_HIGH` reason code
   - Add `DEPTH_TOO_THIN` reason code
   - Add `LIQUIDITY_TOO_LOW` reason code
   - Add `MARGIN_STRESS` reason code
   - Add `EXPOSURE_TOO_HIGH` reason code
   - Add threshold checks in `RiskGuardian.check()`

5. **Macro Feed MVP** (`services/ingest-gateway/app/macro.py`)
   - RSS feed fetching
   - Postgres storage (macro_feed table)
   - Simple keyword tagging
   - `GET /state/macro/feed` endpoint

### Frontend Changes

1. **Market Page** (`services/cockpit-ui/src/pages/Market.tsx`)
   - Add `LiquidityPanel` component
   - Add heatmap visualization (bar/table)
   - Add spread/depth/slippage badges
   - Add truthfulness labels (REAL/PROXY/UNAVAILABLE)

2. **Overview Page** (`services/cockpit-ui/src/pages/Overview.tsx`)
   - Add "Execution Conditions" strip
   - Add Macro Feed panel (RSS headlines)

3. **Opportunity Detail** (`services/cockpit-ui/src/pages/OpportunityDetail.tsx`)
   - Add "Execution Risk" box
   - Show spread/depth/impact for proposed size
   - Show risk guardian block reasons with explanations
