# TradeSync Route Inventory (Post-Step 0)

This document lists all active routes across the TradeSync microservices architecture.

## 1. state-api (Port 8000)
The central hub for system state and risk-guarded actions.

| Method | Path | Description | Tags |
| :--- | :--- | :--- | :--- |
| GET | `/state/health` | Aggregated health check (DB + Freshness) | health |
| GET | `/state/snapshot` | High-level system overview | state |
| GET | `/state/events/latest` | Latest normalized events (symbol/tf filter) | state |
| GET | `/state/signals/latest` | Latest bias/confidence signals | state |
| GET | `/state/opportunities` | Actionable trade candidates | state |
| GET | `/state/evidence` | Supporting data for an opportunity | state |
| GET | `/state/positions` | Aggregated positions across venues | state |
| GET | `/state/execution/status` | Circuit breaker & gate status | state |
| GET | `/state/risk/limits` | Current risk policy & counters | risk |
| POST | `/actions/preview` | Generate execution plan & risk check | actions |
| POST | `/actions/execute` | Commit decision to venue | actions |
| GET | `/healthz` | Liveness probe | system |

### Legacy Aliases (state-api)
| Method | Path | Canonical Successor |
| :--- | :--- | :--- |
| GET | `/opps` | `/state/opportunities` |
| GET | `/opps/{id}` | `/state/evidence?opportunity_id={id}` |
| POST | `/preview` | `/actions/preview` |
| POST | `/execute` | `/actions/execute` |
| GET | `/execution/status` | `/state/execution/status` |

## 2. ingest-gateway (Port 8080)
Handles data entry from external providers and internal pollers.

| Method | Path | Description |
| :--- | :--- | :--- |
| POST | `/ingest/tv` | TradingView Alert Webhook |
| GET | `/ingest/sources` | Metadata about active ingestion sources |
| POST | `/ingest/metrics` | Generic metrics ingestion |
| GET | `/healthz` | Health check |

## 3. fusion-engine (Port 8002)
Standardized confluence scoring engine.

| Method | Path | Description |
| :--- | :--- | :--- |
| GET | `/healthz` | Health check |

## 4. exec-drift-svc (Port 8003)
| Method | Path | Description |
| :--- | :--- | :--- |
| GET | `/healthz` | Health check |
| GET | `/exec/drift/preflight` | Drift-specific account readiness check |
| GET | `/exec/drift/circuit-status` | Internal circuit breaker status |
| GET | `/exec/drift/positions` | Raw Drift positions |
| POST | `/exec/drift/order` | Place a Drift order |

## 5. exec-hl-svc (Port 8004)
| Method | Path | Description |
| :--- | :--- | :--- |
| GET | `/healthz` | Health check |
| GET | `/exec/hl/preflight` | Hyperliquid account readiness check |
| GET | `/exec/hl/circuit-status` | Internal circuit breaker status |
| GET | `/exec/hl/positions` | Raw HL positions |
| POST | `/exec/hl/order` | Place a Hyperliquid order |

## 6. core-scorer (Port 8001)
| Method | Path | Description |
| :--- | :--- | :--- |
| GET | `/healthz` | Health check |
| GET | `/bias/latest` | Latest technical bias for symbol |
