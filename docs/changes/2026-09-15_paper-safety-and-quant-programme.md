# 2026-09-15 — Paper safety, managed positions, opportunity evidence, local access security and refinements

Operator instruction of 15 September: continue with all of paper trading safety; managed paper
positions with entry evidence; why opportunities lose (the one-hour return's restart gap, testing
funding, open-interest change and liquidation skew, and combining sources by their track records);
security before any remote access; and the refinements (heatmap coverage, scheduled Hermes readings,
Fleet run progress and output, pipeline feed heartbeats, the Cockpit bundle, phone-width testing).
The operator-only acceptance items were left for last. Paper mode throughout: no execution flag,
signer, wallet or live order changed.

## How it was built

Six workstreams on their own branches and worktrees, merged into
`codex/2026-09-01-dashboard-overhaul`, plus lead changes. API session limits stopped the workstreams
twice; each resumed from its committed and uncommitted state.

| Workstream | Merged | Record |
|---|---|---|
| Fleet run progress and output, pipeline feed heartbeats, reading schedule, heatmap coverage | `cae05af` | [record](2026-09-15_fleet-pipeline-reading-schedule.md) |
| One-hour return restart gap, positioning candidates | `8a5480d` | [record](2026-09-15_restart-gap-and-candidates.md) |
| Evidence combination by track record | `2a0d748` | [record](2026-09-15_evidence-combination.md) |
| Local access hardening and security review | `2c1e3c0` | [record](2026-09-15_local-access-hardening.md) |
| Paper risk engine | `d1ee36c`, integrated `a43559e` | [record](2026-09-15_paper-risk-engine.md) |
| Managed paper positions | `21af3fb` | [record](2026-09-15_managed-paper-positions.md) |

Lead changes: page-level code splitting (`86e2de9`), the every-page QA script (`1a7062f`), the Fleet
stored-output fallback (`ec48165`), the Positions default venue and the Cockpit icon (`8c26bd2`), and
the resolution of the managed positions merge (risk hooks in `entry_admission` and on close, the
unaudited pause route retired, both test fakes kept under distinct names).

## What changed

### Paper trading safety
- Kill switch, separate from the pause and persistent; engaging it closes every open paper position
  through the managed paper close (book-walk fill, fees, funding so far).
- Capital ledger from 10,000 USDC: one realised entry per closed position, and funding that settles
  after a close booked as its own funding adjustment, so reconciliation stays exact.
- Limits enforced at admission under the entry lock, seeded conservative: daily loss 200 USDC,
  drawdown from peak 6%, gross exposure 35% of equity, per symbol 12%, a correlated bucket 25% at
  correlation 0.7 (measured hourly), three open positions, entry quote age 15 s, mark age 60 s. A
  daily-loss or drawdown breach pauses entries automatically; nothing raises a limit automatically.
- Restart reconciliation at startup and every five minutes, with observation-gap detection; any
  mismatch keeps entries paused with the reason.
- The unaudited `POST /state/paper-control` answers 410; pause, resume and the kill switch go through
  audited routes that record the operator's name and reason. The Paper risk panel sits on the
  Signal Ledger.
- New paper entries remain paused ("Initial paper safety review required"): resuming is the
  operator's decision.

### Managed paper positions
- Lifecycle rules v2 per style (stop, target, trailing stop, time expiry), fills walked through the
  observed book, settled hourly Hyperliquid funding in an append-only table (migration 032), entry
  evidence cut off at the entry time with a verifiable digest, eligibility over the ten tracked
  symbols.
- Live-data acceptance in an isolated rolled-back schema passed 57 of 57 checks (a NEAR long netted
  +0.10980 USDC after fees and funding; replays on real candles fired a HYPE stop and a UNI trailing
  stop and kept a BTC swing open).

### Why opportunities lose
- After an outage the one-hour return's anchor fell inside the observation hole for an hour; it now
  uses the venue's 1-minute candle close when no mark-price sample qualifies (catalog 1.8.1; median
  difference 1.6 bps, same sign 97.5% of the time).
- Nine positioning candidates in 120 pre-declared cells: none earned admission (best z +0.71 against
  a Holm bar of 3.53). No scoring configuration changed.
- Evidence combination, shadow only: on 3,727 decisions at one hour, combined sources were 3.3 points
  from outcomes against 2.9 for the base rate; log loss 0.6929 against 0.6927 (base rate) and 0.6905
  (rulebook), every difference inside its interval; no decision reached the 72.3% (long) or 39.7%
  (short) needed to cover the round trip.

### Local access security
- Every published port bound to 127.0.0.1 (8000, 3000, 8001, 8002, 8005, Redis 6379, Postgres 5432);
  changes from other web pages refused; an optional operator token, off; Cockpit credentials kept for
  the browser session only; Hermes outputs redacted at the bridges.
- Open from the review: cloudflared shares the compose network (M3); the signer checks no caller (M4);
  eight low findings.

### Refinements
- Fleet: what runs now, the last runs, the latest stored output and its full text; a failed output
  read serves runs and usage with the reason instead of failing the page.
- Pipeline: nine feed heartbeats with context-only markers.
- Timeframes: a per-band Hermes reading schedule, off by default.
- Heatmap: coverage stated; the 7-day window fills by 21 September and the 30-day window by 14 October.
- Cockpit: JavaScript loaded up front fell from 942 kB to 318 kB; pages load when opened.
- Every page at 1366 and 375 CSS pixels: no layout overflow; the Positions page's 500 (its own default
  venue refused) and the missing icon were found and fixed.

## Deploy

- Earlier on 15 September: migration 033, then market-data, state-api, core-scorer and cockpit-ui with
  the first merges; later state-api and cockpit-ui with evidence combination and the Fleet fallback.
- Final, 18:00–18:02 BST: Postgres and Redis recreated for loopback ports (volumes kept); the stale
  `031` schema_migrations row (the 14 September market history renumbering) removed; migrations 031
  and 032 applied; state-api, core-scorer, discord-reader, cockpit-ui, market-data and fusion-engine
  rebuilt and recreated; all healthy.

## Verification

- Tests on the deployed tree (`a43559e`): root 1019, state-api 401, market-data 160, exec-hl-svc 3,
  signer-svc 10; Cockpit 97 tests; build clean.
- Security checks after the deploy: 12 of 13 at once (ports, reachability, access policy, cross-site
  refusal, webhook exemption, callers), and the thirteenth once the fleet bridge posted its next
  snapshot at 17:06:34 UTC over 127.0.0.1 with redaction on.
- Paper checks: 13 of 13 (migrations, tables, trigger, audit column, clean startup reconciliation,
  account 10,000 USDC, seeded limits, risk state blocked by the pause, rules v2, observer ticking,
  entries paused, old pause route 410).
- Through the Cockpit and nginx: a drawing saved (POST 200) and undone (DELETE 200) under the origin
  check; Settings states the access policy; the Paper risk panel shows equity 10,000 USDC with entries
  paused. The one-hour return is present for all ten markets.
- Every page on the final build (`tools/qa_all_pages.cjs`, 20 pages at 1366 and 375 CSS pixels): 40
  page views, no page or console errors, no horizontal overflow. Screenshots:
  `E:/Visual QA/TradeSync Visual QA/Current Reviews/2026-09-15-all-pages-final`. Physical phones remain
  the operator's to check.

## Found on the way

- 15 September 07:22–10:42 BST: the PC was in Modern Standby, which froze Docker without restarting
  containers; verdicts stopped. Not a TradeSync fault.
- Postgres in-place crash resets ("server process exited with exit code 2") four times on
  13 September and once on 15 September at 11:26 UTC, during cancelled large scans; cause not
  established, shared memory ruled out.
- An unnamed client held the paper entry lock idle in transaction for over ten minutes earlier on
  15 September; none held it at deploy.

## Still open

- Operator: resume paper entries when satisfied; send one real TradingView alert through the Pine
  webhook; Android and iPhone notification receipt; the watch-only wallet with a public address; the
  WalletConnect project ID; optionally switch on the operator token.
- Security findings M3, M4 and L1–L8.
- A kill-switch exit held for a thin book and filled later has no kill-switch close audit row.
- The frozen research trial specification v1 still names BTC, ETH, SOL and scenario funding; source
  comparison does not yet evaluate the new entry evidence.
- Target, time expiry and a gap at a candle's open are proven by unit tests only; partial fills are
  not modelled.
- `services/state-api/app/main.py` (about 3,400 lines) and `services/market-data/app/main.py` (about
  1,100) still exceed the file-size rule.
- The cause of the Postgres resets.
