# TradeSync Documentation

This folder is the documentation system of record for the Hyperliquid-only TradeSync product. Documents are grouped by authority and purpose so historical plans do not silently become current architecture.

## Start here

1. [Repository README](../README.md) — current product boundary and operator start/stop.
2. [Roadmap](../roadmap.md) — delivery sequence, three-week mobile-alert sprint, gates, and future phases.
3. [Standalone and federated architecture](architecture/STANDALONE_FEDERATED_ARCHITECTURE.md) — capability tiers and outage behavior.
4. [Data and knowledge plane](architecture/DATA_AND_KNOWLEDGE_PLANE.md) — database roles, ChaseOS projection, and real-time agent access.
5. [Mobile alert control plane](architecture/MOBILE_ALERT_CONTROL_PLANE.md) — reusable cross-project notification design.
6. [Rust boundaries](architecture/RUST_BOUNDARIES.md) — where Rust is adopted and where Python/TypeScript remain appropriate.

## Brand

- [TradeSync identity](brand/TRADE_SYNC_IDENTITY.md)
- [Canonical transparent mark](brand/assets/tradesync-mark.png)

## Current contracts

- [Preview contract](contracts/PREVIEW_CONTRACT.md)
- [Alert event v1](contracts/ALERT_EVENT_V1.md)
- [Knowledge synchronization v1](contracts/KNOWLEDGE_SYNC_V1.md)
- [Risk limits](contracts/RISK_LIMITS.md)

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
