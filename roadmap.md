# TradeSync Roadmap

Last updated: 2026-09-01

Planning horizon: three-week foundation sprint plus gated continuation

Operating rule: standalone-first, Hyperliquid-only, paper-first, fail-closed

## Expected outcome

At the end of the foundation programme, TradeSync is one coherent operator workstation that can:

1. consume and retain authoritative Hyperliquid market data in real time;
2. calculate explainable regimes and liquidation evidence without presenting proxies as facts;
3. surface ranked paper opportunities and complete decision evidence;
4. provide an internal Market Canvas with chart-native alerts;
5. continue all core functions while ChaseOS, Strike Zone, local models, notification adapters, or wallets are unavailable;
6. synchronize approved ChaseOS graph snapshots and Strike Zone paper candidates when those connectors are available;
7. deliver governed alerts to desktop and mobile without an Xcode/native-iOS build;
8. support later wallet preview and execution only through an isolated signer, single-use approval consumption, risk policy, and reconciliation;
9. feed outcomes and lessons back as proposals for ChaseOS review, never as autonomous canonical truth.

## Architecture invariants

- **Standalone is a product, not a degraded mode.** Market data, regimes, alerts, charting, paper opportunities, and journaling belong to Tier A.
- **Connectors enrich; they do not own core availability.** Optional connector outages are visible and recoverable.
- **Knowledge and authority are separate.** A graph fact, model explanation, or Strike Zone candidate can inform a decision but cannot approve or execute it.
- **Execution fails closed.** Missing Gate, signer, wallet state, account state, nonce state, risk state, or reconciliation blocks order submission.
- **Artifacts are truth; indexes are rebuildable.** ChaseOS `GraphSnapshot` JSON and TradeSync Postgres rows are durable. Redis and Qdrant are derived/transport layers.
- **Hyperliquid is the only venue.** Solana ecosystem research stays in a separate namespace and does not silently become an execution venue.
- **Paper/live labels are explicit on every record and surface.**

## Three-week foundation sprint

### Week 1 — Market truth, contracts, and Rust foothold

Status: in progress.

- Replace polling-only critical paths with a reconnecting Hyperliquid WebSocket design for `activeAssetCtx`, candles, `l2Book`, trades, and later user-scoped fills/events.
- Correct 24-hour change, market freshness, and service-probe semantics.
- Define `market_event_v1`, `alert_event_v1`, `knowledge_sync_v1`, and `trade_candidate_v1` boundaries.
- Add the Rust shared-contract crate and make it the compatibility seam for the future real-time edge and notification router.
- Audit existing liquidation proxies; label proxy fields unmistakably and prevent 50/50 long/short estimates from appearing authoritative.
- Design PostgreSQL partitions/indexes for candles, market events, alerts, and graph projections.
- Add deterministic data-quality tests for duplicate IDs, timestamp order, source authority, stale events, and missing lineage.

Exit gate:

- Rust contract tests pass.
- Hyperliquid samples map to versioned fixtures.
- Liquidation and regime fields declare `observed`, `derived`, `proxy`, or `unavailable` provenance.
- Restart/replay tests prove no duplicate durable events.

### Week 2 — Regimes, opportunities, knowledge connector, and alert router

Status: in progress. Quant Foundations Book 1, the draft paper rulebook, 17-feature catalog, cadence-governed feature extraction, ordinary/robust normalization, deterministic block aggregation, State API comparison, persistence migrations/runner, and the private Regime Lab are implemented locally. Docker-backed history accumulation, migration application, fixed-window replay, and active-scorer integration remain unverified/planned.

- Rebuild regime classification from measured trend, volatility, funding, OI, volume, liquidity, and market-structure inputs.
- Run the versioned rulebook beside the legacy classifier before replacement; retain configuration digest, source lineage, per-block quality, contribution trace, and paper-risk caps for every score.
- Extract and persist only catalog-admitted `market_feature_v1` observations; block proxy/context/unavailable inputs from generic scoring and reject future timestamps to prevent look-ahead.
- Add a Regime Lab where the operator can inspect notation, edit a draft challenger, validate weights, compare versions, replay a fixed paper window, and request paper activation without exposing live execution controls.
- Restore scorer/fusion health probes and the paper opportunity pipeline.
- Implement a read-only ChaseOS graph-snapshot adapter and a local PostgreSQL graph projection.
- Implement Strike Zone receipt validation into `trade_candidate_v1`; candidates remain paper research.
- Begin the Rust `alert-router-rs` service with PostgreSQL outbox, Redis consumer groups, deduplication, priority, expiry, quiet hours, and delivery receipts.
- Replace Sources with Knowledge Graph intake: drag/drop enters quarantine, extraction produces a proposed graph delta, and only approved promotion changes canonical knowledge.
- Replace Decisions/Orders shells with Activity & Evidence tabs: Decisions, Approvals, Orders, Alerts, Outcomes.

Exit gate:

- TradeSync remains fully usable with every optional connector disabled.
- Disconnect/reconnect tests replay graph deltas and alerts without duplication.
- No model or connector can write canonical ChaseOS knowledge or consume approval authority.

### Week 3 — Mobile alerts, Market Canvas foundation, and reliability

Status: planned; feasible as an MVP without Xcode.

- Add a PWA manifest, service worker, notification permission flow, and Web Push subscription management.
- Add an ntfy adapter as a free fast-path while keeping the Rust router vendor-neutral.
- Add notification preferences by project, symbol, severity, category, quiet hours, and device.
- Add acknowledgement, retry/backoff, dead-letter, dedupe, rate-limit, and delivery-ledger views.
- Add the first Market Canvas route with a Hyperliquid chart, timeframe selection, evidence markers, and alert-rule creation.
- Run desktop/tablet/mobile responsive QA, browser-console checks, restart recovery, and an alert-latency soak.

Exit gate:

- A paper opportunity or critical system-health event reaches an enrolled Android or iOS Home Screen PWA/ntfy client with a durable delivery receipt.
- iOS setup documents the Home Screen requirement; no Apple Developer membership or Xcode project is required for standards-based Web Push.
- No alert action can place an order.
- The service can be reused by another ChaseOS project by changing `project`, routing policy, and producer credentials—not by forking the router.

## Phase 4 — Market Canvas and journal maturity

- TradingView Lightweight Charts or KLineChart-based per-market workspace.
- Candles, funding, OI, volume, order-book depth, liquidity, regimes, alerts, drawings, and evidence timeline.
- Versioned user drawings and alert rules stored server-side.
- Deterministic outcome metrics: expectancy, drawdown, adverse/favourable excursion, slippage, thesis adherence, and regime fit.
- Reconciliation views for orphaned events, duplicate candidates, stale approvals, partial orders, and missing outcomes.

Exit gate: a paper trade can be reconstructed from source observation through outcome without screenshots or memory.

## Phase 5 — Wallet and approval foundation

This phase moves earlier than Solana expansion, but remains approval-gated.

- Create a separate Hyperliquid agent/API wallet only after explicit operator action.
- Keep private keys out of browser storage, logs, prompts, model contexts, PostgreSQL, Redis, Qdrant, and general service environments.
- Run the signer in an isolated service with the smallest possible API and network scope.
- Implement preview → approval request → approval decision → single-use consumption → final risk check → order intent → venue receipt → reconciliation.
- Support modes: `locked`, `observe`, `paper`, `approval_required`, and later `bounded_autonomous`.
- A ChaseOS Gate outage blocks modes that require approval; it does not stop standalone observation, paper alerts, or journal review.

Exit gate: testnet or non-broadcast signed-intent verification, replay protection, expiration, changed-payload invalidation, kill-switch test, and security review.

## Phase 6 — Bounded Hyperliquid canary

- Separate canary wallet and explicit capital ceiling.
- One market, one strategy version, low leverage, small notional, and a bounded time window.
- Pre-trade and post-trade account reconciliation.
- Automatic block on stale market/account state, policy mismatch, approval mismatch, nonce uncertainty, delivery uncertainty, or daily-loss ceiling.
- Human-readable incident and rollback runbooks.

No-go: no production-sized deployment, self-increasing limits, self-promotion of a strategy, or model access to signing material.

## Phase 7 — Solana ecosystem research

- Add Solana token discovery and Phantom/Solana wallet visibility in a separate `solana_research` authority namespace.
- Use Rust where it improves Solana RPC ingestion, transaction decoding, and deterministic validation.
- Add liquidity, contract/program risk, holder concentration, mint/freeze authority, route quality, and manipulation gates.
- Reuse Market Canvas and alerting; do not route Solana assets through Hyperliquid execution semantics.
- Any Solana signing capability gets its own signer, approvals, limits, and threat model.

## Product-surface backlog

### Regime Lab

Show the active paper champion and draft challenger, all block weights, running total, normalization curve, data-quality coverage, contribution trace, risk caps, rulebook digest, experiment hypothesis, evaluation window, outcome KPI, drivers, guardrails, and rollback. The panel must call the shared calculation library through the API rather than reproduce mathematical logic in TypeScript.

### Regime summary

Show current regime, confidence, evidence components, conflicting factors, source freshness, transition history, and “why not higher confidence.” Never show `UNKNOWN` without the missing inputs.

### Liquidations

Separate observed user-fill liquidation events, venue-level liquidation mechanics, inferred pressure, and legacy proxy estimates. Show direction only when the source supports it.

### Opportunities

Show symbol/timeframe, side, regime fit, entry conditions, invalidation, stop, targets, estimated risk/reward, evidence, provenance, age, and paper/live state.

### Activity & Evidence

- Decisions: proposed/allowed/blocked/expired plus policy reasons.
- Approvals: pending/approved/denied/expired/consumed with immutable payload digest.
- Orders: preview/submitted/placed/partial/filled/cancelled/failed/reconciled.
- Alerts: triggered/routed/delivered/acknowledged/expired/dead-lettered.
- Outcomes: P&L, MFE/MAE, fees, funding, slippage, thesis adherence, and lessons.

### Settings

Replace generic browser-local API fields with operator settings: data connections, connector health, notification devices and quiet hours, display/timezone, risk-policy summaries, execution mode, wallet connection status, retention, exports, and diagnostics. Secrets are configured through governed server-side mechanisms, never pasted into ordinary UI fields.

### Operator profile

Make the profile menu identify the current operator/runtime, trust tier, active mode, approval inbox, device sessions, audit exports, and lock/sign-out actions. It must not imply authentication until real identity/session support exists.

## Free provider plan

| Need | Initial free path | Authority |
|---|---|---|
| Perpetual market truth | Hyperliquid public API/WebSocket | Authoritative |
| Spot cross-check | CoinGecko Demo | Context only |
| Protocol TVL | DefiLlama | Context only |
| Macro | FRED free key | Context only |
| Mobile delivery | Standards-based Web Push plus optional ntfy | Notification transport only |
| Local explanations | Hermes/Ollama | Advisory only |

Paid data is considered only after a measured gap cannot be closed with venue data, local calculation, or a free source.

## Programme definition of done

TradeSync is not “done” because containers start or panels render. A capability is complete only when its contract, source authority, persistence, restart behavior, failure behavior, tests, operator surface, evidence, security boundary, and documentation agree.

## Quant learning lane

Every mathematical feature follows an education gate alongside its engineering gate:

1. define notation, units, comparator, and formula in plain English;
2. calculate a small example by hand;
3. implement the deterministic function and tests;
4. map the topic to the operator's Year 2 syllabus;
5. complete the associated practice task;
6. run paper-shadow evidence before changing the champion;
7. retain a public-safe development record without publishing secrets, trade calls, or unverified performance claims.

Book 1 covers notation, z-scores, `tanh`, weighted averages, data quality, basis points, paper-risk multipliers, and champion/challenger versioning. Later books will cover covariance, regression, inference, optimization, time series, and Markov models only when the required data and implementation stage exist.
