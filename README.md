# TradeSync Mission Control

TradeSync is the Hyperliquid-only market-state, paper-research, risk, evidence, and future fail-closed execution layer inside ChaseOS Market Command.

The current system is deliberately **paper-only**:

- Hyperliquid is the sole venue and authoritative market source.
- `EXECUTION_ENABLED=false` and `DRY_RUN=true` are the required defaults.
- No wallet or signer is configured.
- CoinGecko, DefiLlama, and optional FRED data are context-only and never grant scoring, approval, risk, or execution authority.
- ChaseOS means the canonical control-plane vault at `C:\Users\chaseos\Documents\chaseos_obsidian`; this repository does not replace or relocate it.

## Current runtime

The lean operator stack used by the dashboard contains:

| Service | Role | Current operator profile |
|---|---|---|
| `postgres` | Durable market, signal, opportunity, decision, and order records | Running |
| `redis` | Streams and short-lived coordination state | Running |
| `market-data` | Hyperliquid public market polling and normalized snapshots | Running |
| `state-api` | Read model and bounded action API | Running |
| `cockpit-ui` | Responsive Mission Control dashboard | Running |
| `core-scorer` | Signal scoring | Optional / not in lean dashboard profile |
| `fusion-engine` | Opportunity construction | Optional / not in lean dashboard profile |
| `exec-hl-svc` | Hyperliquid paper executor | Optional profile; fail-closed |

The dashboard reports measured output. It does not label an unprobed service outage as healthy, and it does not treat the absence of signals as venue disconnection.

## Start and stop

Use the governed runtime environment file already prepared on E:. Do not copy secrets into this repository.

```powershell
docker compose `
  --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
  -f ops\compose.full.yml `
  -f ops\compose.market-command.yml `
  up -d postgres redis market-data state-api cockpit-ui
```

Open [http://localhost:3000/](http://localhost:3000/).

Stop the same bounded services with:

```powershell
docker compose `
  --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
  -f ops\compose.full.yml `
  -f ops\compose.market-command.yml `
  stop cockpit-ui state-api market-data redis postgres
```

Do not use `down -v`; it would remove persistent volumes.

## Mission Control surfaces

- `/` — authoritative Hyperliquid market pulse, readiness, context-only providers, measured system output, and execution safety.
- `/market` — detailed market data already exposed by the current snapshot contract.
- `/opportunities` — paper opportunity review when scorer/fusion output exists.
- `/sources` — source inspection.
- `/logs` — decisions and orders evidence.
- `/execution` — read-only readiness and future activation gates; no arming controls.

## APIs used by the dashboard

| Endpoint | Purpose |
|---|---|
| `GET /state/health` | State API and PostgreSQL read health |
| `GET /state/snapshot` | Stream/output timestamps and fail-closed execution gate |
| `GET /state/market/snapshots` | Authoritative Hyperliquid snapshots |
| `GET /state/opportunities` | Paper opportunities |
| `GET /state/context/overview` | Cached context-only CoinGecko, DefiLlama, and optional FRED data |
| `GET /state/execution/status` | Read-only execution boundary |

## Provider policy

See [docs/providers/MARKET_PROVIDER_MATRIX.md](docs/providers/MARKET_PROVIDER_MATRIX.md).

- Hyperliquid public API: authoritative for the current market table; free and keyless for the endpoints in use.
- CoinGecko Demo API: free spot-reference context.
- DefiLlama: free Hyperliquid TVL context.
- FRED: free macro context after the operator supplies a free API key; currently optional and disabled.

No paid API is required for the present dashboard.

## Verification

Frontend:

```powershell
cd services\cockpit-ui
npm install --prefer-offline --no-audit --no-fund
npm run build
```

Context-feed tests:

```powershell
python -m pytest services\state-api\tests\test_context_feed.py -q
```

## Architecture and roadmap

- [ChaseOS Market Command handover](docs/CHASEOS_MARKET_COMMAND_HANDOVER.md)
- [Project roadmap](roadmap.md)
- [Market provider matrix](docs/providers/MARKET_PROVIDER_MATRIX.md)
- [Dashboard overhaul change record](docs/changes/2026-09-01_mission-control-dashboard-overhaul.md)
- [Phase 0 resource readiness](docs/PHASE0_RESOURCE_READINESS.md)

Historical documents may describe removed venues or aspirational components. Current source, tests, this README, the Hyperliquid-only migration record, and the canonical ChaseOS control plane take precedence.
