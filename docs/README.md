# TradeSync Documentation

This folder is the documentation system of record for the Hyperliquid-only TradeSync product. Documents are grouped by authority and purpose so historical plans do not silently become current architecture.

## Start here

15 September managed paper positions: [Versioned lifecycles with trailing stops, depth-walked fills, settled funding, entry evidence cut off at entry, and live-data acceptance](changes/2026-09-15_managed-paper-positions.md).

14 September paper safety: [Persistent entry-pause foundation — source only pending SQL/UI acceptance](changes/2026-09-14_paper-control.md).

Consolidated current handover: [14 September integration state, verification limits and next safety work](HANDOVER_2026-09-14_INTEGRATION_STATE.md).

14 September research registration: [Deployed fixed specifications, fingerprints, immutable registry and evaluation API](changes/2026-09-14_research-registration.md).

14 September source comparison: [Deployed cohort API/UI, experimental liquidity filter, mathematics and remaining evaluation gates](research/2026-09-14_source-comparison-v1.md). Empty current cohort is not a measured source benefit.

14 September entry context: [Frozen Bybit receipts and Hyperliquid book history, causal tests and remaining source evaluation](changes/2026-09-14_entry-liquidation-context.md).

14 September liquidation provenance: [First-received timestamps, replay dedupe and remaining durable-entry work](changes/2026-09-14_first-received-liquidations.md).

14 September mobile lifecycle continuation: [Deployed opt-in, quiet hours, budget policy and remaining phone acceptance](changes/2026-09-14_mobile-lifecycle-policy.md).

14 September real-market API acceptance: [Isolated open/close and unchanged evidence](changes/2026-09-14_paper-api-live-market-acceptance.md), [trading-day readiness checklist](runbooks/TRADING_DAY_READINESS.md).

14 September managed-paper dashboard: [Controls, frozen evidence, desktop/mobile QA and remaining acceptance](changes/2026-09-14_managed-paper-dashboard.md).

14 September managed-paper backend: [Implementation/verification](changes/2026-09-14_managed-paper-backend.md), [research protocol and learning exercises](research/2026-09-14_managed-paper-protocol.md).

14 September mobile foundation: [Outbox, enrollment and verification](changes/2026-09-14_mobile-alert-outbox.md), [Android/iPhone setup and acceptance](runbooks/MOBILE_ALERTS.md).

14 September wallet continuation: [Watch-only positions, orders, fills and remaining acceptance](changes/2026-09-14_watch-only-activity.md).

14 September active-goal continuation: [Liquidity feeds, intraday horizons, verification and remaining integration work](changes/2026-09-14_liquidity-intraday-and-integration-goal.md).

Current status: [13 September roadmap reconciliation and handover closure register](ROADMAP_RECONCILIATION_2026-09-13.md).
Development evidence: [Fleet controls and cost-aware trading research](changes/2026-09-13_fleet-and-trade-research.md).

13 September continuation: [Context-card fit, RSI correctness and handover review](changes/2026-09-13_context-fit-and-handover-review.md).

Pairing acceptance follow-up: [Build, dependency audit and setup-screen QA](changes/2026-09-09_walletconnect-build-acceptance.md).

Optional pairing: [WalletConnect address-only implementation and setup gates](changes/2026-09-09_walletconnect-address-only.md).

Watch-only onboarding: [Public-address account inspection](changes/2026-09-09_watch-only-wallet.md).

Latest UI slice: [Canvas modes, paper outcomes and adapter readbacks](changes/2026-09-09_canvas-and-adapter-readbacks.md).

Current review: [9 September usability, measurement and wallet progression](REVIEW_20260909_USABILITY_AND_WALLETS.md), with updated architecture diagrams and explicit acceptance gaps.

Latest continuation: [Claude handover — 7 September 2026](CLAUDE_CONTINUATION_HANDOVER_2026-09-07.md), including checkout recovery boundaries, current Docker availability, historical verification, and the next paper-pipeline slice.

1. [Repository README](../README.md) — current product boundary and operator start/stop.
2. [Roadmap](../roadmap.md) — delivery sequence, three-week mobile-alert sprint, gates, and future phases.
3. [Standalone and federated architecture](architecture/STANDALONE_FEDERATED_ARCHITECTURE.md) — capability tiers and outage behavior.
4. [Data and knowledge plane](architecture/DATA_AND_KNOWLEDGE_PLANE.md) — database roles, ChaseOS projection, and real-time agent access.
5. [Mobile alert control plane](architecture/MOBILE_ALERT_CONTROL_PLANE.md) — reusable cross-project notification design.
6. [Rust boundaries](architecture/RUST_BOUNDARIES.md) — where Rust is adopted and where Python/TypeScript remain appropriate.
7. [Quant Foundations — Book 1](quant-learning/README.md) — notation-first education, weighting, paper-risk caps, and practice gates.
8. [Regime Rulebook v1](architecture/REGIME_RULEBOOK_V1.md) — deterministic scoring, provenance, versioning, and outage behavior.
9. [Regime Lab API](contracts/REGIME_LAB_API.md) — private learning controls, same-evidence comparison, persistence, and fail-closed boundaries.
10. [Regime Lab live-runtime verification](changes/2026-09-02_regime-lab-live-runtime.md) — Docker repair, live feature evidence, restart behavior, tests, and remaining gaps.
11. [Integration Pipeline status v1](contracts/INTEGRATION_PIPELINE_STATUS_V1.md) — live probes, declared connectors, missing links, and recovery semantics.
12. [Regime-backed paper signal path](changes/2026-09-07_regime-backed-paper-signal.md) — one-hour return admission, catalog 1.1.0, the 0.55 coverage ceiling, admission gates, and replay idempotency.
13. [Outcome measurement and directional CVD](changes/2026-09-08_outcomes-and-directional-cvd.md) — forward-return measurement, the first track record, and a second admitted directional feature.
14. [Dashboard truthfulness and 24h change](changes/2026-09-08_dashboard-truthfulness-and-24h-change.md) — venue-published previous-day derivation, the structurally capped Tier A counter, and honest probe defaults.

## Current state

- [Roadmap state and plan — 8 September 2026](ROADMAP_STATE_2026-09-08.md) — decisions taken, the first measured track record, and outstanding work in priority order.

## Planning

- [Implementation sequence](IMPLEMENTATION_SEQUENCE.md) — every outstanding item with its slot, precondition, and the reason it sits there. Includes health-state ageing, Strike Zone, agent harnesses, ChaseOS Gate and Pine Script.

## Recent change records

- [Market Canvas drawings](changes/2026-09-08_canvas_drawings.md) — versioned operator levels that supersede rather than overwrite.
- [Coinbase spot premium](changes/2026-09-08_spot_premium_context.md) — a third directional candidate, deliberately context-only until you admit it.
- [Regime-split skill gate](changes/2026-09-08_regime-split-skill-gate.md) — the pooled figure was a Simpson's-paradox artefact; no skill demonstrated in either regime.

- [Fixed-window replay](changes/2026-09-08_fixed-window-replay.md) — champion/challenger on frozen evidence, and why weight tuning cannot fix the signal.
- [State ageing and quarantine](changes/2026-09-08_state-ageing-and-quarantine.md) — how long each stage has held its state, and the Tier B admission boundary.

## Architecture diagrams

Visual walkthrough of the whole system, verified against the running stack.

- [System map](architecture/SYSTEM_MAP.md) — start here. Service topology, ports, capability tiers, Cockpit routes, runtime profiles.
- [Paper signal dataflow](architecture/PAPER_SIGNAL_DATAFLOW.md) — observation to opportunity, the producer cycle, admission gates, replay safety.
- [Feature and regime mathematics](architecture/FEATURE_AND_REGIME_MATH.md) — feature lifecycle, the five blocks, the 0.55 coverage ceiling, a worked score.
- [Failure modes](architecture/FAILURE_MODES.md) — how this system actually broke, drawn out, with a checklist.
- [Webhook ingress security](architecture/WEBHOOK_INGRESS_SECURITY.md) — the risk analysis for exposing an endpoint to TradingView.

## Brand

- [TradeSync identity](brand/TRADE_SYNC_IDENTITY.md)
- [Canonical transparent mark](brand/assets/tradesync-mark.png)

## Current contracts

- [Preview contract](contracts/PREVIEW_CONTRACT.md)
- [Alert event v1](contracts/ALERT_EVENT_V1.md)
- [Knowledge synchronization v1](contracts/KNOWLEDGE_SYNC_V1.md)
- [Risk limits](contracts/RISK_LIMITS.md)
- [Regime weight configuration v1](contracts/REGIME_WEIGHT_CONFIG_V1.md)
- [Market feature v1](contracts/MARKET_FEATURE_V1.md)
- [Regime Lab API](contracts/REGIME_LAB_API.md)
- [Integration Pipeline status v1](contracts/INTEGRATION_PIPELINE_STATUS_V1.md)

## Quant learning

- [Book 1 index](quant-learning/README.md)
- [Mathematical notation](quant-learning/01_NOTATION_AND_MATH_LANGUAGE.md)
- [Normalization and tanh](quant-learning/02_NORMALIZATION_AND_TANH.md)
- [Weights, quality, risk caps, and experiments](quant-learning/03_WEIGHTING_QUALITY_AND_EXPERIMENTS.md)
- [Year 2 module map and practice](quant-learning/04_YEAR2_MODULE_MAP_AND_PRACTICE.md)
- [Build-in-public evidence practice](quant-learning/05_BUILD_IN_PUBLIC_PRACTICE.md)
- [Book 1 handover](quant-learning/BOOK_1_HANDOVER.md)
- [Applied Lab 1 — rolling normalization and outliers](quant-learning/labs/LAB_01_ROLLING_NORMALIZATION.md)
- [Applied Lab 2 — regime weights and coverage](quant-learning/labs/LAB_02_REGIME_WEIGHTS_AND_COVERAGE.md)

## Legacy contracts requiring reconciliation

- [Market contract](contracts/MARKET_CONTRACT.md)
- [Opportunity contract](contracts/OPPORTUNITY_CONTRACT.md)
- [Symbol normalization](contracts/SYMBOL_NORMALIZATION.md)

These files contain useful historical schema detail but still include retired multi-venue fields. Do not use them as a new implementation contract until a Hyperliquid-only version replaces them.

## Providers and operations

- [Market provider matrix](providers/MARKET_PROVIDER_MATRIX.md)
- [Runbooks](RUNBOOKS.md)
- [Phase 0 resource readiness](PHASE0_RESOURCE_READINESS.md)

## Diagrams

Canonical Mermaid sources live in [diagrams/](diagrams/README.md). Existing PlantUML diagrams and exports are retained as historical evidence; a diagram is not current merely because an export exists.

## Historical handovers and phase reports

- [ChaseOS Market Command handover](CHASEOS_MARKET_COMMAND_HANDOVER.md)
- `phase3A_report.md`, `phase3B_report.md`, and `phase3C_report.md`
- `CLAUDE_HANDOFF_PHASE3B.md`

These preserve decisions and evidence. They do not override the current README, roadmap, source, tests, or Hyperliquid-only boundary.
