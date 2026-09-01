# Standalone and Federated Architecture

## Decision

TradeSync is a complete standalone product with optional federated connectors. ChaseOS is expected to be present in the operator’s personal deployment, but its temporary absence must not erase TradeSync’s ability to observe Hyperliquid, calculate regimes, trigger alerts, build paper opportunities, render charts, or review evidence.

The architecture uses capability tiers rather than a single all-or-nothing runtime.

## Tier A — standalone workstation

Required:

- Hyperliquid public market access;
- market-data/real-time edge;
- Redis Streams;
- PostgreSQL;
- State API;
- Cockpit UI;
- local regime/opportunity services needed for the selected profile;
- notification ledger and at least an in-app delivery adapter.

Available features:

- market pulse and market drilldowns;
- candles, funding, OI, volume, order-book and trade evidence;
- regime and liquidation views with provenance;
- rule-based alerts;
- paper opportunities and previews;
- journal, decision and outcome review;
- local exports and restart recovery.

Tier A never needs a wallet or ChaseOS to start.

## Tier B — federated intelligence

Optional adapters:

- ChaseOS graph snapshot/query adapter;
- ChaseOS proposal and evidence writeback adapter;
- ChaseOS Gate/approval-status reader;
- Strike Zone `trade_candidate_v1` receipt adapter;
- Hermes/Ollama explanation and synthesis adapter;
- mobile notification delivery adapters;
- later Solana research adapters.

Failure behavior:

- mark the connector `offline`, `stale`, `degraded`, or `incompatible`;
- retain the last verified snapshot as read-only, with age and digest visible;
- queue bounded outbox work when safe;
- never convert cached knowledge into fresh approval;
- continue Tier A;
- block only features that specifically require the missing connector.

## Tier C — governed execution

Required simultaneously:

- current Hyperliquid market and account state;
- isolated signer health;
- wallet/agent identity match;
- risk policy version and limits;
- immutable decision payload digest;
- unexpired single-use approval where required;
- nonce/replay state;
- order-intent idempotency key;
- pre-submit and post-submit reconciliation;
- emergency stop state.

Any missing or contradictory requirement blocks execution. The Cockpit must state the exact block reason.

## Component ownership

| Component | Owns | Does not own |
|---|---|---|
| TradeSync | Hyperliquid market state, regimes, alerts, paper opportunities, journal, outcomes, notification ledger | Canonical personal knowledge, human approval authority, wallet secrets |
| ChaseOS | Canonical knowledge artifact, promotion rules, trust tiers, Gate/approval governance | Hyperliquid market ingestion or TradeSync runtime availability |
| Strike Zone Crypto | Research/thesis artifacts and paper candidate receipts | Execution approval or order placement |
| Hermes/Ollama | Bounded explanation, summarization, comparison, and proposal drafting | Risk limits, approval, canonical promotion, signing |
| Wallet signer | Key custody and narrowly-scoped signing | Opportunity selection, policy changes, UI, knowledge |
| Hyperliquid | Venue market/account/order truth | ChaseOS governance or TradeSync policy |

## Connector envelope

Every connector exchange must include:

- schema name and version;
- event/artifact ID and SHA-256 payload digest;
- producer identity and trust tier;
- created/observed timestamps in UTC;
- authority class (`authoritative`, `derived`, `context_only`, `advisory`);
- environment (`paper`, `testnet`, `live`);
- provenance and evidence links;
- expiry/freshness policy;
- correlation and causation IDs;
- idempotency/deduplication key;
- requested action, if any, as data—not authority.

## Availability matrix

| Outage | Continue | Block |
|---|---|---|
| ChaseOS unavailable | Market, regimes, charts, alerts, paper journal, cached read-only knowledge | New knowledge promotion, new ChaseOS approvals, approval-required execution |
| Strike Zone unavailable | TradeSync-native opportunities and all core functions | New Strike Zone candidate intake only |
| Hermes/Ollama unavailable | Deterministic scoring, alerts, UI, evidence | AI explanation/synthesis only |
| Qdrant unavailable | Exact/relational knowledge queries and core functions | Semantic retrieval; rebuild index later |
| Redis unavailable | Durable reads and historical review | Real-time pipeline until stream transport recovers |
| PostgreSQL unavailable | Existing in-memory market observation may show as degraded | Durable decisions, approvals, orders, outcomes, and execution |
| Notification adapter unavailable | In-app state and alert ledger | That delivery channel; retry from outbox |
| Signer/Gate unavailable | All Tier A and Tier B features | Execution |

## Canonical diagram

Source: [standalone-federated.mmd](../diagrams/standalone-federated.mmd)
