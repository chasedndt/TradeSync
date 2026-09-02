# Regime Lab Live Runtime — 2026-09-02

## Repo-truth delta

The previous Regime Lab slice rendered its learning and comparison controls but
Docker was unavailable, so live feature accumulation, migration application,
database persistence, and the Cockpit proxy were unverified. The bounded stack
now runs against Hyperliquid's public market-data API and keeps the paper-only
authority boundary intact.

## Changes

- repaired market-data and State API catalog path resolution inside their
  shallow container filesystem;
- added real mark price and mark/oracle premium feature extraction;
- seeded the cadence-governed funding window from available seven-day funding
  history and protected current values from out-of-order backfill replacement;
- exposed honest history progress through `history_count` and
  `collecting_history` rather than presenting real-but-young inputs as empty;
- aligned L2 freshness thresholds with the 15-second snapshot cadence;
- separated display-only, collecting, admitted, planned, and unavailable states
  in Regime Lab statistics and evidence labels;
- clarified the top-bar hierarchy as `TradeSync` plus the current page name;
- made the Cockpit `/api/` proxy re-resolve the State API container after a
  service-only replacement;
- added a safe default trace field for dependency log records so HTTP client
  diagnostics cannot break the State API formatter;
- corrected the hidden mobile sidebar so it cannot cast an off-canvas shadow.

## Runtime evidence

The bounded stack started PostgreSQL, Redis, schema-init, market-data, State
API, and Cockpit. Hyperliquid public requests returned successfully. A captured
BTC-PERP snapshot exposed 10 current values from the 17-definition catalog,
including mark, funding, open interest, volume, L2 measurements, and oracle
premium. Two liquidity inputs passed the score gate during the recorded sample;
three inputs were collecting history. These counts are rolling observations,
not fixed product claims.

Migrations `001`, `002`, and `003` completed. PostgreSQL stored the paper-only
draft experiment `544d514d-82d1-4ad1-b79a-240cbf1fb844`. Replacing only the
State API briefly made the route unavailable as expected; the Cockpit proxy
then recovered without a Cockpit restart.

## Safety and untouched boundaries

- `execution_authority=false` throughout verification;
- no wallet, private key, signer, approval, or Hyperliquid execution service
  was configured or started;
- the legacy active classifier/scorer was not replaced;
- the canonical ChaseOS vault, Strike Zone Crypto, and external connectors were
  not changed.

## Verification

- shared feature and regime suite: 26 passed;
- focused market-data extraction, rolling-window, and rate-limit suite: 21
  passed;
- focused Regime Lab State API suite: 5 passed;
- Cockpit production build: TypeScript and Vite passed, 1,858 modules
  transformed;
- Docker Compose configuration passed and all five long-running bounded
  services reported healthy;
- live `/status`, `/features`, `/state/regime-lab/overview`, and Cockpit proxy
  readback;
- desktop and 390 by 844 browser inspection, BTC/ETH market switching, and an
  empty browser error/warning log.

Exact final commands and counts are recorded in the task handover because live
coverage and history counts continue to advance while the stack is running.

## Remaining work

Direct liquidation provenance, one-hour return history, Coinbase premium, ETF
flows, verified external-event context, fixed-window replay, and active-scorer
integration remain planned or unavailable. Zero-dispersion windows remain
blocked from normalization by design.

Visual evidence:
`E:\Visual QA\TradeSync Visual QA\Current Reviews\2026-09-02-regime-lab-live`
