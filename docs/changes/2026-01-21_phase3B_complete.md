# Phase 3B Complete - Market Data Expansion

**Date:** 2026-01-21
**Phase:** 3B (All Sub-phases: 3B.0 through 3B.7)

## Summary

Phase 3B delivers a complete market data pipeline with real-time funding, OI, volume, orderbook data, and regime detection. The pipeline supports multiple venues with truthful data sourcing (REAL/PROXY/UNAVAILABLE badges) and integrates with the Cockpit UI.

| Sub-Phase | Description | Status |
|-----------|-------------|--------|
| 3B.0 | Provider Discovery | ✅ Complete |
| 3B.1 | MarketSnapshot Contract | ✅ Complete |
| 3B.2 | Ingestion Pipeline | ✅ Complete |
| 3B.3 | Persistence Strategy | ✅ Complete |
| 3B.4 | State API Endpoints | ✅ Complete |
| 3B.5 | Regime Engine | ✅ Complete |
| 3B.6 | UI Wiring | ✅ Complete |
| 3B.7 | Testing & Verification | ✅ Complete |

---

## Phase 3B.0: Provider Discovery

### Provider Matrix Documentation
**File:** `docs/providers/MARKET_PROVIDER_MATRIX.md`

Comprehensive documentation of data availability:
- Hyperliquid: funding, OI, volume, orderbook (✅ REAL)
- Drift: funding, OI (✅ REAL), liquidations (PROXY)
- Liquidation data marked as PROXY (estimated from OI deltas)

### Sample Payloads
**Directory:** `docs/samples/market/`

Captured API responses for offline development:
- `hyperliquid_metaAndAssetCtxs.json` - Context data with funding, OI, volume
- `hyperliquid_l2Book.json` - Orderbook depth
- `hyperliquid_fundingHistory.json` - Historical funding rates
- `drift_contracts.json` - Contract specifications
- `drift_fundingRates.json` - Funding rate data

---

## Phase 3B.1: MarketSnapshot Contract

### Contract Definition
**File:** `docs/contracts/MARKET_CONTRACT.md`

Canonical schema for market data:
- Venue/symbol identification (canonical format: `BTC-PERP`)
- Multi-horizon windows (5m, 15m, 1h, 4h, 24h, 7d)
- Metric availability tracking with truthfulness badges

### Symbol Normalization
**File:** `docs/contracts/SYMBOL_NORMALIZATION.md`

Mapping rules for venue-specific symbols:
- Hyperliquid: `BTC` → `BTC-PERP`
- Drift: `BTC-PERP` → `BTC-PERP`

---

## Phase 3B.2: Ingestion Pipeline

### Market Data Service
**Directory:** `services/market-data/`

New microservice for market data aggregation:

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI service with health, snapshots endpoints |
| `app/models.py` | Pydantic models for MarketSnapshot, enums |
| `app/processors/normalizer.py` | Raw → Normalized event transformation |
| `app/processors/snapshotter.py` | Event → Snapshot aggregation |
| `app/providers/hyperliquid.py` | Hyperliquid API integration |
| `app/providers/drift.py` | Drift API integration |
| `app/rate_limiter.py` | Rate limiting with backoff/jitter |
| `app/store.py` | Redis storage layer |

### Normalizer Features
- Staleness threshold detection per metric type
- MetricStatus classification (REAL/PROXY/UNAVAILABLE/STALE)
- Source metadata tracking
- Proxy liquidation estimation from OI deltas

### Snapshotter Features
- Rolling window storage (7-day retention)
- Multi-horizon aggregations
- Regime change detection with alert generation
- Confidence scoring based on data availability

---

## Phase 3B.3: Persistence Strategy

### Architecture Documentation
**File:** `docs/architecture/market_storage.md`

Storage strategy:
- Redis for hot data (snapshots, recent timeseries)
- PostgreSQL for alerts and long-term storage
- 7-day rolling window for historical data

### Redis Store Implementation
**File:** `services/market-data/app/store.py`

- Snapshot caching with TTL
- Alert persistence
- Timeseries storage with window pruning

---

## Phase 3B.4: State API Endpoints

### New Endpoints
**File:** `services/state-api/app/main.py`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/state/market/snapshots` | GET | All current snapshots |
| `/state/market/snapshot` | GET | Single snapshot by venue/symbol |
| `/state/market/timeseries` | GET | Historical data for metric |
| `/state/market/alerts` | GET | Recent market alerts |
| `/state/market/status` | GET | Provider status |

### Response Formats
Snapshots include full MarketSnapshot schema with:
- `available_metrics` array with status badges
- `regimes` summary (funding, OI, volume, trend, condition)
- `sources` array with provider metadata

---

## Phase 3B.5: Regime Engine

### Regime Classifications
**File:** `services/market-data/app/models.py`

| Regime Type | Values |
|-------------|--------|
| FundingRegime | extreme_positive, elevated_positive, neutral, elevated_negative, extreme_negative |
| OIRegime | build, unwind, flat |
| VolumeRegime | high, normal, low |
| TrendRegime | strong_trend, weak_trend, range |
| MarketCondition | trending_healthy, squeeze_risk, capitulation, choppy, unknown |

### Classification Logic
**File:** `services/market-data/app/processors/snapshotter.py`

- Funding: Based on annualized rate (>50% = extreme, >20% = elevated)
- OI: Based on 24h/4h delta percentages (>3% build, <-3% unwind)
- Volume: Based on 7-day average ratio (>2x = high, <0.5x = low)
- Market Condition: Composite of funding + OI + volume signals

### Alert Generation
Alerts triggered on:
- Regime changes (funding, OI, volume, trend)
- Extreme values
- Data staleness

---

## Phase 3B.6: UI Wiring

### Market Page
**File:** `services/cockpit-ui/src/pages/Market.tsx`

Full market data dashboard with:
- Asset cards showing funding, OI, volume, orderbook
- MetricStatusBadge component (REAL/PROXY/UNAVAILABLE colors)
- Regime summary display
- Provider status indicators
- Data freshness tracking

### Overview Updates
**File:** `services/cockpit-ui/src/pages/Overview.tsx`

- **HTF Thesis**: Replaced static BTC/ETH bias with real regime data
  - Funding regime from `snapshot.regimes.funding`
  - OI regime from `snapshot.regimes.oi`
  - Trend regime from `snapshot.regimes.trend`
  - Dynamic color coding based on regime
- **Market Data Providers**: Replaced static venue liquidity with real provider status

### Opportunity Detail Updates
**File:** `services/cockpit-ui/src/pages/OpportunityDetail.tsx`

- **Market Context Panel**: New section after Evidence Trail
  - Funding regime + current rate
  - OI regime + current value
  - Volume regime
  - Spread in bps
  - MetricStatusBadge for each metric

### Logs Updates
**File:** `services/cockpit-ui/src/pages/Logs.tsx`

- **Market Alerts Tab**: Third tab added to Decisions/Orders
  - Time, Symbol, Alert Type, Metric, Change, Venue columns
  - Color-coded alert types (regime_change = blue, extreme = red)
  - Alert count badge on tab

### API Hooks
**File:** `services/cockpit-ui/src/api/hooks/useMarketData.ts`

| Hook | Purpose |
|------|---------|
| `useMarketSnapshots()` | All current snapshots |
| `useMarketSnapshot(venue, symbol)` | Single snapshot |
| `useMarketTimeseries(venue, symbol, metric, window)` | Historical data |
| `useMarketAlerts(limit)` | Recent alerts |
| `useMarketStatus()` | Provider status |

### Types
**File:** `services/cockpit-ui/src/api/types.ts`

Added 15+ TypeScript interfaces:
- `MarketSnapshot`, `MarketAlert`, `MarketDataStatus`
- `MetricStatus`, `MetricAvailability`
- `FundingData`, `FundingHorizons`, `OpenInterestData`
- `VolumeData`, `OrderbookData`, `LiquidationData`
- `RegimeSummary`, `HorizonValue`

---

## Phase 3B.7: Testing & Verification

### Fixture Runner
**File:** `services/market-data/tests/fixture_runner.py`

Offline testing script that:
1. Loads sample payloads from `docs/samples/market/`
2. Parses Hyperliquid response format
3. Normalizes through MarketNormalizer
4. Processes through MarketSnapshotter
5. Verifies truthfulness badges
6. Tests regime change detection

Usage:
```bash
python -m tests.fixture_runner
```

### Rate Limiter Tests
**File:** `services/market-data/tests/test_rate_limits.py`

Unit tests covering:
- Initial state verification
- Minimum interval calculation
- Backoff on rate limit (doubles, capped at 10x)
- Recovery on success (0.9x reduction)
- Registry behavior
- Global rate limiter configuration

Usage:
```bash
pytest tests/test_rate_limits.py -v
```

---

## Verification Commands

```bash
# Build and run full stack
docker compose -f ops/compose.full.yml up --build

# Verify market-data service
curl http://localhost:8005/healthz
curl http://localhost:8005/snapshots

# Verify state-api proxy
curl http://localhost:8002/state/market/snapshots
curl http://localhost:8002/state/market/alerts

# Run fixture test
docker compose exec market-data python -m tests.fixture_runner

# Run unit tests
docker compose exec market-data pytest tests/ -v
```

---

## Files Changed (Phase 3B Complete)

### Created
| File | Description |
|------|-------------|
| `docs/providers/MARKET_PROVIDER_MATRIX.md` | Provider capability matrix |
| `docs/contracts/MARKET_CONTRACT.md` | MarketSnapshot schema |
| `docs/contracts/SYMBOL_NORMALIZATION.md` | Symbol mapping rules |
| `docs/architecture/market_storage.md` | Storage strategy |
| `docs/architecture/phase3B_dataflow.md` | Data flow diagram |
| `docs/samples/market/*.json` | Sample API responses |
| `services/market-data/` | Complete market data service |
| `services/market-data/app/models.py` | Pydantic models |
| `services/market-data/app/processors/normalizer.py` | Data normalizer |
| `services/market-data/app/processors/snapshotter.py` | Snapshot builder |
| `services/market-data/app/providers/hyperliquid.py` | Hyperliquid provider |
| `services/market-data/app/providers/drift.py` | Drift provider |
| `services/market-data/app/rate_limiter.py` | Rate limiting |
| `services/market-data/app/store.py` | Redis storage |
| `services/market-data/tests/fixture_runner.py` | Offline testing |
| `services/market-data/tests/test_rate_limits.py` | Unit tests |
| `services/cockpit-ui/src/api/hooks/useMarketData.ts` | React hooks |

### Modified
| File | Changes |
|------|---------|
| `services/state-api/app/main.py` | Market data proxy endpoints |
| `services/cockpit-ui/src/api/types.ts` | Market data TypeScript types |
| `services/cockpit-ui/src/api/hooks/index.ts` | Hook exports |
| `services/cockpit-ui/src/pages/Market.tsx` | Full market dashboard |
| `services/cockpit-ui/src/pages/Overview.tsx` | Real HTF thesis + provider status |
| `services/cockpit-ui/src/pages/OpportunityDetail.tsx` | Market Context panel |
| `services/cockpit-ui/src/pages/Logs.tsx` | Market Alerts tab |
| `ops/compose.full.yml` | market-data service definition |

---

## API Dependencies

### New Endpoints
- `GET /state/market/snapshots` - All market snapshots
- `GET /state/market/snapshot?venue={}&symbol={}` - Single snapshot
- `GET /state/market/timeseries?venue={}&symbol={}&metric={}&window={}` - Historical
- `GET /state/market/alerts?limit={}` - Market alerts
- `GET /state/market/status` - Provider status

### External APIs
- Hyperliquid: `https://api.hyperliquid.xyz/info`
- Drift: (future integration)

---

## What's Next

### Phase 3C: Scoring Upgrades
- [ ] Liquidity/slippage guards in fusion scoring
- [ ] Regime shift detection integration
- [ ] Exposure-aware scoring adjustments

### Phase 4: AI & RAG
- [ ] AI Copilot integration
- [ ] Sources/RAG knowledge base
- [ ] Natural language trade explanations

---

## Known Issues Addressed

| Issue | Status | Resolution |
|-------|--------|------------|
| Static HTF Thesis in Overview | ✅ Fixed | Real regime data from market snapshots |
| No market context in opportunity detail | ✅ Fixed | Market Context panel added |
| No market alerts visibility | ✅ Fixed | Logs page Market Alerts tab |
| Missing truthfulness indicators | ✅ Fixed | REAL/PROXY/UNAVAILABLE badges |

---

*Phase 3B is 100% complete. Ready to proceed to Phase 3C.*
