# 13 September: Fleet control and cost-aware trade research

## Repo-truth delta / activity

Codex / Axiom-Codex continued the Timeframes/Hermes handover and the operator's
request for realistic trades. Existing shared-checkout work preserved. No
commit, push, canonical daily-note write or public publication performed.
This file is the project-local build log, daily activity record and handover;
canonical ChaseOS ingestion remains governed-writer work.

Start: 22:33 BST, E: about 318 GiB free. Host RAM later fell below 1 GiB.
Detailed current/remaining status: [roadmap reconciliation](../ROADMAP_RECONCILIATION_2026-09-13.md).

## Implementation

- `fleet_live.py`: bounded live gateway overlay, 15s cache and explicit fallback.
- `fleet.py`: invalidate after applied directives; never bypass a 4xx denial
  using bridge fallback. Fleet UI adds filters, refresh and confirmations.
- `trade_economics.py`: actual cohort diagnostics and explicit null/coverage rules.
- `trade_replay.py`: frozen scalp/swing candidate simulation, conservative fills,
  separate temporal segments, deterministic inputs and disclosed assumptions.
- `trade_research.py`: diagnostics, evidence coverage, replay/save/list API.
  Bounded set-based latest-outcome query replaces a timed-out lateral read.
- Migration 021: durable research inputs/results, applied successfully.
- Signal Ledger `TradeResearch` panel: real economics, provenance, interactive
  research assumptions, saved runs and individual trade inspection.
- Candle start/end proxy; RSI neutral fix and non-overlap terminology.
- One Hermes test under the WSL scripts checkout now verifies the portable
  launcher's fake-runtime invocation. Original file backed up before editing.
  No live launcher/job schedule/publishing behavior was changed.

## Verification

- `.venv/Scripts/python.exe tools/run_tests.py root state-api`:
  **633 root passed**, 17 integration tests deselected, 2 warnings,
  10 subtests passed; **125 State API passed**.
- Final `.venv/Scripts/python.exe tools/run_tests.py state-api market-data exec-hl-svc signer-svc`:
  **125 / 119 / 3 / 10 passed**, respectively. Integration tests remain
  intentionally separate; the real API and browser acceptances above provide
  bounded runtime evidence, not a complete trading/security certification.
- `npm run build`: TypeScript/Vite passed. Existing bundle-size, Browserslist
  freshness and dependency annotation warnings remain; no claim of clean
  security audit.
- Docker State API built from source. Cockpit packaged from host-built `dist`
  using `ops/cockpit-prebuilt.Dockerfile`, then only those services replaced.
  Docker initially failed to receive a Cockpit stop event; bounded compose
  retry recovered the task's replacement. No volume deletion or stack shutdown.
- Live diagnostic GET succeeds: 598 resolved, -867.8501 USDC, profit factor
  0.377, no +3% captured moves. Full denominators in reconciliation.
- Live evidence GET succeeds with actual intake and claim counts.
- Live Fleet GET reports gateway source, live status, 85 jobs.
- Both BTC replay POSTs succeeded and persisted; GET runs read back both records.
  Scalp holdout +5.02 USDC/2 trades; swing -27.72 USDC/8. Not proof of skill.
- `node tools/qa_fleet_research.cjs`: real-data panels at 1366 and 375 pixels;
  no page overflow or uncaught errors; filtering works; dismissed schedule
  confirmation sends **zero** directives. Screenshots visually inspected.
  Repeated on the final build with saved swing run expanded: UTC sample/split
  dates and individual development/holdout trades render at both widths.
- Earlier `node tools/qa_context_timeframes.cjs`: populated context fit at
  1366/1024/768/375 and ETH feature-link/scroll/chart checks at 1366/375 passed.
- Completed ETH Hermes timeframe reading rendered, about 165 seconds. Restart
  clears its transient in-memory job status; receipt is distinct from cache.
- Hermes focused suite before fix: **104 passed, 1 failed** (portable launcher
  hard-coded path assertion). Corrected isolated launcher test: **1 passed**.
  Full post-fix focused suite: **105 passed in 61.58 seconds**, using the same
  eight files as the executor with `--capture=sys -p no:cacheprovider` and E:
  temporary/cache directories. No scheduled self-review was manually run to
  manufacture success. The executor's own default capture/cache environment
  still needs the next normal job receipt.

- Final 23:26 BST health snapshot: State API, Cockpit, market-data, scorer,
  fusion, signer, PostgreSQL, Redis and tunnel healthy; Discord reader running
  without a healthcheck. E: 341.53 GB free. `git diff --check` passed (existing
  Windows LF/CRLF conversion warnings only).

QA: `E:/Visual QA/TradeSync Visual QA/Current Reviews/2026-09-13-context-timeframes/fleet-research`.
Hermes reading screenshot: sibling `live/hermes-reading.png`.

## Remaining unknowns and next safe action

Refer to the complete handover register and overall backlog in the reconciliation.
In particular: scheduled self-review/weekly recap acceptance, genuine closeout,
incremental graph scan, era/bootstrap analysis, continuous candle archive,
immutable external-entry evidence, profitable held-out/forward strategy,
managed paper portfolio, wallet security/reconciliation and live execution
gates are **not complete**. Host-memory contention can degrade otherwise healthy
services; component availability checks are not a long-running reliability soak.

## Learning checkpoint

Start with percentages, descriptive statistics and experimental design; these
are topic mappings, not invented Year 2 module names. Supply the syllabus for
an exact module mapping.

- One basis point is 0.01%. 4.5 bps per fill means 0.045% per fill.
- On 1,000 USDC, a 0.24% favourable move is about 2.40 USDC gross, before costs.
  Two 4.5-bps fees and two 2-bps slippage assumptions are approximately 1.30 USDC
  at unchanged notional. Funding adds a separate cost or credit in reality.
  Do not subtract slippage twice if it already changed the simulated fills.
- Expectancy here means total recorded net P&L divided by resolved trades:
  -867.8501 / 598 = approximately -1.4513 USDC per trade.
- Profit factor means total winning net P&L divided by absolute losing net P&L.
  Below one means losses exceed wins. Missing/no-loss denominators display a
  dash, not an invented infinity or zero.
- Practice: calculate net proceeds for a 0.5% move on 1,000 USDC using the
  same approximate round-trip costs; then double notional and explain why
  that changes dollar P&L but does not create a statistical edge.
- Holdout means data reserved for testing a fixed idea. Repeatedly changing
  the idea after seeing that data destroys the separation.
