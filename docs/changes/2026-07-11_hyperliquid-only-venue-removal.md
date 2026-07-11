# Hyperliquid-Only Venue Migration

## Result

TradeSync now has one supported venue integration: **Hyperliquid**. The retired protocol's provider, polling collector, execution service, SDK dependency, config, routes, UI controls, test adapters, sample artifacts, and replay rows were removed from this branch.

Historical Git history remains the rollback source. No service, container, private API, exchange endpoint, wallet, credential, or order path was invoked during this work.

## Safety posture

- `EXECUTION_ENABLED=false` in Compose and `.env.example`.
- `DRY_RUN=true` remains the default.
- The execution service rejects requests before contacting Redis or a venue dependency when execution is disabled.
- Unknown opportunity directions fail closed.
- Long/buy directions map to `buy`; short/sell directions map to `sell` instead of always submitting `buy`.
- No credentials were read, changed, or added.

## Removed surfaces

- Provider and collector modules for the retired protocol.
- Dedicated execution service and legacy executor.
- SDK dependency and environment variables.
- Compose service, routes, status fields, circuit state, and execution URL map.
- UI venue selector entries, status cards, provider cards, and kill-switch defaults.
- Dedicated verification tests and samples.
- Mixed samples that could not remain truthful after removing their retired-protocol evidence.
- Retired-protocol rows from replay fixtures; existing Hyperliquid rows were retained.

## Data migration

| Replay fixture | Before | Hyperliquid rows retained | Retired rows removed |
|---|---:|---:|---:|
| calibration/chop | 1,872 | 290 | 1,582 |
| calibration/trend | 1,872 | 290 | 1,582 |
| real_trade_data | 1,870 | 288 | 1,582 |

No data was fabricated or relabeled. Rows sourced from the retired protocol were removed rather than rewritten as Hyperliquid observations.

## Verification

- Removal invariant: 5 passed.
- Market-data service: 17 passed.
- Hyperliquid execution service: 3 passed.
- State API routing/adapters: 2 passed.
- TypeScript production build: passed, 1,793 modules transformed.
- Python compileall: passed.
- Compose YAML parsing and sole-venue assertion: passed.
- Git whitespace/error check: passed.
- Case-insensitive tracked-source and tracked-path scan for the retired protocol: zero matches.

The repository's monolithic `pytest` invocation remains unsuitable because multiple services expose conflicting top-level `app` packages and some legacy tests rely on stale mocks or unavailable service dependencies. Service-isolated suites above are the authoritative migration verification.

## Rollback

The work is isolated on a dedicated migration branch in a separate worktree. Before merge, remove the worktree and then delete its branch with the normal Git worktree/branch commands.

After merge, use a normal Git revert of the migration commit. Do not restore files manually from copied credentials or runtime state.
