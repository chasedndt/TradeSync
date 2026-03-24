RUNBOOKS.md

How to run, develop, test, and operate TradeSync v0.1 locally and in containers.

Audience: you (founder/dev), coding agents, CI, future contributors
Scope: local dev (Windows + PowerShell), containerized dev, seeds, health/metrics, common ops

0) Golden Path (first 60 minutes)

Clone & open

git clone <your_repo_url> TradeSync
cd TradeSync
code .


Create .env files (root + services)

Root .env

# --- Core infra ---
POSTGRES_URL=postgresql://ts:ts@localhost:5432/tradesync
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333

# --- Auth/keys (fill when you have them) ---
OPENAI_API_KEY=
DISCORD_WEBHOOK_URL=

# --- Feature flags ---
TS_ENABLE_RISK=1
TS_ENABLE_QDRANT=1


Service-specific .env (create inside each service folder as needed):

services/state-api/.env, services/ingest-gateway/.env, services/exec-hl-svc/.env, etc.
Use the same connection strings; add any service-only secrets (e.g., HL keys).

Start infra (option A: local tools)

Install Postgres, Redis, Qdrant locally (Windows installers or Docker Desktop).

Or use the containerized option below (recommended).

Start infra (option B: Docker Desktop – recommended)

# from repo root
docker compose -f ops/compose.infra.yml up -d


This brings up: postgres:5432, redis:6379, qdrant:6333.

Create virtual envs / node deps

# Python (for ingest-gateway, agents, fusion, risk-guardian, state-api)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Node (for exec-hl-svc)
cd services/exec-hl-svc
npm install
cd ..\..\   # back to repo root


Run migrations + seed config

# create DB schema (alembic) & seed baseline rows
powershell -ExecutionPolicy Bypass -File ops\scripts\bootstrap-db.ps1


Smoke test: up the core services (local processes)
Open three terminals:

T1 – state-api (Standardized Contract)

.\.venv\Scripts\Activate.ps1
uvicorn services.state-api.app.main:app --reload --port 8000


T2 – fusion-engine + ingest-gateway

.\.venv\Scripts\Activate.ps1
python services\ingest-gateway\app\main.py
python services\fusion-engine\app\main.py


T3 – executors

# Drift (python)
.\.venv\Scripts\Activate.ps1
python services\exec-drift-svc\app\main.py

# Hyperliquid (python)
.\.venv\Scripts\Activate.ps1
python services\exec-hl-svc\app\main.py


Ping health + metrics

Health: http://localhost:8000/state/health

Metrics (Prometheus): http://localhost:8000/metrics

Send a test TradingView webhook

$body = @{
  symbol="BTCUSDT"; timeframe="2h"; label="FVG close"; level=69250.0; alert_id=[guid]::NewGuid()
} | ConvertTo-Json
Invoke-RestMethod -Method POST -Uri http://localhost:8080/ingest/tv -Body $body -ContentType 'application/json'


Expect: Event → Signal(s) → Opportunity → /opps/latest shows data.

1) Service Inventory (what runs where)
Service	Lang	Port	Purpose
ingest-gateway	Py	8080	accept TV/ideas/metrics → x:events.*
core-scorer	Py	8001	produce technical bias & confidence
fusion-engine	Py	8002	merge signals → opportunities
state-api	Py	8000	REST: state, risk-guarded actions, telemetry
exec-drift-svc	Py	8003	Drift executor
exec-hl-svc	Py	8004	Hyperliquid executor
cockpit-ui	TS/JS	3000	Main management dashboard
Infra	—	—	Postgres, Redis Streams, Qdrant
2) Local Dev (per service)
Python services (common)
.\.venv\Scripts\Activate.ps1
export PYTHONPATH=$PWD  # use $env:PYTHONPATH on Windows if needed
uvicorn services.state_api.app:app --reload --port 8000
# or
python services\ingest-gateway\main.py


Hot-reload is enabled for uvicorn-based APIs.
Logs include trace_id propagated across services.

Node/TS (exec-hl-svc)
cd services/exec-hl-svc
npm run dev     # ts-node-dev / nodemon


HL keys go in services/exec-hl-svc/.env and never committed.

Cockpit UI (Dashboard)
cd services/cockpit-ui
npm install
npm run dev

3) Containerized Dev (one command)

Everything (infra + services):

docker compose -f ops/compose.full.yml up -d --build


Tail logs

docker compose -f ops/compose.full.yml logs -f state-api ingest-gateway exec-hl-svc


Stop

docker compose -f ops/compose.full.yml down


ops/compose.*.yml are minimal, documented templates; edit ports and resource limits as needed.

4) Environments & Config

Config precedence: service .env → root .env → env vars in shell.

Timeframes are canonicalized to ["1m","5m","15m","30m","1h","2h","4h","8h","1d"].

Feature flags: TS_ENABLE_RISK, TS_ENABLE_QDRANT.

5) Database, Migrations, Seeds

Migrations (Python/Alembic)

# create new migration after model change
alembic revision -m "add exposures idx"
alembic upgrade head


Baseline seed

powershell -ExecutionPolicy Bypass -File ops\scripts\bootstrap-db.ps1


Seeds regime defaults, risk policy, agent registry placeholders.

Indexes to verify (per ERD):

signals(symbol,timeframe,created_at)

events(hash UNIQUE)

exposures(venue,symbol UNIQUE)

6) Streams & Queues

Redis Streams names:

x:events.raw, x:events.norm, x:signals.*, x:opps, x:exec.orders

Consumer groups (examples):

redis-cli XGROUP CREATE x:events.norm agents $ MKSTREAM
redis-cli XGROUP CREATE x:signals.* fusion $ MKSTREAM


Backpressure: ingest returns 429 if lag > threshold.

7) Testing

Unit

pytest -q


Golden fixtures

tests/
  fixtures/tech/events/*.json
  golden/signals/tech/*.json


Reliability/Calibration job (offline)

python ops\jobs\run_calibration.py --days 30


Latency budgets: P95 < 50ms per Event per agent; verify in test output.

8) Health, Metrics, Tracing

Health: GET /state/health (Standardized)

Metrics: GET /state/snapshot (Internal stats)

Trace IDs: logged at ingest; propagated via headers to all downstream services.

8a) Step 0 Verification (API Contract)

To verify alias compatibility:
```bash
curl -I http://localhost:8000/opps
# Expect: 200 OK + Deprecation Header
```

To verify symbol normalization:
```bash
curl "http://localhost:8000/state/opportunities?symbol=BTCUSDT"
# Response should contain "symbol": "BTC-PERP"
```

9) Webhooks (TradingView & Ops)

TradingView alert endpoint: POST /ingest/tv
Payload is normalized; dedupe via hash.

Ops/Discord: services can post summaries to your webhook when set in env.

10) Security

Internal HMAC: X-TS-Signature = HMAC_SHA256(body, SECRET)

External UI: JWT (scopes read:opps, write:actions)

Secrets: never commit .env; consider doppler/vault later.

11) Common Workflows
A) Add a new audited TV alert source

Add to ingest-gateway allowlist.

Update config/agents/tech.yaml → input_filters.allow_payload_names.

Create test fixture & golden signal.

Redeploy agents.

B) Onboard a new metric from the provider

Extend metrics normalizer (kind, fields).

Add feature usage in funding agent.

Update calibration after a week.

C) Execute on Hyperliquid with Node service

Put HL keys in services/exec-hl-svc/.env.

Start exec-hl-svc and verify /healthz.

Preview → Execute from UI or curl /actions/execute.

12) Troubleshooting

No opportunities appear

Check x:events.norm is being published (redis-cli XLEN x:events.norm).

Ensure at least one agent is running and producing to x:signals.*.

Fusion waits for a complete window; try a smaller window in config.

429 from ingest

Stream lag high → pause sources or scale agents.

Decision blocked

See risk-guardian logs for reason_code (cooldown, exposure, quality).

HL orders rejected

Verify nonce/time drift, API perms, and WS connectivity in exec-hl-svc logs.

13) Clean Up
docker compose -f ops/compose.full.yml down -v   # remove volumes (dev only)
deactivate  # python venv

14) Phase 3C: Market Microstructure Verification

Verify microstructure data in market snapshots:
```bash
curl -s http://localhost:8005/snapshots | jq '.snapshots[0].microstructure'
```

Verify confluence scoring in opportunities:
```bash
curl -s http://localhost:8000/state/opportunities | jq '.[0].confluence'
```

Verify macro feed:
```bash
curl -s http://localhost:8000/state/macro/headlines | jq '.headlines[:3]'
```

Test preview with microstructure checks:
```bash
OPP_ID=$(curl -s http://localhost:8000/state/opportunities?status=new | jq -r '.[0].id')
curl -s http://localhost:8000/actions/preview \
  -H "Content-Type: application/json" \
  -d "{\"opportunity_id\": \"$OPP_ID\", \"size_usd\": 1000, \"venue\": \"hyperliquid\"}" | jq '.risk_verdict'
```

Run Phase 3C tests:
```bash
pytest tests/test_phase3c.py -v
```

See `docs/runbooks/Phase3C_Verification.md` for comprehensive verification steps.

15) Appendix

Ports: Postgres 5432, Redis 6379, Qdrant 6333, state-api 8000, core-scorer 8001, fusion-engine 8002, exec-drift 8003, exec-hl 8004, market-data 8005, ingest 8080.

Diagrams: see docs/SYSTEM_DESIGN.md (links to SVGs).

Specs: see docs/AGENT_INTERFACE.md (canonical contracts).

Phase Reports:
- docs/phase3A_report.md - Core pipeline hardening
- docs/phase3B_report.md - Market data expansion
- docs/phase3C_report.md - Market microstructure & risk intelligence