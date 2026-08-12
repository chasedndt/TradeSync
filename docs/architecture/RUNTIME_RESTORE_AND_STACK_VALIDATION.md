# TradeSync: Runtime Restore and Stack Validation

**Last updated:** 2026-03-30

---

## ⚠️ Critical: --env-file .env Required

**Always include `--env-file .env` when running docker compose commands from the project root.**

The compose file is at `ops/compose.full.yml` (a subdirectory). Docker Compose V2 looks for `.env` relative to the compose file location, not the CWD. Without `--env-file .env`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` are blank, and services that connect to postgres will fail with `password authentication failed for user "root"`.

**Affected services (fail without --env-file):** `state-api`, `fusion-engine`, `core-scorer`, `ingest-gateway`

---

## New Machine Bring-Up Procedure

### Prerequisites

- Docker Desktop installed and running
- Git clone of the TradeSync repo
- Working directory: project root (parent of `ops/`, `services/`, `libs/`)

### Steps

```bash
# 1. Create .env from template
cp .env.example .env
# Edit .env — at minimum set POSTGRES_PASSWORD

# 2. Build and start all services (--env-file .env is REQUIRED)
docker compose -f ops/compose.full.yml --env-file .env up -d --build

# 3. Wait for infra health (postgres + redis + qdrant take ~10s on first start)
docker compose -f ops/compose.full.yml --env-file .env ps
# All services should show "healthy" or "running"

# 4. Verify DB schema was applied
docker compose -f ops/compose.full.yml --env-file .env exec postgres \
  psql -U tradesync -d tradesync -c "\dt"
# Expected: events, signals, opportunities, decisions, exec_orders, exposures, regimes, calibration_params
```

### Schema Application Mechanism

`compose.full.yml` mounts `./ops/sql:/docker-entrypoint-initdb.d:ro` on the postgres container.
Postgres runs all `.sql` files in that directory on **first start** (empty volume).

- On new machine: schema applied automatically.
- On existing volume: init scripts are skipped — schema already present.
- **`ops/scripts/bootstrap-db.ps1`** is for the `compose.infra.yml` (infra-only) stack only. Do NOT run it when using `compose.full.yml`.

---

## Live Smoke Tests

After bring-up, verify each layer:

```bash
BASE=http://localhost:8000

# 1. Liveness
curl -s $BASE/healthz | jq .
# Expected: {"ok": true}

# 2. State snapshot (cockpit overview data)
curl -s $BASE/state/snapshot | jq '{execution_gate, degraded, errors}'
# Expected: execution_gate=true/false, degraded=false (if all services up)

# 3. Opportunities (should be empty on fresh stack)
curl -s "$BASE/state/opportunities?status=new&limit=5" | jq length
# Expected: 0 (no opportunities yet)

# 4. Risk limits (verify env vars loaded)
curl -s $BASE/state/risk/limits | jq '{daily_notional_limit, account_equity_usd, max_leverage}'
# Expected: values from .env or defaults (50000.0, 50000.0, 5.0)

# 5. Positions (exec services may return empty in dry-run)
curl -s $BASE/state/positions | jq length
# Expected: 0 (dry-run, no real positions)

# 6. Execution status
curl -s $BASE/state/execution/status | jq .execution_enabled
# Expected: "true" (from compose.full.yml EXECUTION_ENABLED)

# 7. Cockpit UI
curl -s http://localhost:3000 | head -1
# Expected: <!doctype html> (nginx serving SPA)

# 8. Market data health
curl -s http://localhost:8005/healthz | jq .
# Expected: {"status": "ok"} or similar

# 9. Fusion engine health
curl -s http://localhost:8002/healthz | jq .
# Expected: {"status": "ok"}
```

---

## Service Dependency Map

```
postgres ──┐
           ├──► state-api (8000)
           ├──► core-scorer (8001)
           └──► fusion-engine (8002)

redis ─────┐
           ├──► state-api
           ├──► fusion-engine
           ├──► ingest-gateway (8080)
           └──► market-data (8005)

(no health dependency):
exec-drift-svc (8003)  ← state-api calls at preview time
exec-hl-svc (8004)     ← state-api calls at preview time

cockpit-ui (3000) ──► state-api (via nginx proxy /api/ → http://state-api:8000/)
```

**Notes:**

- `state-api` does NOT depend on exec services in `depends_on`. Position fetch failures are graceful (exposure defaults to 0).
- `ingest-gateway` depends only on `redis` (not postgres) in compose. If postgres is down, ingest will queue events in Redis streams but scorer won't process them.
- `backtest-runner` is in `profiles: [backtest]` — not started by default.

---

## Build Context Reference

All build contexts in `compose.full.yml` are relative to the compose file's location (`ops/`):

| Service | Context | Resolves to |
|---------|---------|-------------|
| state-api | `..` (project root) | Uses `Dockerfile` at `services/state-api/Dockerfile` |
| core-scorer | `..` | `services/core-scorer/Dockerfile` |
| fusion-engine | `..` | `services/fusion-engine/Dockerfile` |
| ingest-gateway | `..` | `services/ingest-gateway/Dockerfile` |
| exec-drift-svc | `../services/exec-drift-svc` | Service-local Dockerfile |
| exec-hl-svc | `../services/exec-hl-svc` | Service-local Dockerfile |
| market-data | `../services/market-data` | Service-local Dockerfile |
| cockpit-ui | `../services/cockpit-ui` | Service-local Dockerfile |

Services with `context: ..` (project root) install `libs/tradesync_core` as part of the Docker build. Services with service-local contexts do NOT use the shared library.

---

## Environment Variables Reference

| Var | Default | Used by | Notes |
|-----|---------|---------|-------|
| `POSTGRES_USER` | (required) | postgres, all services | Set in .env |
| `POSTGRES_PASSWORD` | (required) | postgres | Set in .env |
| `POSTGRES_DB` | tradesync | postgres, all services | |
| `REDIS_URL` | redis://redis:6379 | state-api, fusion-engine, ingest-gateway, market-data | |
| `EXECUTION_ENABLED` | false | state-api, exec services | Set to "true" in compose.full.yml for state-api |
| `ACCOUNT_EQUITY_USD` | 50000.0 | state-api, fusion-engine | Capital base for risk load calculation |
| `DAILY_NOTIONAL_LIMIT` | 50000.0 | state-api | Max daily order notional; 0 = disabled |
| `OPPORTUNITY_TTL_SECONDS` | 300 | state-api | TTL for stale opportunities |
| `MAX_EXPOSURE_PER_SYMBOL_USD` | 25000 | RiskGuardian | Per-symbol notional cap |
| `MARGIN_STRESS_THRESHOLD` | 0.8 | RiskGuardian | Account risk load threshold |
| `MIN_QUALITY` | 50.0 | RiskGuardian | Min opportunity quality score |
| `DRY_RUN` | true | exec services | Set to false for live execution (requires wallet keys) |

All risk params are readable from `GET /state/risk/limits`. None are writable via API — require env var update + service restart.
