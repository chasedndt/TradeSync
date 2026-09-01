# Architecture, Roadmap, Brand, and Rust Contract Revision

Date: 2026-09-01

Branch: `codex/2026-09-01-dashboard-overhaul`

## Repo-truth delta

- Reframed TradeSync from a component that depends on the entire Market Command stack into a standalone-first workstation with optional federation.
- Defined three capability tiers: standalone, federated intelligence, and governed execution.
- Replaced the previous linear/far-future wallet roadmap with a three-week foundation sprint and earlier wallet/approval foundation.
- Defined a reusable mobile notification control plane and a no-Xcode PWA/ntfy path.
- Selected PostgreSQL + Redis Streams + Qdrant + content-addressed files with ChaseOS `GraphSnapshot` as canonical knowledge artifact.
- Established Rust at the realtime/security boundaries and added the first shared Rust contract crate.
- Promoted one transparent TradeSync TS mark to the canonical current logo and bound the Cockpit sidebar to it.

## Current versus planned

Implemented in this change:

- canonical documentation structure and Mermaid diagram sources;
- canonical PNG mark and UI consumption;
- `alert_event_v1` documentation;
- Rust `tradesync-contracts` validation crate and tests;
- explicit unverified ChaseOS private connector boundary.

Still planned:

- Hyperliquid Rust WebSocket edge;
- Rust notification router;
- PWA/Web Push and ntfy delivery;
- PostgreSQL knowledge projection tables;
- live ChaseOS connector and Gate binding;
- wallet/signer and any execution activation.

## Safety

- No wallet, key, token, signing, execution enablement, deployment, public exposure, or spend occurred.
- Paper defaults remain required.
- The ChaseOS private vault was read only; no canonical ChaseOS writeback was performed.
- Existing historical diagrams were retained and labeled historical rather than deleted.

## Verification evidence

Passed:

- `cargo fmt --check`
- `cargo test -p tradesync-contracts --offline` — 4 passed, 0 failed; doc tests 0 failed
- direct TypeScript `tsc --noEmit` — exit 0
- `python -m pytest tests\test_context_feed.py -q` from `services\state-api` — 2 passed
- documentation relative-link check — 12 current files, 0 broken links
- `git diff --check` — exit 0
- canonical/UI logo SHA-256 parity — `558301F53870747CA289F865CB71C09465AAEC87B57F1B039B397A1841C1F499`
- logo alpha validation — RGBA, transparent corners, non-empty subject bounds
- Compose status after build attempt — PostgreSQL, Redis, market-data, state-api, and the existing Cockpit container remained running; services with health checks reported healthy

Blocked/unverified:

- Direct Vite production bundling and the Docker Cockpit image rebuild each exceeded a five-minute timeout while the host was saturated by unrelated Node workload. Neither emitted a source/compiler error, and the independent TypeScript check passed.
- The existing healthy Cockpit container was preserved, so `http://localhost:3000/` still serves the prior image until a successful rebuild/recreate.
- HTTP probes timed out under the same host congestion despite Compose health state.
- No browser screenshot/console visual QA was completed for the new logo in this revision.

## Next safe action

When host load is lower, rerun the Cockpit production build, rebuild/recreate only `cockpit-ui`, verify `/brand/tradesync-mark.png`, then capture desktop and mobile evidence under the TradeSync visual-QA review folder.
