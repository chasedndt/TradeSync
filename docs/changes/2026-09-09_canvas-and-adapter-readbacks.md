# Canvas and adapter readbacks — 9 September 2026

Codex development record. Preserved the pre-existing review document and index edit. No canonical vault, credentials, jobs, webhook ingress, wallet configuration, scorer weights or execution authority changed.

## Runtime findings

- The actual Cockpit proxy at `127.0.0.1:3000/api/state/market/snapshots` returned three market snapshots. Prior direct localhost port checks are not equivalent to this operator path.
- Harness status says `not_configured`: AGENT_HARNESS_URL is unset. This is not proof that all local runtimes are stopped.
- Graph status says configuration absent but a cached projection contains 7,314 nodes and 10,123 edges, imported September 8. Its build metadata reports 17 extraction errors. Cached graph readability, snapshot synchronization and approval authority are separate facts.
- Wallet preview reports no configured public address; authority remains read-only.
- Pine source repository exists at `C:\Users\chaseos\Documents\Projects\strikezone_crypto`. An E: StrikeZone security worktree exists at `E:\Projects\Trading Systems\2026-08-24-strikezone-security\worktree`, HEAD `50c07e6`, with pack/runtime/vault material. It has NOT been established as a complete current mirror of all TradingView/Pine source. No source was moved or copied.

## UI changes

- URL-preserved Chart & drawings / Research signals toggle. Clean chart defaults to no paper markers; saved drawings stay visible in both modes.
- Price chart fits once on initial data per symbol/timeframe, rather than resetting the operator's zoom every poll.
- Drawing save/delete failures are visible.
- Paper outcomes replace the timeline heading, with selected 15/60/240-minute horizon, full local date/time and hypothetical gross dollar impact per $1,000 unleveraged notional. Missing measured values are not converted to zero in the headline. No fees, funding, slippage, portfolio exposure or real fills are implied.
- Marker text identifies research calls, not a percentage that could be mistaken for win probability. All existing records remain; no losing signals were hidden or deleted.
- Pipeline node cards read the actual harness and graph status endpoints. Cached graph with sync off is distinguishable from an unavailable graph. Strike Zone is described as a Pine submission source, not a daemon.
- Legacy aggregate/edge status remains in the existing pipeline API; the adapter readback is explicitly separate. A full unified backend status contract is still needed.
- Homepage distinguishes WAITING, UNREACHABLE, STALE and LIVE. LIVE requires all returned symbols to meet the existing 15-second freshness threshold rather than only the freshest symbol. Threshold calibration remains separate work.

## Verification and limits

Initial TypeScript check and local production build passed (1,889 modules). Final Docker Cockpit rebuild also passed TypeScript and Vite, replaced only cockpit-ui with `--no-deps`, and HTTP readback served the new `index-Bxa5AVFO.js` bundle. Container was starting its healthcheck at immediate readback. Bundle-size and aged Browserslist warnings remain. Git whitespace check passed. Browser automation failed to attach to Chrome; an alternative Playwright import also failed. Rendered desktop/mobile, drawing interaction and zoom-preservation QA are NOT claimed as passed. The Compose orphan warning for the signer was left untouched; no orphan removal ran.

The dashboard skill guided source-backed outcomes and explicit missing/authority states. No synthetic market data was introduced. The $1,000 figure is an expressly labelled hypothetical conversion of the observed signed return, not account P&L.

## Next bounded work

1. Visually accept Canvas toggle, drawing creation/persistence, zoom across refresh, outcome cards and mobile wrapping.
2. Build a unified integration contract: local source location, configured adapter, reachability, last successful receipt/snapshot/job, freshness, error, and separately permitted actions. Replace generic endpoint probing for file-backed adapters and Pine submission sources.
3. Inventory and compare the C: Pine repo and E: worktree before deciding whether a migration or canonical E: repository is needed. Verify indicator versions on TradingView through operator-provided exports/receipts; a folder alone cannot prove the deployed script matches it.
4. Review signal lifecycle before tuning weights: repeated same-side calls, cooldown/re-entry, side-flip hysteresis, minimum expected move after costs, one hypothetical position policy, exit/expiry rules and net outcomes. Replay proposals on fixed windows; do not impose untested filters to make charts look profitable.
5. Add public-address watch-only wallet onboarding and paper rehearsal, with explicit network labels. No private-key input, real funding or signing during that slice.
6. Resolve the canonical ChaseOS path conflict before any graph mount/writeback change. Governed Discord jobs and external webhook ingress require separate connection/authority checks, not automatic activation.
