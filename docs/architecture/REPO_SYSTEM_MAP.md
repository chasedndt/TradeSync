# TradeSync — Repo & System Map

**Last Updated:** 2026-03-27
**Purpose:** Ground-truth map of the repository structure, services, runtime dependencies, and data flows.

---

## 1. Top-Level Repo Tree

```
TradeSync/
├── services/                   # All microservices
│   ├── state-api/              # REST hub (port 8000)
│   ├── ingest-gateway/         # Data ingestion (port 8080)
│   ├── core-scorer/            # Signal scoring loop (port 8001)
│   ├── fusion-engine/          # Signal → Opportunity (port 8002)
│   ├── market-data/            # Market data aggregation (port 8005)
│   ├── exec-drift-svc/         # Drift executor (port 8003)
│   ├── exec-hl-svc/            # Hyperliquid executor (port 8004)
│   ├── backtest-runner/        # Replay / backtest (port unassigned)
│   └── cockpit-ui/             # React frontend (port 3000)
│
├── libs/
│   └── tradesync_core/         # Shared Python library
│       └── tradesync_core/
│           ├── core_score.py   # calculate_score() — the actual scoring function
│           ├── scoring.py      # EnhancedScorer — microstructure + regime + exposure
│           ├── risk.py         # RiskGuardian — all trade validation checks
│           ├── contracts.py    # ScoreBreakdown, EnhancedScore, ExecutionRisk
│           └── __init__.py     # Exports: normalize_symbol, normalize_venue, RiskGuardian, EnhancedScorer
│
├── ops/
│   ├── compose.full.yml        # Full docker-compose (canonical)
│   ├── migrations/             # DB migration scripts
│   └── sql/
│       └── schema.sql          # Canonical DB schema
│
├── docs/                       # Documentation
│   ├── roadmap/
│   │   └── CANONICAL_ROADMAP.md
│   ├── architecture/           # System maps (this directory)
│   ├── changes/                # Handover notes per session
│   ├── contracts/              # Interface contracts (market, opportunity, preview)
│   ├── diagrams/               # PlantUML + exports
│   ├── samples/                # Real API response samples
│   └── runbooks/
│
├── data/
│   └── replay/                 # Backtesting scenarios
│
├── CLAUDE.md                   # AI session context (commands, architecture brief)
└── roadmap.md                  # OLD — superseded by docs/roadmap/CANONICAL_ROADMAP.md
```

---

## 2. Service Map

### 2a. Data Pipeline Services (left to right)

```
External APIs
  │  Hyperliquid /info (funding, OI, price, orderbook)
  │  Drift /contracts (funding, OI, volume)
  │  TradingView webhooks (bias signals)
  ▼
ingest-gateway (8080)
  │  Writes → events table (Postgres)
  │  Writes → x:events.norm (Redis stream)
  │  Maintains → ingest:source_mirror:{source} (Redis hash, 24h TTL)
  │  Background: poll_hyperliquid_markets() every 60s
  │              poll_drift_markets() every 10s
  ▼
core-scorer (8001)
  │  Reads → events table (last 30 min, per symbol)
  │  Calls → tradesync_core.calculate_score(events)
  │  Writes → signals table (Postgres)
  │  Writes → x:signals.funding (Redis stream)
  │  Runs → score_loop() every SCORING_INTERVAL (default 60s)
  ▼
fusion-engine (8002)
  │  Consumes → x:signals.funding (Redis consumer group "fusion-engine")
  │  Calls → market-data:8005/snapshot/{venue}/{symbol} (microstructure)
  │  Calls → tradesync_core.EnhancedScorer.compute_enhanced_score()
  │  Writes → opportunities table (Postgres)
  │  Background: recover_pending() on startup
```

### 2b. Market Data Service (parallel)

```
External APIs
  │  Hyperliquid: funding, OI, price (every 5s)
  │  Hyperliquid: orderbook (every 3s)
  │  Hyperliquid: funding history (every 5 min)
  │  Drift: contracts/funding/OI (every 5s)
  ▼
market-data (8005)
  │  Normalizes → MarketNormalizer (canonical event format)
  │  Snapshots → MarketSnapshotter (rolling windows, regime classification)
  │  Derives → MicrostructureDeriver (depth_usd, impact_est_bps, liquidity_score)
  │  Stores → snapshot:{venue}:{symbol} (Redis, latest snapshot)
  │  Stores → timeseries:{venue}:{symbol}:{metric} (Redis, historical)
  │  Writes → x:alerts (Redis stream, regime changes)
  │  Exposes → /snapshot/{venue}/{symbol}
  │             /snapshots (all)
  │             /timeseries/{venue}/{symbol}/{metric}
  │             /alerts
  │             /status
```

### 2c. State API — the hub (8000)

```
state-api (8000)
  │
  ├── Reads ←  Postgres (events, signals, opportunities, decisions, exec_orders, exposures)
  ├── Reads ←  Redis (circuit breakers, stream lengths, ingest source mirrors)
  ├── Calls →  market-data:8005 (snapshot, aggregate)
  ├── Calls →  exec-drift-svc:8003 (circuit-status, order)
  ├── Calls →  exec-hl-svc:8004 (circuit-status, order)
  ├── Calls →  ingest-gateway:8080 (ingest/sources via snapshot)
  │
  ├── Background: expire_stale_opportunities() every 60s
  │
  └── Exposes → All endpoints consumed by cockpit-ui
```

### 2d. Execution Services

```
exec-drift-svc (8003)
  │  Reads ← Redis (circuit breaker keys)
  │  Writes → Redis (idempotency cache, circuit breaker state)
  │  Writes → exec_orders table (via state-api after routing)
  │  DRY_RUN=true by default — no real signing implemented

exec-hl-svc (8004)
  │  Same pattern as exec-drift-svc
  │  Valid assets: BTC, ETH, SOL, ARB
  │  DRY_RUN=true by default — no real signing implemented
```

### 2e. Frontend

```
cockpit-ui (3000)
  │  React + TypeScript + Vite
  │  TanStack Query for all data fetching
  │  All API calls proxied: /api/* → state-api:8000/*
  │
  └── Pages: Overview, Opportunities, OpportunityDetail, Market,
             Execution, Positions, Sources (placeholder), Copilot (placeholder),
             Autonomy, Logs, RiskPolicies, Settings
```

---

## 3. Docker Compose Startup Order

```
1. postgres          → health: pg_isready
2. redis             → health: redis-cli ping
3. qdrant            → health: curl /readyz  (used by future RAG, idle now)
4. schema-init       → runs apply_schema.py; depends_on: postgres (healthy)
5. state-api         → depends_on: postgres, schema-init
6. ingest-gateway    → depends_on: postgres, redis, schema-init
7. core-scorer       → depends_on: postgres, redis, schema-init
8. market-data       → depends_on: redis
9. fusion-engine     → depends_on: postgres, redis, market-data
10. exec-drift-svc   → depends_on: redis
11. exec-hl-svc      → depends_on: redis
12. cockpit-ui       → depends_on: state-api (nginx static, /api proxy)
```

---

## 4. Database Schema

| Table | Owner | Purpose |
|-------|-------|---------|
| `events` | ingest-gateway writes, core-scorer reads | Raw market/signal events |
| `signals` | core-scorer writes, state-api reads | Scored directional signals |
| `opportunities` | fusion-engine writes, state-api reads/updates | Actionable trade setups |
| `decisions` | state-api writes on preview | Risk-reviewed trade plans |
| `exec_orders` | state-api writes on execute | Sent-to-venue orders |
| `exposures` | exec services update | Current position tracking |
| `regimes` | market-data writes (future) | Regime audit trail |
| `calibration_params` | backtest-runner (future) | ML calibration params |

**Key constraints:**
- `opportunities.signal_id` UNIQUE — one opportunity per signal
- `decisions` UNIQUE on `(opportunity_id, venue)` — one decision per opp/venue
- `exec_orders` UNIQUE on `decision_id` — one order per decision

---

## 5. Redis Key Map

| Key Pattern | Type | Written By | Read By | TTL |
|-------------|------|-----------|---------|-----|
| `x:events.norm` | Stream | ingest-gateway | core-scorer | No expiry |
| `x:signals.funding` | Stream | core-scorer | fusion-engine | No expiry |
| `x:opportunities` | Stream | fusion-engine (future) | monitoring | No expiry |
| `x:alerts` | Stream | market-data | monitoring | No expiry |
| `ingest:source_mirror:{source}` | Hash | ingest-gateway | state-api snapshot | 24h |
| `exec:idempo:{venue}:{key}` | String | exec services | exec services | 24h |
| `exec:failcount:{venue}` | String | exec services | exec services | No expiry |
| `exec:disabled:{venue}` | String | exec services | exec services | 600s (auto-expire) |
| `snapshot:{venue}:{symbol}` | String (JSON) | market-data | fusion-engine, state-api | No expiry |
| `timeseries:{venue}:{symbol}:{metric}` | List/String | market-data | state-api | No expiry |

---

## 6. External API Dependencies

| Service | External Target | Endpoint | Frequency |
|---------|----------------|----------|-----------|
| ingest-gateway | Hyperliquid | POST /info (metaAndAssetCtxs) | Every 60s |
| ingest-gateway | Drift | GET /contracts | Every 10s |
| ingest-gateway | TradingView | Webhook receiver | On-demand |
| market-data | Hyperliquid | POST /info (multiple methods) | 3–5s context, 3s book, 5min history |
| market-data | Drift | GET /contracts | Every 5s |
| exec-drift-svc | Drift RPC | JSON-RPC preflight | On order |
| exec-hl-svc | Hyperliquid Exchange | POST /exchange | On order |
| state-api | (internal only) | market-data, exec services | On demand |

---

## 7. Which Services Are Required Per Cockpit Page

| Page | Required Services | Optional / Graceful Degradation |
|------|------------------|--------------------------------|
| Overview | state-api, postgres | exec-drift-svc, exec-hl-svc (circuit status) |
| Opportunities | state-api, postgres | — |
| OpportunityDetail | state-api, postgres | — |
| Market | state-api, market-data | — (page shows UNAVAILABLE if market-data down) |
| Execution | state-api, postgres | exec-drift-svc or exec-hl-svc (for actual execution) |
| Positions | state-api, exec-drift-svc, exec-hl-svc | Falls back to exposures table |
| Sources | none (placeholder) | — |
| Copilot | none (placeholder) | — |
| Autonomy | state-api, exec-drift-svc, exec-hl-svc | Reads circuit status for readiness checks |
| Logs | state-api, postgres | — |
| RiskPolicies | state-api | — |
| Settings | none (localStorage) | — |

---

## 8. tradesync_core Library — Exported Interface

```python
from tradesync_core import (
    calculate_score,        # core_score.py — directional bias from events
    EnhancedScorer,         # scoring.py — microstructure + regime + exposure scoring
    compute_enhanced_score, # scoring.py — convenience wrapper
    RiskGuardian,           # risk.py — all trade validation checks
    normalize_symbol,       # symbol normalization (BTC → BTC-PERP, etc.)
    normalize_venue,        # venue normalization
    ScoreBreakdown,         # contracts.py — score breakdown dataclass
    EnhancedScore,          # contracts.py — full enhanced score result
    ExecutionRisk,          # contracts.py — execution risk flags
)
```

---

## 9. Port Reference

| Port | Service |
|------|---------|
| 3000 | cockpit-ui |
| 5432 | postgres |
| 6379 | redis |
| 6333 | qdrant |
| 8000 | state-api |
| 8001 | core-scorer |
| 8002 | fusion-engine |
| 8003 | exec-drift-svc |
| 8004 | exec-hl-svc |
| 8005 | market-data |
| 8080 | ingest-gateway |
