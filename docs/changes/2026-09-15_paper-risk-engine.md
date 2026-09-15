# Paper risk engine — 15 September 2026

Branch `claude/paper-risk`, integrated with managed paper positions at `21af3fb`.
Source, tests and isolated acceptance only: migration 031 is **not applied** and nothing is
deployed. Paper only. `DRY_RUN`, `EXECUTION_ENABLED`, signer, wallet and execution paths are
untouched, and nothing here grants execution authority.

## What changed

### Kill switch, distinct from pause

- Pause stops new entries. The kill switch also closes every open paper position.
- The close goes through the managed paper close (`tradesync_core.paper_kill`,
  `app/paper_kill_switch.py`), the way the observer closes:
  - funding settled so far is stored and netted first;
  - the exit walks a fresh observed book for the position's quantity;
  - the taker fee is paid at that fill.
- The rule recorded is `kill_switch`. A stop, target or expiry fired at the same observation
  is kept beside it as `coincided_rule`.
- A position without a fresh usable book stays open, is listed as pending, and is retried by
  the monitor every 15 s. A book too thin for the quantity leaves the kill-switch exit owed
  (`pending_exit`) until an observation can fill it. No price is assumed.
- Engaging takes entry lock 230914, records the kill and switches the persistent pause on in
  one transaction. An entry either committed before the kill or sees it.
- Resuming after a kill:
  - needs `confirm: true` (the Cockpit also asks for a typed `RESUME`);
  - is refused while any paper position is still open;
  - leaves new entries paused until they are resumed separately.
- Pause, kill, resume and every kill-switch close are audited with operator and reason
  (`managed_paper_control_events.operator`, `paper_kill_switch_events`). Resuming entries is
  refused while the kill switch, reconciliation or a standing loss or drawdown breach keeps
  them paused.

### Capital accounting (`paper_account`, `paper_account_ledger`)

- **Starting capital** from `PAPER_STARTING_CAPITAL_USDC` (default 10,000) becomes the first,
  single capital entry when the account is created. A later setting change does not rewrite
  the ledger; the account endpoint reports the difference.
- **Realised entry.** A closed position gets one, from the state its `closed` event recorded:
  gross from the fill prices, less both taker fees and settled funding. Funding comes from
  `funding_usdc` (`settled_partial` while an hour is unpublished), or `funding_scenario_usdc`
  in older states. Each fill's cost against the mid (`slippage.entry`/`exit.cost_usdc`) is
  already inside the prices. It is reported beside gross and never subtracted twice.
- **Funding adjustment.** Funding settled after the close becomes a `funding_adjustment`
  entry (see Late funding).
- **Exact identity.** Amounts are quantised to 1e-8 USDC, so a recompute from the events
  equals the stored balances exactly. The ledger, equity peaks and audit rows are
  append-only: triggers refuse UPDATE, DELETE and TRUNCATE.
- **Marks.** Open positions are marked at their latest observation, after the fees and
  funding they would pay to close there. Figures:
  - equity and cash;
  - gross and per-symbol exposure;
  - P&L per UTC day (realised entries and adjustments, plus the change in unrealised);
  - peak equity (a high-water mark sampled every monitor tick) and drawdown.
- **Booking** happens inside the transaction that stores the closed state, under a savepoint.
  If booking fails, the close or settlement still stands and reconciliation reports what is
  missing.

### Late funding

Hyperliquid publishes each hour's funding rate after the hour. A position can close before its
last hours are published. `managed_paper.update` later rewrites the closed position with those
settlements and stores a `funding_settled` event.

- **Booking.** `update` hands every stored closed state to `record_position_event`: the close,
  and each `funding_settled` rewrite. `paper_account_store.book_position` then:
  1. books the realised entry once, from the `closed` event's state, even if booking first
     runs after late funding arrived;
  2. compares the state's quantised `funding_usdc` with the funding already charged to that
     position (realised plus earlier adjustments);
  3. appends one `funding_adjustment` for the change, if nonzero. Its funding is the change;
     its amount is minus the change; gross, fees and slippage are zero.
- **Idempotent.** Booking the same state again appends nothing.
- **Exact.** Adjustments telescope: however many are booked, they sum to the latest funding
  less the funding at the close. Cash and realised P&L move by exactly minus each change, and
  the funding total moves by exactly the change.
- **Reconciliation** checks the realised entry against the `closed` event, and a position's
  adjustments against its lifecycle-latest state, which includes `funding_settled` events.
  Unbooked or double-booked late funding is `LEDGER_FUNDING_ADJUSTMENT_DIFFERS`, and pauses
  entries until an operator resumes after a clean run.

### Limits (`paper_risk_limits`), enforced at admission under lock 230914

Operator-editable, persisted, and audited with previous and new values
(`paper_risk_limit_events`). Only the audited route writes a limit; nothing raises one
automatically.

| Limit | Default | Refusal code |
|---|---|---|
| Daily loss (realised plus unrealised since UTC day start) | 200 USDC | `DAILY_LOSS_LIMIT`; `DAILY_LOSS_BUDGET` when planned risk would pass it |
| Drawdown from peak | 6% | `DRAWDOWN_LIMIT`; `DRAWDOWN_BUDGET` for planned risk |
| Gross exposure / equity | 35% | `GROSS_EXPOSURE_LIMIT` |
| Per-symbol exposure / equity | 12% | `SYMBOL_EXPOSURE_LIMIT` |
| Correlated bucket exposure / equity | 25% | `CORRELATED_EXPOSURE_LIMIT`; no current measurement: `CORRELATION_UNAVAILABLE` |
| Correlation that joins a bucket | 0.7 (absolute) | — |
| Concurrent positions | 3 | `MAX_POSITIONS_LIMIT` |
| Entry quote age | 15 s | `STALE_ENTRY_QUOTE` |
| Open-position mark age | 60 s | `STALE_POSITION_MARK` |

- **Checked before the limits:** `KILL_SWITCH_ACTIVE`, `RECONCILIATION_PENDING` (none since
  start, or older than 15 minutes), `RECONCILIATION_MISMATCH`, `LIMITS_UNAVAILABLE`,
  `ACCOUNT_UNAVAILABLE`, `NON_POSITIVE_EQUITY`.
- **Refusal detail** reads `Paper entry refused [CODE]: …` and lists any other codes.
- **Automatic pause.** A standing daily-loss or drawdown breach switches the persistent pause
  on, with operator `paper-risk-engine` and the figures recorded.
- **Existing gates stay.** The managed paper portfolio cap (three open, one per symbol) and
  its size gates still apply.
- **Buckets are derived, never listed.** The correlation job measures absolute correlation of
  closed 1h returns over seven days (at least 120 shared returns) for the universe
  market-data reports. A bucket is a connected group at the operator threshold. An unmeasured
  entry symbol is refused; an unmeasured open symbol counts against every bucket.

### Restart reconciliation (`paper_reconciliation_runs`, `paper_observation_gaps`)

Background loop `paper_reconciliation` runs at startup, every five minutes and on request.
From one repeatable-read snapshot it:
- rebuilds each position from its lifecycle events and checks the stored state. The latest
  event is chosen by the lifecycle's own order: time evaluated through, observations plus
  candles, closed after open, then funding hours settled.
- rebuilds the ledger from the `closed` and later funding events, and checks stored balances
  and the peak;
- records gaps longer than the lifecycle's latch (`COMMON.observation_gap_s`, 45 s) with start
  and end. A position not observed since before a restart is an ongoing gap until its next
  observation. Gaps are never filled.

Any mismatch switches the persistent pause on with the reason. Monitoring resumes through
`paper_risk_monitor` (every 15 s) and `paper_correlation` (hourly).

### API

- `GET /state/paper-account`, `GET /state/paper-limits`, `GET /state/paper-risk`,
  `GET /state/paper-reconciliation`.
- `POST /state/paper-limits`, `POST /state/paper-pause`, `POST /state/paper-kill`,
  `POST /state/paper-kill/resume`. Every POST needs `operator` and a reason of five
  characters or more; kill and resume also need `confirm: true`.
- The merge retired `POST /state/paper-control`: it now returns 410, pointing to
  `POST /state/paper-pause`.

### Hooks in managed paper

- `entry_admission` calls `admit_entry(conn, symbol=symbol, plan=plan)` right after the
  persistent pause check, under lock 230914, and before the portfolio cap.
- `update` calls `record_position_event(conn, identity, result)` whenever the stored result is
  closed.

### Cockpit

Signal Ledger shows a **Paper risk** panel above Managed paper positions:
- equity and cash, day P&L against the daily loss limit, drawdown against its limit;
- exposure meters for each limit and bucket, and P&L per UTC day;
- pause and kill-switch state and controls, with operator, reason and confirmation dialogs;
- the last reconciliation with its mismatches and gaps;
- an audited limits editor.

Every reading shows its UTC time and a refresh control. One CSS module per component.

## Integration with managed paper positions (`21af3fb`)

The fast-forward left 19 unit tests failing (root 8, state-api 11). Changes, in `8086a89`,
`92d8b75`, `74ee9f9` and `5f9cb52`:
- **Ledger:** slippage read from book-walk fill costs; the flat `slippage_bps` path is kept
  for older states only. Late funding booked as adjustments (above).
- **Kill switch:** closes through the managed close. The earlier version relabelled a v1
  close priced at the touch with flat slippage.
- **Reconciliation:** the new lifecycle order; realised entries checked against the closed
  event and adjustments against the latest state. New codes:
  `CLOSED_POSITION_WITHOUT_CLOSE_EVENT` and `LEDGER_FUNDING_ADJUSTMENT_DIFFERS`.
- **`managed_paper.update`:** books every closed state, not only `kind == 'closed'`.
- **Tests:**
  - the gate route tests use the new entry flow: lock, then pause check, then risk gate,
    then insert;
  - the two positions route tests stub the risk gate and assert its place in admission,
    including that a risk refusal stops admission before the portfolio is read;
  - new tests cover late funding in the ledger, the account store, the observer hook and
    reconciliation.
- **Migration 031, changed:**
  - ledger `kind` also allows `funding_adjustment`;
  - `position_id` is no longer column-unique: the partial unique index
    `paper_account_ledger_one_realised` keeps one realised entry per position;
  - new index `paper_account_ledger_position`;
  - every non-capital row must have amount equal to gross less fees less funding;
  - an adjustment carries zero gross, fees and slippage and nonzero funding.

## Tests and acceptance

At integration (code as committed in `74ee9f9`):
- `tools/run_tests.py`, every unit suite: root **1019 passed** (17 deselected, 2 warnings,
  49 subtests), state-api **401**, market-data **160**, exec-hl-svc **3**, signer-svc **10**.
- Cockpit: `npm test` **97 passed**; `npm run build` succeeded with only existing warnings.
- `tools/qa_paper_risk_sql.py` on a throwaway `postgres:16` container: **16/16 PASS**,
  exit 0.
  - New coverage: the funding-adjustment constraints, and state-api's booking statements
    run as prepared. An appended adjustment moves cash, funding and realised by exactly its
    amount; a repeat against the old sequence changes nothing.
  - Two defects in the tool itself were fixed on the way: an unescaped apostrophe in a
    failure message, and `CREATE TABLE AS` over an `INSERT … RETURNING`.
- `tools/qa_paper_risk_api.py`, rewritten for managed paper v2, on the same container:
  **7/7 PASS**, exit 0. Positions are seeded directly; the observer, routes, gate and runner
  are state-api's own. It checks:
  - late funding booked as a realised entry and then an adjustment of exactly the change,
    with cash and funding moved by it;
  - a gate refusal, and the lock against a second connection;
  - the kill switch through the managed close, with two settled funding hours stored and
    netted;
  - clean reconciliations, resume after kill, and an ongoing gap.
- The container was removed afterwards. No live database was touched during integration.

Before integration (`e69068c`): root 846 and state-api 327 passed, Cockpit 66, SQL acceptance
15/15 on live PostgreSQL 16.15 (rolled back) and on a throwaway container, API acceptance
11/11. That live run caught `overlaps` as a reserved word in 031 (`bde58f4`).

## Live read-only checks, 15 September (before integration)

- `GET /state/paper-control` was paused with its original reason. `GET /state/paper-risk`
  returned 404: the running build has no new code.
- Database: no 031 objects and no QA schemas; 0 positions and 0 events. `schema_migrations`
  holds 030, the stale 031 (`market_history`) and 033.
- Correlation from live hourly candles over the ten-symbol universe: all measured, 168 shared
  returns. At 0.7 the buckets are {BTC, ETH, HYPE, ZEC, SOL, XRP, LINK, UNI}, {NEAR} and
  {PUMP}. With default limits a third 1,000 USDC position in the large bucket is refused.
- A client held lock 230914 idle in transaction for more than 10 minutes (not this task's).

## Before deploying

1. **Clear the stale 031 row.** Remove `schema_migrations` row `031` (`market_history`), or
   the runner skips this 031. This 031 and 032 (managed paper funding) are independent;
   apply both.
2. **Check closed positions.** Confirm there are no closed managed paper positions before 031
   applies (live had none). Any that exist are reported unbooked and keep entries paused.
3. **Funding inputs.** The kill switch and late-funding booking use the observer's funding
   inputs: market-data `/funding-history` and prices recorded in `market_open_interest`.
   Without them a close still happens, its funding stays listed as missing, and each later
   settlement is booked as an adjustment.
4. **Starting capital.** `PAPER_STARTING_CAPITAL_USDC` is optional, default 10000, read once
   when the account is created.

## Remaining

- Deploy, then browser QA at 1366 and 375 px against live data.
- An owed kill-switch exit that the observer fills later records `kill_switch`, but writes no
  kill-switch close audit row and loses `coincided_rule`.
- Peak equity is sampled every 15 s. Exposure is gross at exit-side marks. No MFE/MAE,
  leverage or volatility-scaled limits yet.
- Find the client that held lock 230914 idle in transaction; while held it blocks admission
  and pause changes.

[Managed paper positions](2026-09-15_managed-paper-positions.md) ·
[Paper control foundation](2026-09-14_paper-control.md) ·
[Documentation index](../README.md)
