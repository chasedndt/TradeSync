# TradeSync Agent Guide

TradeSync is a standalone-first, Hyperliquid-only workstation with optional ChaseOS, Strike Zone, local-AI, notification, and wallet connectors.

## Authority

- Hyperliquid is the only venue and authoritative market source.
- Paper mode is the default: `DRY_RUN=true`, `EXECUTION_ENABLED=false`.
- ChaseOS means the private instance at `C:\Users\chaseos\Documents\chaseos_obsidian`.
- ChaseOS governs canonical knowledge promotion and approval authority; TradeSync must remain usable when the connector is offline.
- Optional context providers and AI models never grant risk, approval, wallet, or execution authority.
- No key, signer, wallet, deployment, spend, or live execution without explicit operator approval and passing roadmap gates.

## Working location

Use an isolated E: worktree under `E:\Projects\TradeSync\<task>`. Put caches, test output, builds, and other reproducible artifacts on E:. Route new visual evidence to `E:\Visual QA\TradeSync Visual QA`.

## Core commands

Start the bounded dashboard profile:

```powershell
docker compose `
  --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
  -f ops\compose.full.yml `
  -f ops\compose.market-command.yml `
  up -d postgres redis market-data state-api cockpit-ui
```

Stop the same services with `docker compose ... stop cockpit-ui state-api market-data redis postgres`. Never use `down -v` during ordinary development.

## Current service roles

- `market-data`: Hyperliquid public data and normalized market snapshots.
- `state-api`: durable read model and bounded actions.
- `cockpit-ui`: Mission Control and operator surfaces.
- `core-scorer`: signal scoring; optional in the lean profile.
- `fusion-engine`: opportunity construction; optional in the lean profile.
- `exec-hl-svc`: paper/future Hyperliquid execution boundary; fail-closed.
- `postgres`: durable truth.
- `redis`: stream transport and short-lived state.
- `qdrant`: optional, rebuildable semantic evidence index.

## Documentation order

1. `README.md`
2. `roadmap.md`
3. `docs/README.md`
4. `docs/architecture/STANDALONE_FEDERATED_ARCHITECTURE.md`
5. `docs/architecture/DATA_AND_KNOWLEDGE_PLANE.md`
6. relevant contracts, providers, runbooks, and change records

Historical phase reports and PlantUML exports can include retired venues or unimplemented components. They are evidence, not current authority.

## Verification

- Run targeted Python tests.
- Run `npm run build` for Cockpit changes.
- Run `cargo test --workspace` for Rust contract/service changes with cache and target output on E:.
- Verify the bounded Docker profile when runtime behavior changes.
- Record exact results and keep paper/live, planned/implemented, and local/deployed status separate.
