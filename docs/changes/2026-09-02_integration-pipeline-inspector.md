# Integration Pipeline Inspector

Date: 2026-09-02

Branch: `codex/2026-09-01-dashboard-overhaul`

Worktree: `E:\Projects\TradeSync\dashboard-overhaul-2026-09-01`

## Repo-truth delta

Before this slice, the standalone/federated tiers were documented, but the
Cockpit did not expose a single inspectable runtime topology. Mission Control
could say that the intelligence pipeline was partial without showing which
stage was missing, whether a connector was merely documented, or what a safe
recovery target would be.

After this slice, `GET /state/integration-pipeline` and `/pipeline` expose live
Tier A probes, optional connector state, workflow edges, explicit capability
gaps, impact, and bounded recovery guidance. Repository contracts are reported
as `contract_only`, never as live connections.

## Implemented

- Added the versioned `integration_pipeline_status_v1` State API response.
- Added live checks for Hyperliquid/market-data, Redis, PostgreSQL,
  ingest-gateway, core-scorer, and fusion-engine.
- Added configured-only health probes for Strike Zone Crypto, agent harnesses,
  and ChaseOS.
- Added a responsive Cockpit Integration Pipeline page with expandable stage
  evidence, missing items, operational impact, recovery target, workflow edges,
  capability gaps, and an ordered recovery queue.
- Added an Integration Pipeline navigation item and a top-bar status menu that
  is inspectable by hover or keyboard focus.
- Linked Mission Control Market Data, Intelligence Pipeline, and Execution
  readiness cards to the inspector.
- Marked `price_change_24h` as `deferred_non_blocking`; no substitute value is
  calculated or displayed.
- Kept direct liquidation evidence unavailable instead of presenting the OI
  pressure proxy as a liquidation feed.

## Runtime correction discovered during QA

The market-data container was healthy and returned snapshots directly, but the
State API's internal async proxy occasionally timed out while the Cockpit was
polling several legacy routes. That caused Mission Control to report a false
market outage.

The read-only market snapshot proxy and integration probes now perform bounded
internal HTTP reads outside the primary API event loop. Market probes and
unstarted-service probes use separate deadlines. The bounded Compose profile
leaves unstarted service endpoints empty, so a failed Docker DNS lookup cannot
invalidate or delay authoritative market evidence.

Verified after rebuilding State API:

- `/state/market/snapshots`: HTTP 200, 0.160-1.175 seconds across final
  acceptance reads, three live market rows.
- `/state/integration-pipeline`: HTTP 200, 0.395-1.108 seconds across final
  acceptance reads, Tier A partial, 4/7 fully ready.
- Hyperliquid and market normalization: live.
- Redis and PostgreSQL: healthy.
- Regime engine and performance/journal: partial.
- Scorer/fusion and TradingView/Pine: offline in the bounded profile.
- Strike Zone, agent harnesses, and ChaseOS: contract only.
- Execution: locked; `execution_authority=false`.

## Safety and untouched boundaries

- Paper-only behavior is unchanged.
- No wallet, signer, private key, approval, or live order path was added.
- No restart action is executable from the UI; commands are explanatory text.
- The canonical ChaseOS vault at
  `C:\Users\chaseos\Documents\chaseos_obsidian` was not read, moved, or
  modified.
- PostgreSQL and Redis volumes were retained. No `down -v` operation ran.
- Ingest-gateway, scorer, fusion, Strike Zone, agent harness, ChaseOS, and
  execution services were not started or represented as connected.

## Verification

- State API integration and Regime Lab tests: 8 passed.
- Shared market-feature and regime-weight tests: 21 passed.
- TypeScript: `npx tsc --noEmit --pretty false` passed.
- Production bundle: `npx vite build` passed; 1,867 modules transformed.
- Market-data suite: 20 passed; one pre-existing Windows wall-clock timing
  assertion failed twice (`0.184-0.195s` observed against a `<0.15s` ceiling).
  No market-data source was changed in this slice.
- Browser DOM verified the top-bar focus inspector, expandable scorer recovery,
  Mission Control-to-pipeline navigation, three live Hyperliquid market rows,
  and the 390x844 mobile layout/navigation.
- Browser console: no warnings or errors in the final pipeline view.

## Visual evidence

Evidence is stored outside the source tree at:

`E:\Visual QA\TradeSync Visual QA\Current Reviews\2026-09-02-integration-pipeline`

The review contains the final live desktop view, focus/hover status menu,
expanded/recovery states, and responsive mobile views.

## Remaining unknowns and next safe action

The next Tier A development slice is scorer/fusion restoration: reconcile the
legacy scorer input contract with `market_feature_v1` and the regime evidence
engine, then start only `core-scorer` and `fusion-engine` and verify a paper
opportunity end to end. TradingView/Pine, Strike Zone, agent harness, and
ChaseOS work should follow as optional versioned adapters and must not become
startup dependencies.
