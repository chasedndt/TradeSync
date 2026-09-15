# Managed paper positions: lifecycles, measured costs and entry evidence — 15 September 2026

Branch `claude/paper-positions` in `E:\Projects\TradeSync\paper-positions-2026-09-15`, branched from
`codex/2026-09-01-dashboard-overhaul` at `db27305`. Project-local build record.
Nothing here is deployed: no container was built, started, stopped or restarted, no migration was
applied, and no public table was written. Paper only; no order, wallet, signer or execution path
was touched.

## What changed

### Lifecycle rules per holding style, in one versioned place

`libs/tradesync_core/tradesync_core/paper_lifecycle_rules.py` declares every parameter under
`managed-paper-lifecycle-v2`. A position freezes the rules it opened under, version included. The
numbers are engineering hypotheses, not validated edges; changing one is a new version.

| Style | ATR | Stop | Target | Trailing stop starts | Trail distance | Time expiry |
|---|---|---|---|---|---|---|
| Scalp | 14 closed 15m candles | 1.5 × ATR | 2 × stop distance, at least 0.4% | 1 × stop distance in favour | 1 × ATR | 3 h |
| Intraday | 14 closed 1h candles | 1.5 × ATR | 2 × stop distance, at least 0.8% | 1 × stop distance in favour | 1.25 × ATR | 24 h |
| Swing | 14 closed 4h candles | 2 × ATR | 2 × stop distance, at least 2% | 1.5 × stop distance in favour | 1.5 × ATR | 7 days |

Shared gates (also in that module): notional at most 1,000 USDC, planned risk at most 50 USDC, quote
at most 30 s old, spread at most 20 bps, stop distance at most 10% of entry, reward at least 3 × the
cost budget and a net reward-to-risk of at least 1.25, a latched observation gap above 45 s, and
opportunities at most five minutes old.

Exits (`paper_exits.py`) are evaluated on observations in time order, in one rule order: the stop in
force (initial, or the trailing stop once tighter), then the target, then the time expiry, then an
operator close. Every exit is a market exit at the observation that fired it:

- **Quotes** (the live path): the exit-side touch (bid for a long, ask for a short). A price already
  past the stop when seen fills at that observed price, never at the stop (`gap_fill`).
- **Closed candles** (replays, and available for restart reconciliation): the open is checked first,
  so a gap fills at the open; inside a candle the stop comes before the target (`ambiguous_candle`
  when both were reached), and the trailing stop moves only after a candle is checked, so a candle's
  own high cannot tighten the stop its own low then hits. An exit inside a candle is dated at its open.
- The trailing stop only tightens. An exit the displayed book cannot fill stays owed (`pending_exit`)
  and fills at the next observation that can, with both observations recorded.

Every exit records the rule, its level, the trigger price, the observation that fired it, the
observation that filled it and the fill. The rule formerly called `time_exit` is now `time_expiry`.

### Costs

- **Fees**: the existing published source, `paper_rehearsal.HYPERLIQUID_BASE_FEES` (base taker
  0.045%, read 14 September from the Hyperliquid fee page), charged on both fills; the schedule is
  frozen into each plan.
- **Slippage** (`paper_depth.py`): the entry walks the observed book outward from the touch for the
  position's notional, the exit walks it for the quantity. Half spread, depth past the touch and the
  total against the mid are recorded with the levels taken and the book snapshot (source, precision,
  observed and received times). Too little displayed depth is refused, never extrapolated. Candle
  entries and exits move the reference price (open, or level) by the cost of the book recorded at or
  before that candle; `market_depth_snapshots` holds books aggregated to 3 significant figures, so
  that cost is an upper bound and is labelled with its precision. The flat 2 bps assumption is gone.
- **Funding** (`paper_funding.py`, `services/state-api/app/paper_funding_store.py`, migration 032):
  Hyperliquid's settled hourly rates for each settlement strictly after entry and at or before exit,
  valued at the oracle price recorded in `market_open_interest` nearest the settlement (five minutes
  before to one minute after; the mark from that row if no oracle price). Each settlement is stored
  once, append-only, with its rate, price, price source and receipt time. Open positions show funding
  accrued so far. An hour whose rate or price is not recorded yet stays listed as missing; nothing is
  estimated. Closed positions keep settling for a day after exit. The constant adverse funding
  scenario is gone from profit and loss.
- **Net** = gross from the fill prices − fees − settled funding. Spread and depth are inside the fills
  and are not subtracted again. The entry gates still need a budget before any settlement exists:
  they use the mean absolute settled rate of the rows seen before entry, floored at a declared
  0.125 bps an hour. That planning number gates entries only.

### Entry evidence, frozen at entry

`paper_entry_evidence.py` (schema `managed-paper-entry-evidence-v2`) lists nine items for every entry,
each present with records or missing with its reason: the opportunity; the scorer verdict (the linked
`signals` row); feature observations (market-data `/features`, each at its metric read time); the
latest timeframe measurement (`/state/market/horizons`, `computed_at` per part); resting-liquidity
walls near price (latest recorded aggregated book and the entry book); liquidations received in the
hour before entry; open interest (latest and an hour earlier); settled funding rows for the day
before entry; and the latest thesis edition. Every record carries its source, `observed_at`,
`received_at` and `age_s` at entry.

A record observed or received after the entry time, or missing either time, is excluded and listed
with the reason. Received times come from what TradeSync recorded: `recorded_at` for recorded books
and open interest, `received_at` for liquidations, `created_at` for scorer verdicts, the creation time
for TradeSync's own opportunities, the response time for HTTP answers, and the read time for thesis
editions (their rows keep no insert time). Every source is bounded to about three seconds and fails
to a missing marker; all of them answer before the entry book is requested.

The document carries `item_order`, the cut-off rule, the plan inputs (entry book, ATR candles, ATR) and
the earlier Bybit receipt and book-history context in its previous shape (the source comparison reads
it). Its SHA-256 is computed over canonical JSON that reads back from JSONB unchanged; it is stored in
the existing immutable entry record (migration 023's trigger) and the evidence route reports
`digest_verified`.

### Eligibility

Fresh (at most five minutes), directional opportunities for every symbol market-data reports it
tracks (`editions.tracked_symbols`); no symbol is named in code. An unreadable universe admits
nothing. `tradesync_core.paper_eligibility` is the one rule for both the candidates list and entry
admission.

### State API

- `POST /state/paper-positions`: eligibility, evidence, plan, then `entry_admission(conn, symbol, plan,
  captured_at)` under advisory lock 230914. **`entry_admission` in
  `services/state-api/app/managed_paper.py` is the single place for any further admission check; a
  comment marks where the risk engine's `admit_entry` call goes.** It is deliberately not named
  `admit_entry`: the risk branch imports `admit_entry` from `app.paper_risk_hooks`, and a function of
  the same name here would shadow that import and silently skip the risk gate.
- `GET /state/paper-positions/candidates`, `GET /state/paper-positions/rules`,
  `GET /state/paper-positions/{id}/funding`; `GET /state/paper-positions/{id}/evidence` adds
  `digest_verified`.
- The observer stores settlements as they are published and never lets a funding failure block quotes
  or exits. `register()` returns its `update` and `loop` handles for tooling.

### Cockpit

Signal Ledger's managed paper panel is split into one component per file under
`src/components/ledger/paper/` with CSS modules. Per position: the style's rules with exact expiry time
and where the trail stands; the exit rule that fired, the observation that fired it and whether the
fill started past the level; a fees, slippage and funding table with how each was measured and the
stored funding rows on demand; and the entry evidence item by item with observed and received times,
ages, missing markers, exclusions and the digest check. The open form lists candidates for the whole
API universe and shows the chosen style's rules from the rules route.

### Migration 032

`ops/migrations/032_managed_paper_funding.sql`: `managed_paper_funding`, primary key
`(position_id, settled_at)`, settlements on the hour only, and a trigger refusing update and delete.

### Tooling

- `tools/run_in_state_api.py`: runs a QA script inside the running state-api container against this
  checkout's code held in memory; nothing is written into the container.
- `tools/qa_managed_paper_positions.py` with `tools/qa_paper_live.py` and `tools/qa_paper_replay.py`:
  the live-data acceptance below.
- `tools/qa_managed_paper_ui.cjs`: browser fixtures updated for the new routes and fields.

## Verification

### Tests

Project venv, `tools/run_tests.py`, on the committed branch:

- root: **840 passed**, 17 deselected, 2 warnings, 49 subtests passed (803 at `db27305`). New:
  `test_paper_exits` 14, `test_paper_depth` 6, `test_paper_funding` 6, `test_paper_entry_evidence` 5,
  `test_paper_lifecycle_rules` 3, `test_paper_eligibility` 2, one more in `test_managed_paper` (9).
- state-api: **297 passed** (284 at `db27305`). New: `test_paper_positions_routes` 11,
  `test_paper_entry_rows` 2 (a liquidation item cut at the 500-row cap says so).
- The cut-off is proven twice: `tests/test_paper_entry_evidence.py::test_evidence_received_after_the_entry_time_is_excluded`
  (records received or observed after entry are excluded with their reason), and
  `services/state-api/tests/test_paper_positions_routes.py::test_entry_freezes_evidence_cut_off_at_entry_with_a_verifiable_digest`
  (through the route: a feature stamped after the entry is excluded, every source answers before the
  entry book is requested, and the stored digest verifies).

Cockpit, `services/cockpit-ui` on the committed tree:

- `npm test`: **64 of 64 passed**, including `paper-format.test.mjs` (3 new) and the retired-wording scan
  over every rendered string.
- `npm run build` (`tsc` and Vite): **passed**, built in 26.40 s. The existing chunk-size, Browserslist-data
  and dependency-annotation warnings remain.
- Browser QA (`tools/qa_managed_paper_ui.cjs`) not run: Playwright is not installed in this environment.

### Live-data acceptance

From the worktree root. The script runs inside the running state-api container against this checkout's
code, held in memory. Everything is written to one isolated schema inside one transaction and rolled
back; public tables are only read.

```powershell
E:\Projects\TradeSync\dashboard-overhaul-2026-09-01\.venv\Scripts\python.exe tools\run_in_state_api.py `
  tools\qa_managed_paper_positions.py --with tools\qa_paper_live.py --with tools\qa_paper_replay.py -- 10 6
```

#### Final run, 15:53:44–16:04:53 UTC: 57 of 57 checks passed

Code at `c8d5339`. The state-api container peaked at 284 MiB of its 512 MiB limit. Timed so the live
position held through the 16:00 settlement.

**A. Live position: NEAR-PERP intraday LONG.**

- *Opportunity*: `f07d8f9a-09f4-4b9e-ae4e-95f778819951` (snapshot 15:52:42.968, 62.5 s old), the first of
  5 fresh candidates across the ten-market universe. Admitted at the first style tried, no refusal.
- *Entry, 15:53:50.830 UTC*: book seen 15:53:50.694, bid 2.3661, ask 2.3663. The fill took 1 of 10
  levels: 105.65017115 NEAR at 2.3663 for 250 USDC. Half spread 0.423 bps, depth 0 bps, 0.010565 USDC
  against the mid.
- *Plan*: ATR (14 closed 1h candles) 0.0387929. Stop 2.3081107, target 2.4826786. The trailing stop
  starts at 2.4244893 and trails 0.0484911 behind the best price. Time expiry 16 September 15:53:50.830
  UTC. Planned risk 6.47 USDC.
- *Ten minutes live*: 38 observer updates, 39 quote observations, largest gap 17.91 s, no refused quote.
  Best bid 2.3791, so the trail never activated.
- *Exit*: operator close on the quote at 16:03:54.842 UTC (bid 2.3695, ask 2.3696). Fill 2.3695, one
  level, half spread 0.211 bps, 0.005283 USDC.
- *Fees*: entry 0.1125 USDC, exit 0.1126521 USDC.
- *Settled funding*: 1 of 1 settlement.
  - The 16:00 rate of 0.00125% (premium −0.0001676) was received at 16:00:07.807.
  - It was valued at the oracle price 2.36866, recorded for 15:58 (the nearest minute recorded when the
    row was stored, inside the window).
  - Payment 0.0031281 USDC paid, stored once. A later update and delete of that row were both refused.
- *Result*: gross +0.3380805, fees 0.2251521, funding 0.0031281, **net +0.1098003 USDC**.
- *Entry evidence* (digest `2b4d7369…15fb0`, verified after the JSONB round trip, nothing excluded). Ages
  at entry:
  - opportunity 67.9 s; scorer verdict 68.0 s;
  - 22 feature observations (newest 7.6 s);
  - recorded book plus entry book (newest 0.14 s);
  - 7 liquidations (newest 17 min 37 s); open interest 50.8 s;
  - 24 funding rows (newest, the 15:00 settlement, 53 min 51 s);
  - thesis edition 6 h 5 min.
  - Timeframe measurement missing: `unavailable: ReadTimeout`.

**B. Replays on the last six hours of real 1-minute candles.** All ten markets were tried and all three
styles replayed. Refused, all "Insufficient reward after declared costs": scalp on BTC, ETH, SOL, HYPE,
ZEC, NEAR and PUMP; intraday on BTC, ETH and SOL.

| | BTC-PERP swing LONG | HYPE-PERP intraday LONG | UNI-PERP scalp LONG |
|---|---|---|---|
| Opportunity | `03bbe006…` 10:08:33 | `e3a3fc53…` 10:43:15 | `aca27886…` 10:43:21 |
| Entry (UTC) | 10:09:00 | 10:44:00 | 10:44:00 |
| Candle open → fill | 77,000 → 77,050.03 | 79.362 → 79.41201 | 6.7126 → 6.7176057 |
| Recorded book cost | 6.50 bps (book 10:07) | 6.30 bps (book 10:43) | 7.46 bps (book 10:43) |
| ATR | 780.43 (4h) | 0.7385 (1h) | 0.0609857 (15m) |
| Stop / target | 75,489.18 / 80,171.75 | 78.30426 / 81.62751 | 6.6261271 / 6.9005628 |
| Candles evaluated | 354, none missing | 211, none missing | 35, none missing |
| Exit | none: still open | **stop** at 14:14:00 | **trailing stop** at 11:18:00 |
| Candle that fired it | — | O 78.521 H 78.529 L 78.221 C 78.230 | O 6.8002 H 6.8002 L 6.7752 C 6.7826 |
| Level → fill | — | 78.30426 inside the candle → 78.25441 (6.37 bps) | 6.7814143 inside the candle → 6.7714416 (14.71 bps) |
| Trail | not started (best 77,209) | not started (best 79.777) | started at 6.8090842, best 6.8424, stop 6.7814143 |
| Fees | 0.1125 + 0.11167 estimated | 0.1125 + 0.11086 | 0.1125 + 0.11340 |
| Settled funding | 6 of 6 (11:00–16:00): 0.018658 paid | 4 of 4 (11:00–14:00): 0.011705 paid | 1 of 1 (11:00): 0.003129 paid |
| Gross / net (USDC) | −1.84000 / −2.08283 marked | −3.64426 / **−3.87933** | +2.00354 / **+1.77451** |

- Funding rates and recorded oracle prices, in settlement order:
  - BTC: every hour 0.00125%, at 77,044.9, 76,935.0, 76,967.0, 76,636.0, 75,944.9 and 76,512.0.
  - HYPE: 0.00094047% at 79.4, then 0.00125% at 79.0405, 79.5375 and 79.137.
  - UNI: 0.00125% at 6.7268.
- Evidence as of each entry: kept the opportunity, scorer verdict, recorded book, open interest and the
  liquidations received in the hour before (6, 2 and 10). Excluded the features (observed after entry),
  and the funding rows (24) and thesis edition (received after entry). The BTC timeframe measurement (2
  records) was excluded as observed after entry.

Also passed: migration 032 DOWN then UP in the isolated schema; rollback with the schema gone, public
positions 0 before and after, and public entries still paused. Confirmed separately afterwards,
read-only: no `qa_%` schema, `managed_paper_funding` absent from `public`, no open transaction, and no
PostgreSQL restart since 15:53.

#### Earlier run, 15:04:16–15:14:53 UTC: 29 of 30 checks passed

Code at `f998fc4`, scripts as committed in `34c9658`. The state-api container peaked at 315 MiB.

**A. Live position.**

- *Opportunity*: the universe read from the API was ten markets (BTC, ETH, HYPE, ZEC, SOL, XRP, NEAR, PUMP,
  LINK, UNI). The first candidate was BTC-PERP LONG `b54fc1f4-d1e6-4fe7-8e97-dbdb589cfe12` (snapshot
  15:03:52.546, 26.2 s old). Intraday, the first style tried, was admitted with no refusal.
- *Entry, 15:04:22 UTC*: book seen 15:04:22.855, bid 75,989, ask 75,990. The fill took 1 of 10 levels:
  0.003289906566653507 BTC at 75,990 for 250 USDC. Half spread 0.066 bps, depth 0 bps, 0.0016 USDC
  against the mid.
- *Plan*: ATR (14 closed 1h candles) 434.93. Stop 75,337.61, target 77,294.79. The trailing stop starts
  at 76,642.39 and trails 543.66 behind the best price. Time expiry 16 September 15:04:22 UTC. Planned
  risk 2.45 USDC.
- *Ten minutes live*: 39 observer updates, 40 quote observations, largest gap 17.04 s, no refused quote.
  Best bid 76,071, so the trail never activated.
- *Exit*: operator close on the quote at 15:14:31.974 UTC (bid 75,959, ask 75,960). Fill 75,959, one level.
- *Fees*: entry 0.1125 USDC, exit 0.11245 USDC (0.045% of each fill).
- *Funding*: no settlement between entry and exit, so 0 rows and a complete summary.
- *Result*: gross −0.10199, fees 0.22495, funding 0, **net −0.32694 USDC**.
- *Entry evidence* (`managed-paper-entry-evidence-v2`, digest `1df2e48f…edcb6`, verified after the JSONB
  round trip): ages at entry were opportunity 30.3 s, scorer verdict 30.4 s, 23 feature observations
  (newest 3.8 s), recorded book plus entry book (newest 0.02 s), open interest 82.9 s, 24 funding rows
  (newest 263 s), thesis edition 5 h 16 min. Liquidations kept 500, the cap: the hour held 756, found
  afterwards, and the item now says when it is cut (`353fbdd`). Timeframe measurement was missing:
  `unavailable: ReadTimeout` (not measured within the 3-second bound). Nothing was excluded.
- *Checks passed*: digest, and its verification through the route; every kept record observed and
  received before entry; every source answered before the entry book was read; an update of the entry
  evidence refused by the trigger; both fees; both fills recomputed from the stored books; the funding
  hours, payments and total; net = gross − fees − funding.

**B. Replay on the last six hours of real 1-minute candles.**

- *Entry*: BTC-PERP swing SHORT from opportunity `b2cc3a4f-1d67-4de5-a607-c914a94d8d88` (snapshot
  09:42:49.711), entered 09:43:00. The candle open 76,952 was moved by the cost of the book recorded at
  09:42 (3 significant figures, 6.50 bps) to 76,901.999.
- *Plan*: ATR (14 closed 4h candles) 780.43. Stop 78,462.86, target 73,780.28, trail from 74,560.71.
- *Candles*: 331 evaluated (09:43 to 15:14), no missing minute. No rule fired: the low of 75,600 never
  reached the trail's start or the target, and the stop was never reached. Still open, marked at the
  last close moved by the recorded book.
- *Settled funding*: 6 of 6 hours, 10:00 to 15:00 UTC, each at a rate of 0.00125% and valued at the oracle
  price recorded that minute (76,996.9, 77,044.9, 76,935.0, 76,967.0, 76,636.0, 75,944.9). Payments were
  −0.003129, −0.003131, −0.003126, −0.003128, −0.003114 and −0.003086 USDC (a short receives when the rate
  is positive), totalling −0.018714 USDC.
- *Result*: gross +2.76661, fees 0.22376 (entry 0.1125, exit estimated 0.11126), funding −0.01871,
  **net +2.56157 USDC marked, not closed**.
- *Evidence as of 09:43*: kept the opportunity, scorer verdict, recorded book and open interest.
  Excluded features (23) and the timeframe measurement (2) as observed after entry, and the funding rows
  (24) and thesis edition as received after entry. Liquidations were missing: none were received from
  08:43 to 09:43, confirmed in the table afterwards.
- *Refused*: scalp and intraday on BTC, ETH and SOL, all "Insufficient reward after declared costs".
  Replay costs come from books aggregated to 3 significant figures (6.5 bps a side for BTC, more for the
  others). That is an upper bound, and on it these styles' targets cannot clear the gates at today's
  volatility.
- **Failed check**: "at least two holding styles replayed on real candles"; only swing replayed. The
  search was then widened to every tracked symbol (`c8d5339`) with the criterion unchanged, and the
  final run passed it with all three styles.

Migration 032 DOWN then UP in the isolated schema passed. The rollback check passed: schema gone,
public positions 0 before and after, public entries still paused.

### Interruptions from outside this work

Recorded so the attempts that did not finish are not hidden. None came from this branch: nothing
here was deployed.

- **11:26:56 UTC**: PostgreSQL restarted after backend PID 87870 exited with code 2, and recovered
  at 11:29:37. The first smoke run was setting up its isolated transaction; its connection dropped
  and nothing was committed. The same restart signature is in this container's log on 13 September
  (09:52, 14:19, 15:06 and 15:08 UTC), before this work began. At the time, another service's
  `opportunity_attributions` queries were being cancelled repeatedly. Connection logging is off, so
  the backend cannot be identified and the cause is not established.
- **11:33 and 15:02 UTC**: containers were recreated by deploys of other work: state-api, market-data,
  core-scorer and cockpit-ui at 11:33, then state-api and cockpit-ui at 15:02 (the base branch head was
  `ec48165` by then; the redeployed `managed_paper.py` has no paper risk hooks). The 15:02:35 recreate
  killed the acceptance process running inside the old container (exit 137) at the start of its live phase. PostgreSQL logged
  `unexpected EOF on client connection with an open transaction` for both QA connections at
  15:02:32, which rolled the isolated transaction back.
- After each event: no `qa_%` schema left, public `managed_paper_positions` count 0, public
  `entries_paused` true, and no transaction open for more than a minute.

## What remains

- **Browser QA not run.** `tools/qa_managed_paper_ui.cjs` follows the new routes and fields, but
  Playwright is not installed in this environment, so the populated panel was not exercised in a
  browser at 1366 or 375 CSS pixels. `tsc`, the Vite build and the Cockpit node tests passed.
- **Research trials** keep the frozen `research-trial-v1` specification, whose text names BTC, ETH and
  SOL and "scenario funding". Positions in other markets fall outside those trials' population; a
  new specification version is needed to change that (not done; no trial is registered live).
- **Source comparison** still reads only the Hyperliquid book-history context. The new evidence items
  are captured, not evaluated for contribution.
- **Timeframe measurement** was missing at both live entries (`ReadTimeout` within the 3-second bound;
  only BTC and ETH are kept warm, and BTC's warm-up had just restarted with the service). An entry never
  waits for one.
- **Replay coverage**: on 3-significant-figure book costs, the gates refused scalp on 7 of the 10 markets
  and intraday on 3 at today's volatility. Stop and trailing-stop exits fired on real candles; target,
  time expiry and a gap at a candle's open did not occur in these windows and are proven by the unit
  tests only. The liquidation cap marker was proven by unit tests; neither run's evidence exceeded the
  cap after it was added.
- **Thesis editions** keep no insert time, so their receipt time is the read time; replays exclude them.
- **Candle replays** price costs from books recorded at 3 significant figures (an upper bound); full
  precision books are not recorded historically.
- **Funding** for a settlement with no oracle price recorded within the window stays missing; the
  observer retries for a day after exit, then leaves the hour listed.
- **Restart reconciliation** is not built here. Quote gaps are still latched as observation gaps;
  `advance_on_candle` is available for the risk engine's restart work.
- **Partial fills** are not modelled: an exit the ten displayed levels cannot fill waits for a later
  observation that can.
- Each 15-second observation event still stores the whole book (existing volume, unchanged).
- The portfolio caps (three open, one per symbol) and the 50 USDC planned-risk cap are unchanged;
  account limits and the kill switch belong to the risk engine branch.
- The rules are engineering hypotheses. Nothing here establishes a statistical edge or profitability,
  and no parameter was tuned on results.

## Deploy steps for the lead

Nothing below has been done. Paper only; the public entry pause stays on.

1. **Merge `claude/paper-positions`** (branched from `db27305`) into the dashboard-overhaul branch.
   - `claude/paper-risk` edits the old `services/state-api/app/managed_paper.py`: it imports
     `admit_entry, record_position_event` from `app.paper_risk_hooks`, calls
     `admit_entry(conn, symbol=symbol, plan=plan)` after the pause check, and calls
     `record_position_event(conn, identity, result)` after the lifecycle event in `update`. Keep this
     branch's file and put the first call in `entry_admission` at the marked comment, the second right
     after `await event(...)` in `update`.
   - `update` now also rewrites closed positions when late funding settles (event kind
     `funding_settled`), which changes their net after the close. Either call `record_position_event`
     only when `kind == 'closed'` and book late funding separately, or make the booking idempotent per
     position and have it take the latest net.
   - Migration numbers: the live `schema_migrations` already records `031` (market history under its
     original number) and `033` (horizon_reading_schedule, applied 15 September 11:23 UTC). The runner
     applies every unrecorded version whatever its order, so this branch's `032` applies as pending.
     `claude/paper-risk`'s `031_paper_risk_engine.sql` would be **skipped** as already applied: renumber
     it before deploying. Update `RESERVED_BY_PARALLEL_BRANCHES` in `tests/test_migrations.py` to match.
2. **Test the merged tree**: `.venv\Scripts\python.exe tools\run_tests.py root state-api`, then in
   `services/cockpit-ui` `npm test` and `npm run build`.
3. **Apply migration 032 and replace state-api** (schema-init runs pending migrations before state-api
   starts):

   ```powershell
   docker compose --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml build state-api
   docker compose --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml up -d state-api
   ```

4. **Replace cockpit-ui** from the tested build (low-memory path):

   ```powershell
   docker build -f ops/cockpit-prebuilt.Dockerfile -t tradesync/cockpit-ui:dev services/cockpit-ui
   docker compose --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml up -d --no-deps cockpit-ui
   ```

5. **Read back** (read-only):
   - `SELECT version, applied_at FROM schema_migrations WHERE version = '032'` returns one row;
     `to_regclass('public.managed_paper_funding')` is not null and trigger
     `managed_paper_funding_append_only` exists.
   - `GET /state/paper-positions/rules` shows `managed-paper-lifecycle-v2`;
     `GET /state/paper-positions/candidates` lists the ten-symbol universe;
     `GET /state/paper-positions` shows a current worker tick, `last_error` null and the new note.
   - `GET /state/paper-control` still shows `entries_paused: true`. Resuming entries is an operator
     decision, not part of this deploy.
   - Optionally rerun the acceptance against the merged checkout (isolated schema, rolled back):
     `python tools/run_in_state_api.py tools/qa_managed_paper_positions.py --with tools/qa_paper_live.py --with tools/qa_paper_replay.py -- 10 6`.
6. **Rollback**: redeploy the previous state-api and cockpit-ui images. Migration 032 can stay: the old
   code never reads the table. The new code tolerates the table being absent (funding is listed as
   missing; quotes and exits continue). The public `managed_paper_positions` table is empty, so no
   position state needs converting in either direction.
