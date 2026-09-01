# TradeSync Roadmap

Last updated: 2026-09-01

## Product direction

TradeSync is the Hyperliquid-only operator and evidence layer for ChaseOS Market Command. Development remains paper-first. New capability must improve decision quality, auditability, reliability, or safety before it increases automation.

## Phase 1 — Mission Control foundation (current)

Status: implemented locally; visual QA pending browser availability.

- Responsive Mission Control shell for desktop, tablet, and mobile.
- Hyperliquid-authoritative BTC, ETH, and SOL perpetual market pulse.
- CoinGecko and DefiLlama free context feeds; optional free-key FRED feed.
- Context-only authority labels in the API and UI.
- Honest readiness model that separates live market data, scoring output, and execution authority.
- Read-only execution readiness; no fake arming, kill, or wallet controls.
- Reconciled README, provider matrix, and change record.

Acceptance gate: frontend build, context tests, healthy Docker cockpit, browser visual QA, responsive screenshots, and zero critical console errors.

## Phase 2 — Data truth and journal accuracy

Status: next.

- Expose authoritative Hyperliquid 24-hour mark-price change instead of borrowing spot context.
- Add explicit service probes for scorer and fusion so “no output” and “service offline” remain distinct.
- Audit ingested events, signals, opportunities, decisions, and orders for timestamp, symbol, timeframe, status, and provenance consistency.
- Build reconciliation views for missing links, duplicates, stale rows, and schema drift.
- Define deterministic KPI calculations for win rate, expectancy, drawdown, slippage, and thesis adherence.

Acceptance gate: fixture-backed calculations, database reconciliation report, and no ambiguous simulated/live labels.

## Phase 3 — Market Canvas drilldown (selected future direction 2)

Status: planned, not started.

- Individual Hyperliquid market workspace opened from a Mission Control row.
- Multi-timeframe chart, funding/OI/volume overlays, order-book depth, liquidity, regime, and provenance.
- Evidence timeline linking market observations to signals and paper decisions.
- Time-range, timeframe, and metric controls with mobile-safe interaction states.

Acceptance gate: a single-market paper review can be reproduced from stored evidence without relying on screenshots or memory.

## Phase 4 — Paper intelligence bridge

Status: planned.

- Versioned Strike Zone receipt to `trade_candidate_v1` adapter.
- Single-use approval-consumption ledger and replay protection.
- Scorer/fusion restoration and calibrated opportunity ranking.
- Paper-only outcome tracking and model/rule evaluation.
- Optional local Hermes/Ollama explanations that cannot change risk or authority.

Acceptance gate: end-to-end paper receipt, approval, decision, journal, and outcome evidence across restarts.

## Phase 5 — Ecosystem screener expansion

Status: far-later deferred scope.

- Start with Solana ecosystem discovery and on-chain token screening only after the Hyperliquid workflow is mature.
- Keep on-chain token data in a separate source/authority namespace from Hyperliquid perpetual execution.
- Add provenance, liquidity, contract-risk, holder/distribution, and manipulation-risk gates before any token is surfaced.
- Reuse the Market Canvas pattern for asset drilldown, not the primary Mission Control table.

No-go: do not add Solana execution, wallet authority, token routing, or paid feeds as part of the current dashboard phase.

## Phase 6 — Isolated wallet and bounded canary

Status: approval-gated future work.

- Create a separate Hyperliquid wallet only with explicit operator approval.
- Keep signer secrets outside models, logs, browser storage, and general service environments.
- Require durable approval consumption, idempotency, reconciliation, risk ceilings, and emergency fail-closed controls.
- Start with a bounded canary only after paper evidence and security review pass.

No-go: no wallet creation, credential use, live execution, deployment, spend, or permission changes under the current roadmap authorization.
