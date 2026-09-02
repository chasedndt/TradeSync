# TradeSync System Design

Version: 1.0 architecture baseline

Updated: 2026-09-01

TradeSync is a standalone-first, event-driven Hyperliquid workstation with optional ChaseOS/Strike Zone/AI connectors and a separately gated execution tier.

## Current implementation

- Python/FastAPI market and state services.
- React/TypeScript Cockpit.
- Redis Streams and latest-state caches.
- PostgreSQL 16 durable records.
- Optional Qdrant evidence profile.
- Hyperliquid-only market and future execution boundary.
- Paper defaults: `DRY_RUN=true`, `EXECUTION_ENABLED=false`.
- Read-only `integration_pipeline_status_v1` topology probes surfaced in the Cockpit at `/pipeline`.

## Canonical design documents

- [Standalone and federated architecture](architecture/STANDALONE_FEDERATED_ARCHITECTURE.md)
- [Data and knowledge plane](architecture/DATA_AND_KNOWLEDGE_PLANE.md)
- [Mobile alert control plane](architecture/MOBILE_ALERT_CONTROL_PLANE.md)
- [Rust boundaries](architecture/RUST_BOUNDARIES.md)
- [Roadmap](../roadmap.md)
- [Diagram index](diagrams/README.md)

## Service boundary

TradeSync core owns market observation, regimes, alerts, paper opportunities, evidence, and outcomes. ChaseOS owns canonical personal knowledge and Gate/approval authority. Strike Zone owns research and candidate proposals. AI runtimes are advisory. An isolated signer owns key use. Hyperliquid owns venue truth.

Optional systems enrich the core but do not become Tier A startup dependencies. Approval-required or live execution fails closed when any required authority or state is unavailable.

## Runtime inspectability

The State API assembles a read-only integration graph from live probes and
declared repository contracts. The Cockpit exposes the summary in the top bar
and the complete graph at `/pipeline`. Each stage shows evidence, missing
inputs, operational impact, and the next bounded repair or restart target.

The inspector does not execute its displayed commands. It does not turn a
contract-only adapter into a live connection, and it does not count ChaseOS,
Strike Zone Crypto, TradingView/Pine Script, or agent harness availability
against standalone Tier A readiness. See
[Integration Pipeline status v1](contracts/INTEGRATION_PIPELINE_STATUS_V1.md).

## Historical notice

Earlier versions of this document described multiple venues, Discord as the primary alert plane, active TimescaleDB, and services that are not current. Those descriptions remain discoverable in Git history and historical diagrams but are not current architecture.
