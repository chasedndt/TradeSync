# Rust Boundaries

## Decision

Rust is a first-class TradeSync implementation language for low-latency, high-concurrency, and security-sensitive boundaries. Python remains the preferred research/scoring/AI language, and TypeScript/React remains the Cockpit language.

The goal is a maintainable polyglot architecture—not a wholesale rewrite.

## Rust ownership

| Component | Why Rust | Sequence |
|---|---|---|
| `tradesync-contracts` | One typed contract source for alert/realtime services | Started now |
| `realtime-edge-rs` | Hyperliquid WebSocket reconnects, normalization, backpressure, sequence/freshness checks | Foundation sprint |
| `alert-router-rs` | Concurrent routing, outbox delivery, retries, rate limits, device fan-out | Foundation sprint |
| `signer-rs` | Small auditable secret-bearing boundary, deterministic validation/signing | Wallet phase, approval-gated |
| `solana-adapter-rs` | Solana RPC and transaction ecosystem is strongly supported in Rust | Solana research phase |

## Python ownership

- feature engineering and regime research;
- scoring/fusion experimentation;
- calibration and analytics;
- knowledge extraction and AI harness adapters;
- FastAPI services that are not latency or secret boundaries.

## TypeScript ownership

- React Cockpit and PWA;
- browser service worker and Web Push enrollment;
- chart interaction and drawing tools.

## Interoperability

- versioned JSON contracts at service boundaries;
- Redis Streams for asynchronous events;
- HTTP/SSE/WebSocket for operator surfaces;
- PostgreSQL for durable shared state;
- contract fixtures consumed by Rust, Python, and TypeScript tests.

No service imports another language’s internal implementation. Schema versions and compatibility tests are the seam.

## Adoption gates

- benchmark before moving a Python service solely for speed;
- deny malformed/unknown contract versions;
- use bounded memory and payload limits at network boundaries;
- structured traces include correlation and causation IDs;
- signer code receives separate threat modeling, dependency review, and deployment approval;
- Rust presence alone is not a security claim.
