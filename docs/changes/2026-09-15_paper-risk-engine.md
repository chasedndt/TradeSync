# Paper risk engine — 15 September 2026

Branch `claude/paper-risk` from `db27305`. Source, tests and isolated acceptance only:
migration 031 is **not applied** and nothing is deployed. Paper only. `DRY_RUN`,
`EXECUTION_ENABLED`, signer, wallet and execution paths are untouched, and nothing
here grants execution authority.

## What changed

### Kill switch, distinct from pause

- Pause stops new entries. The kill switch stops new entries **and** closes every open
  paper position at its next observed executable quote with exit reason `kill_switch`,
  through the lifecycle's own exit (`tradesync_core.paper_kill`). A position without a
  fresh quote stays open, is listed as pending and is retried by the monitor every 15 s.
  No price is assumed.
- Engaging takes entry lock 230914, records the kill, and switches the persistent pause
  on in one transaction, so an entry either committed before the kill or sees it.
- Resuming after a kill needs `confirm: true` (the Cockpit also asks for a typed
  `RESUME`). It is refused while any paper position is still open, and it leaves new
  entries paused until they are resumed separately.
- Pause, kill, resume and every kill-switch close are audited with operator and reason
  (`managed_paper_control_events.operator`, `paper_kill_switch_events`). Resuming entries
  is refused while the kill switch, reconciliation or a standing loss or drawdown breach
  keeps them paused.

### Capital accounting (`paper_account`, `paper_account_ledger`)

- Starting capital from `PAPER_STARTING_CAPITAL_USDC` (default 10,000) becomes the
  first, single capital entry when the account is created. A later setting change does
  not rewrite the ledger; the account endpoint reports the difference.
- Each close appends one realised entry: gross after slippage, less fees and funding.
  Slippage is inside the fill prices, so it is reported beside gross and never subtracted
  twice. Funding is the frozen scenario unless the lifecycle records
  `funding_settled_usdc`; the one adapter is `FUNDING_FIELDS` in
  `tradesync_core/paper_account_ledger.py`.
- Amounts are quantised to 1e-8 USDC, so a recompute from closing events equals the
  stored balances exactly. The ledger, equity peaks and audit rows are append-only
  (database triggers refuse UPDATE, DELETE and TRUNCATE).
- Open positions are marked at their latest received exit-side observation, after the
  fees and funding they would pay to close there (entry less round-trip fees before a
  first observation). Figures reported: equity, cash, gross and per-symbol exposure,
  P&L per UTC day (realised plus the change in unrealised across the day), peak equity
  (a recorded high-water mark sampled every monitor tick) and drawdown.
- A close is booked inside the transaction that stores it, under a savepoint: if
  booking fails the close still stands and reconciliation reports the missing entry.

### Limits (`paper_risk_limits`), enforced at admission under lock 230914

Operator-editable, persisted, audited with previous and new values
(`paper_risk_limit_events`). Only the audited route writes a limit; nothing raises one
automatically. Seeded defaults:

| Limit | Default | Refusal code |
|---|---|---|
| Daily loss (realised plus unrealised since UTC day start) | 200 USDC | `DAILY_LOSS_LIMIT`, and `DAILY_LOSS_BUDGET` when planned risk would pass it |
| Drawdown from peak | 6% | `DRAWDOWN_LIMIT`, and `DRAWDOWN_BUDGET` for planned risk |
| Gross exposure / equity | 35% | `GROSS_EXPOSURE_LIMIT` |
| Per-symbol exposure / equity | 12% | `SYMBOL_EXPOSURE_LIMIT` |
| Correlated bucket exposure / equity | 25% | `CORRELATED_EXPOSURE_LIMIT`; no current measurement: `CORRELATION_UNAVAILABLE` |
| Correlation that joins a bucket | 0.7 (absolute) | — |
| Concurrent positions | 3 | `MAX_POSITIONS_LIMIT` |
| Entry quote age | 15 s | `STALE_ENTRY_QUOTE` |
| Open-position mark age | 60 s | `STALE_POSITION_MARK` |

Refused before the limits: `KILL_SWITCH_ACTIVE`, `RECONCILIATION_PENDING` (none since
start, or older than 15 minutes), `RECONCILIATION_MISMATCH`, `LIMITS_UNAVAILABLE`,
`ACCOUNT_UNAVAILABLE`, `NON_POSITIVE_EQUITY`. The 409 detail reads
`Paper entry refused [CODE]: …` and lists any other codes. A standing daily-loss or
drawdown breach also switches the persistent pause on (operator `paper-risk-engine`,
reason and figures recorded). The existing three-position, one-per-symbol and size gates
in `managed_paper.py` still apply.

Buckets are derived, not listed: hourly measurement of absolute correlation of closed 1h
log returns over seven days (at least 120 shared returns) for the universe market-data
reports; buckets are connected groups at the operator threshold. An unmeasured entry
symbol is refused; an unmeasured open symbol counts against every bucket.

### Restart reconciliation (`paper_reconciliation_runs`, `paper_observation_gaps`)

Background loop `paper_reconciliation`: at startup, every five minutes, and on request.
From one repeatable-read snapshot it rebuilds each position from its lifecycle events
(latest by the lifecycle's own observation order), rebuilds the ledger from closing
events and checks the stored balances and peak. Gaps longer than the 45-second lifecycle
latch are recorded with start and end; a position not observed since before a restart
is an ongoing gap until its next observation. Gaps are never filled. Any mismatch
switches the persistent pause on with the reason. Monitoring resumes through
`paper_risk_monitor` (15 s) and `paper_correlation` (hourly), registered with
`background.add`.

### API

`GET /state/paper-account`, `GET /state/paper-limits`, `POST /state/paper-limits`,
`GET /state/paper-risk`, `POST /state/paper-pause`, `POST /state/paper-kill`,
`POST /state/paper-kill/resume`, `GET /state/paper-reconciliation`. Every POST needs
`operator` and a reason of five characters or more; kill and resume need `confirm: true`.

### Hooks in managed paper

`services/state-api/app/managed_paper.py` gains three lines: one import, one admission
call after the persistent pause check (`admit_entry`), and one call after each stored
lifecycle event (`record_position_event`, which books closes). Nothing else there changed.
The earlier `POST /state/paper-control` still exists and records operator `unrecorded`.

### Cockpit

Signal Ledger shows a **Paper risk** panel above Managed paper positions. It shows equity,
cash, day P&L against the daily loss limit, drawdown against its limit, exposure meters
against each limit and bucket, and P&L per UTC day. It carries pause and kill-switch
state and controls with operator, reason and confirmation dialogs, plus the last
reconciliation with its mismatches and gaps, and an audited limits editor. Every reading
shows its UTC time and a refresh control; one CSS module per component. The unaudited
pause form was removed from Managed paper positions.

## Tests and acceptance

- `tools/run_tests.py root state-api`: **root 846 passed**, 17 deselected, 2 warnings,
  49 subtests; **state-api 327 passed**. New: 43 core tests in six root files; 43
  state-api tests in six files (gate refusals, hook placement inside the real entry and
  close routes, booking, kill switch, monitor auto-pause, reconciliation restart and gaps,
  routes).
- `services/cockpit-ui`: `npm test` **66 passed** (5 new); `npm run build` succeeded.
  Only the existing Browserslist, dependency annotation and chunk-size warnings.
- `tools/qa_paper_risk_sql.py`, the isolated SQL acceptance. Two psql connections; one
  transaction rolled back; throwaway schema.
  - Covers 023, 026, 031 UP → DOWN → UP, seeds, append-only triggers, constraints, and
    state-api's gap, mark and reconciliation statements as prepared.
  - Covers lock serialisation: while A holds 230914, B's try-lock is refused, B's
    blocking attempt times out, and B's waiter acquires only after A's rollback.
  - **Live PostgreSQL 16.15, through `docker exec … psql`: 15/15 PASS, exit 0.**
    Nothing committed, schema gone, lock free.
  - The first live run caught `overlaps` as a reserved word in 031 (fixed in `bde58f4`).
  - Two runs queued behind another client holding 230914 idle in transaction for more
    than 10 minutes (not this task's). The tool now waits rather than contends, and ends
    only its own backend.
  - The same 15/15 passed on a throwaway `postgres:16` container.
- `tools/qa_paper_risk_api.py`: state-api's own routes, stores and runner against real
  SQL, rolled back, with fixture books and candles. 11/11 PASS on a throwaway
  `postgres:16` container.
  - Covers account creation, audited resume, an admitted entry, a limit change and its
    `MAX_POSITIONS_LIMIT` refusal, and the lock against a second connection.
  - Covers the kill switch closing, booking and auditing a position; a clean
    reconciliation after it; resume after kill with entries still paused; and an ongoing
    700-second gap.
  - Local PostgreSQL could not bind 127.0.0.1 on this host, inside or outside the
    sandbox, hence the container. It was removed afterwards.

## Live read-only checks, 15 September

- `GET /state/paper-control`: paused, "Initial paper safety review required" (unchanged).
  `GET /state/paper-risk`: 404, so the running build has no new code.
- Database: no 031 objects, no `operator` column, no QA schemas left; 0 positions,
  0 events, 0 control events. `schema_migrations` holds 030, the stale 031
  (`market_history`) and 033.
- Correlation from live hourly candles (GET only) over the ten-symbol universe reported
  by `/state/market/snapshots`: every symbol measured, 168 shared returns.
  - At 0.7 the buckets are {BTC, ETH, HYPE, ZEC, SOL, XRP, LINK, UNI}, {NEAR}, {PUMP}.
  - At 0.8 they are {BTC, ETH, HYPE, SOL, XRP, LINK} plus four singles.
  - Highest pairs: BTC–SOL and ETH–SOL at 0.89. Lowest: NEAR–PUMP at 0.48.
  - With default limits, a third 1,000 USDC position in the large bucket would be
    refused.

## Remaining

- Apply 031 and deploy (lead). Browser QA at 1366 and 375 px against a deployed build.
  The panel is built and tested, but not rendered against live data.
- Align `FUNDING_FIELDS` and `kill_close` with the settled-funding and lifecycle changes
  on `claude/paper-positions`. Retire the unaudited `POST /state/paper-control`.
- Peak equity is sampled every 15 s, not continuously. Exposure is gross at exit-side
  marks. No MFE/MAE, leverage or volatility-scaled limits yet.
- Find the client that held lock 230914 idle in transaction for more than 10 minutes on
  15 September. While held, it blocks admission and pause changes.

[Paper control foundation](2026-09-14_paper-control.md) ·
[Managed paper backend](2026-09-14_managed-paper-backend.md) ·
[Documentation index](../README.md)
