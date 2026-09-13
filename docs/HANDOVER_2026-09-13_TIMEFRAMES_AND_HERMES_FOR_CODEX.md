# Handover for Codex, 2026-09-13 (evening): Timeframes, feature charts, Hermes fleet repairs

Written by Claude because the operator's weekly usage limit is nearly spent.
Codex continues from here. **The operator considers Codex the stronger model
and asks Codex to review everything below critically and improve it**, not just
finish it: check the statistics for honesty, the code for correctness, and the
UI against the operator's standards (section 7). Verify every claim here
yourself; where this document says "verified", it names the evidence.

Branch: `codex/2026-09-01-dashboard-overhaul`. Last pushed commits before this
handover: `113f8e8`, `a8714b8`, `d2e5b9b`. This handover is committed together
with the work in progress (section 3).

---

## 1. Rules that are not negotiable

- **Paper only.** `DRY_RUN=true`, `EXECUTION_ENABLED=false`. No keys, signer,
  wallet, orders or live execution. Hyperliquid is TradeSync's only venue.
- **ChaseOS canonical vault** is `C:\Users\chaseos\Documents\chaseos_chaseintech`.
  `chaseos_obsidian` is a stub and must never be used for anything canonical.
- **Secrets are never displayed or logged**: FRED key, Discord token, Hermes
  `API_SERVER_KEY` (TradeSync env `AGENT_HARNESS_KEY`), TradingView webhook secret,
  Cloudflare credentials. Copy file to file only; never open `.env` files to read them.
- **Commits carry no AI attribution**: no `Co-Authored-By`, no "Generated with"
  footer, in any repository. Commits are authored by the operator only.
- **Never hand-edit Hermes `cron/jobs.json`.** Change jobs through TradeSync:
  `POST /state/fleet/directives` (applied through the Hermes gateway's jobs API,
  falling back to the host bridge). See section 4A.
- **Host scheduled tasks use `pythonw.exe`** with log files under
  `E:\Projects\TradeSync\dashboard-runtime\logs` (python.exe popped console windows).
- **WSL shell commands fail from these shells** (`Wsl/Service/E_UNEXPECTED`). Read
  Hermes files over `//wsl.localhost/Ubuntu/home/chaseos/runtimes/hermes-home`
  (forward slashes in Python), and drive jobs through the gateway API on port 8642.
- **Never invite another Discord bot**; the existing Hermes bot is in every guild.
- **File structure**: one responsibility per file, split past ~300 lines (~200
  for components), CSS modules per component, one source of truth per fact.
- **Statistics are records, not forecasts.** No feature carries a weight without
  measured, held-out skill. Say when a sample is too thin.

## 2. How to run, test and deploy

```powershell
# bounded stack (from the repo root)
docker compose --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
  -f ops\compose.full.yml -f ops\compose.market-command.yml `
  up -d --build --no-deps state-api cockpit-ui
# apply a new migration first: up -d --no-deps schema-init  (then wait for it to exit)
```

- Tests: `.venv\Scripts\python.exe tools\run_tests.py` (all suites, each in its own
  process) or `tools\run_tests.py state-api`. Root tests that import
  `tradesync_core` directly need `PYTHONPATH=libs/tradesync_core` when run with plain pytest.
- Cockpit: `cd services\cockpit-ui; npm run build` (runs `tsc` then Vite).
- Ports: state-api 8000, cockpit 3000 (proxies `/api` to state-api), market-data
  8005 on the host (`MARKET_DATA_URL` inside compose), core-scorer 8001, Hermes
  gateway `127.0.0.1:8642` (containers use `http://host.docker.internal:8642`).
- Host tasks (Task Scheduler, all pythonw): `TradeSync-Hermes-Output-Bridge` (2 min),
  `TradeSync-Hermes-Fleet-Bridge` (5 min), `TradeSync-Thesis-Edition-Renderer` (10 min),
  `TradeSync-StrikeZone-Quant-Bridge` (5 min).

## 3. State at handover

| Item | State |
|---|---|
| Migration `020_hermes_jobs_api.sql` | applied (schema-init log: "Applied migrations: 020") |
| state-api with gateway job control | deployed and healthy; `GET /state/fleet/jobs` reports `control.gateway_api: true`, status `live`; a `run_now` directive returned `applied` via channel `api` |
| state-api with the timeframe routes | redeployed and live: `GET /state/market/horizons?symbol=BTC-PERP` measured 2,217 daily candles (2020-08-19 to 2026-09-13) across all six horizons; a cold request took 55 s (see 6.2) |
| cockpit with the Timeframes page | `npm run build` passed; a redeploy was started at handover time: **open `/timeframes` and check it in the browser** |
| Mission Control events panel | operator reported the reaction button overflowing and an opened reaction that could not be closed. Fixed in `components/EventRow.tsx` (two-line rows, whole-row toggle, Hide control, Escape, table scrolls inside the panel); **check it in the browser** |
| Core horizon engine + features | written; `tests/test_horizon_outlook.py` and `tests/test_horizon_features.py`: 15 passed |
| state-api gateway directives | written; state-api suite 107 passed including `test_fleet_gateway_directives.py` |
| state-api horizon routes | written; `tests/test_horizons.py` **not yet run** |
| Cockpit Timeframes page and fleet controls | written; fleet controls built once (`npm run build` passed); **Timeframes files not yet built** |
| Hermes line endings | restored and verified (see 4A) |
| Hermes targeted script fixes | applied and syntax-checked; the first live runs after the repair passed (see 4A) |

First actions for Codex: run `tools\run_tests.py`, run `npm run build`, redeploy
state-api and cockpit, open `http://localhost:3000/timeframes` and `/fleet`.

---

## 4. What the operator asked for, and where each part stands

### 4A. Fix the failing Hermes scripts and wire the jobs into Market Command

Operator: fix the failures seen in the Hermes scripts "as you wire them all now to
the new market command interface", noting that Hermes "launches on a port", which
is the safe way to integrate (rather than building a separate application).

**Found (survey of `/state/fleet/jobs` last errors, `cron/output`, executions.db):**

- **Five jobs broke on Windows CRLF line endings, caused by TradeSync.**
  `tools/repoint_hermes_vault.py` (the 2026-09-13 04:37 vault re-point) used
  `Path.write_text`, which on Windows writes `\r\n`. Evidence: for each of the five
  entry scripts, the original in
  `E:\Projects\TradeSync\dashboard-runtime\backups\repoint-20260913_043749\scripts.zip`
  had zero CRLF and named the old vault; the live file had CRLF on every line.
  Jobs: `6a1fdf7894c7` StrikeZone health watchdog, `25cae0290b3d` unified
  paper-approval bridge, `6cc8ce77dfe8` market revalidation 19:00, `e6d0e5d87336`
  private director thesis run, `cd7d95dd50ca` Step 6B key-levels cycle (its `.py` is
  run by shebang).
- `9b8976a0804e` scheduled market edition: the market model build hit a read
  timeout on a third-party spot exchange's public API (named in the script),
  the cycle continued with an empty model and crashed with `KeyError: 'BTC'`.
  That API answers normally from this machine, so it was a transient WSL network fault.
- `c7b1fa0a2f3f` approval publish watcher: probe subprocess killed at 30 s.
- `109d391ae292` compute analytics: Discord fetch-back read timeout at 30 s.
- `83d45255c926` quant integrity watchdog held on `funding_archive_stale`: the
  funding archive only moved when outcomes resolved; nothing scheduled the lab's
  existing `funding-sync` mode.

**Done (verified):**

1. `tools/restore_hermes_line_endings.py` restored LF in 121 files the re-point had
   converted (including `config.yaml` and the Discord bindings file) and normalised
   2 other CRLF scripts. Backup:
   `E:\Projects\TradeSync\dashboard-runtime\backups\line-endings-20260913_195605`.
   Rule: restore where the backed-up original was LF and named the old vault;
   normalise any `.sh`, `.bash`, `.py` or shebang file; nothing else changes.
2. `tools/repoint_hermes_vault.py` now reads and writes bytes, so it cannot recur.
3. `tools/hermes_fleet_fixes.py` applied four exact, idempotent replacements
   (backup `...\backups\fleet-fixes-20260913_200253`):
   - edition orchestrator: retry the model build twice (30 s, 60 s), then raise
     `RuntimeError("fresh market model unavailable after 3 attempts: …")` instead
     of rendering an empty model;
   - approval watcher: probe timeout 120 s, `TimeoutExpired` prints a clear line and exits 1;
   - compute analytics: post waits 90 s (not retried, to avoid double posts);
     fetch-back retried twice;
   - `cron_paper_outcomes.sh`: runs `cron_runner funding-sync` (non-fatal) before `outcomes`.
4. Checks: the four Python files compile; `bash -n` passes on the five shell
   scripts; zero carriage returns remain in them.

**Done in code (tests pass; deploy and live check pending):** Market Command drives
jobs through the Hermes gateway's jobs API on its port.

- Hermes 0.21.0 serves, behind the same Bearer key: `GET /api/jobs?include_disabled=true`,
  `GET/PATCH/DELETE /api/jobs/{id}` (PATCH whitelist: name, schedule, prompt,
  deliver, skills, skill, repeat, enabled; schedule as a string such as
  `every 30m` or `0 8 * * *`), `POST /api/jobs/{id}/pause|resume|run`. Source:
  `hermes-agent/gateway/platforms/api_server.py` lines 3250-3440;
  docs `website/docs/user-guide/features/api-server.md` "Jobs API". No route
  reads job outputs (the output bridge still does). `script`, `workdir` and
  `no_agent` are not patchable.
- `services/state-api/app/hermes_jobs.py`: transport (job id `^[a-f0-9]{12}$`).
- `services/state-api/app/fleet.py`: `POST /state/fleet/directives` now applies
  `set_schedule`, `set_enabled`, `set_deliver`, `pause`, `resume`, `run_now`
  through the gateway at once (`status=applied`, `channel=api`, `previous` values
  recorded, read model row refreshed from the gateway's answer). If the gateway
  fails, schedule and enabled fall back to the host bridge (`pending`,
  `channel=bridge`); pause, resume, run now and delivery return an error.
  `set_workdir` is bridge-only. `GET /state/fleet/jobs` adds `control` and
  `restorable_deliver` (the Discord target a job had before a switch to local).
- Migration 020 widens the `fleet_directives.kind` check and adds `channel`.
- Cockpit `pages/FleetJobControls.tsx` (used by the Fleet page and the Hermes
  panel on Agents): schedule, enable, pause or resume, run now (confirms, and warns
  when the job delivers to Discord), "TradeSync only" delivery switch and "restore
  Discord" (both confirm). The Fleet page shows gateway status and each
  directive's channel and detail.
- **Delivery of no job was changed.** Switching jobs from Discord to TradeSync is
  the operator's decision; member-facing StrikeZone publishing must not be switched
  without them.

**Verified live after the repair** (read from the gateway's `GET /api/jobs/{id}`,
all with `failure_streak` 0 and no last error):

| Job | Last run (BST) | Status |
|---|---|---|
| `6a1fdf7894c7` StrikeZone health watchdog | 20:14 | ok |
| `25cae0290b3d` unified paper-approval bridge | 20:14 | ok |
| `09490ac9c6d7` paper-outcome resolver | 20:10 | ok |
| `c7b1fa0a2f3f` approval publish watcher | 20:02 | ok |
| `83d45255c926` quant integrity watchdog | 19:53 | ok |

A `run_now` directive for `6a1fdf7894c7` was also applied through the gateway
(channel `api`).

**Still to do for 4A:**

1. Watch the first scheduled runs of the repaired jobs that have not run since:
   `6cc8ce77dfe8` 19:00, `e6d0e5d87336` 07:30, `109d391ae292` 07:50,
   `9b8976a0804e` 08:00, `cd7d95dd50ca` every 720 m. Do not run publishing jobs by hand.
3. Not fixed, with causes:
   - `95a0edd1754d` weekly member recap: last error names a missing
     `step8b3_result.json` under the old vault path; code is already re-pointed.
     Check the input exists under chaseos_chaseintech before Monday 10:00.
   - `91a09ee8f1c2` and `a63c9cff6ac2` self-reviews: `self_upgrade_executor.py`
     reports `BLOCKED_TEST_FAILURE` (its pytest run fails) and the wrapper stops
     under `set -e`. The CRLF restore may fix the tests; find the failing test if not.
   - `88f6827ea0f4` closeout smoke: needs a Hermes closeout note newer than 14 days
     (a governance artifact; operator decision, do not fabricate).
   - `0c42e5b6b468` graph hygiene: 3600 s script timeout, most likely because the
     fleet now works on the 27k-note canonical vault. Split or raise the timeout.
   - `32fc6f83e99f` publication audit: CDP browser profile `strikezone_tv_cron:9223`
     unhealthy (external browser).
   - "Interrupted by shutdown" rows are fire-claim loss, written by
     `cron/scheduler.py` `_record_fire_ownership_lost` (about lines 2564-2575),
     not gateway restarts. Investigate.
   - Discord and network flakiness inside WSL (DNS, SSL, disconnects) for
     `b15628ea589e`, `8b0657e841d8`, `f65af536b8ea`.

### 4B. Timeframes page (multi-horizon outlook)

Operator: a page with higher, medium and lower time frames: BTC over the next
six months, three months, one month, two weeks, one week and three days; a
readable overview; the features used to say what to expect at each horizon,
algorithmically or with the LLM; and in rich text, links that take you to the graph.

**Why it is built this way:** every existing catalog feature is intraday
(snapshot or at most 4 h; Redis keeps 7 days; skill measured only at 15/60/240
minutes; no feature has earned skill). So the horizon features are computed from
Hyperliquid **daily candles** (venue backfill from 2020-08-19, real volume from
2023-02-26) and nothing is weighted.

**Engine (`libs/tradesync_core/tradesync_core/`, tested):**

- `horizon_stats.py`: forward returns, quantiles, independent (non-overlapping)
  windows, summaries (share up, median, median absolute move, 10/25/75/90th
  percentiles), moving averages, rolling max/min, daily volatility.
- `horizon_outlook.py`: horizons `3d`, `1w` (lower, 20-day average), `2w`, `1m`
  (medium, 50-day), `3m`, `6m` (higher, 200-day). Per horizon: trend state (close
  above or below the average, average rising or falling), momentum over the
  horizon's length, the record for days in the same trend and momentum state
  (then trend alone, when too thin), lean up at a share of 0.6 or more, down at
  0.4 or less, mixed between, `too_few` below 8 independent windows; implied
  one-sigma range; flip level; recent high and low; band agreement.
- `horizon_features/` (one module per feature, registry in `__init__.py`): trend,
  momentum (move in units of an ordinary move), volatility (realised, ranked in the
  past year), range position (lookback 20 days to 2 years by horizon), drawdown
  (from the one-year high), RSI (14 daily bars; about 14 weekly bars for 3 and
  6 months), participation (volume, real-trading days only). Each gives `states`
  (per day), `read` (today), `overlays` (chart data).
- `horizon_evaluation.py`: per horizon, each feature's reading plus the record
  for days in the same state, and a sentence tallying which records lean higher,
  lower, mixed or too thin.
- `horizon_chart.py`: a candle window per horizon, every feature's overlays, and
  the record's cone (10/25/50/75/90th percentiles of past moves from the same
  state, spread by the square root of time from the last close).

**state-api:**

- `app/horizons.py`: `GET /state/market/horizons?symbol=`, `GET
  /state/market/horizons/chart?symbol=&horizon=`, `POST
  /state/market/horizons/reading?symbol=`. Daily candles fetched from market-data
  in 900-day chunks (its limit is 1000 per request), cached per symbol for an hour,
  measured in a worker thread; BTC and ETH warmed by a background loop.
- `app/horizon_reading.py`: Hermes writes a four-paragraph prose reading from the
  measured facts through `/state/agents/harness/ask` (intent `summarise`), as a
  background job the page polls (the cockpit proxy cuts requests at 90 s). Prose
  only: the harness boundary refuses answers carrying `direction`, `score` and
  similar fields.
- Registered in `app/main.py` after the StrikeZone lab.

**Cockpit:** `api/horizonTypes.ts`, `api/hooks/useHorizons.ts`,
`components/horizons/` (HorizonBands, HorizonCard, FeatureCard, FeatureChart,
LinkedText, ReadingPanel, horizonText), `pages/Timeframes.tsx` at `/timeframes`
(sidebar "Timeframes"). Feature names in horizon cards, the tally sentence and
Hermes's prose are links (`LinkedText`) that switch to the right horizon, scroll
to `#feature-<key>` and flash the card. `FeatureChart` uses lightweight-charts
4.2 (no panes): candles plus price-pane overlays and cone lines on one chart;
RSI and volume in a second chart kept in step by visible time range.

**Still to do for 4B:** run `tests/test_horizons.py`, build, deploy, open the page
for BTC and ETH at 1366x768 and 375 px, check every chart draws, that links scroll,
and that the Hermes reading completes. Then improve (section 6).

### 4C. A chart for every feature on the market features page

Operator: on the market features page, a graph for every feature showing what
the feature expects, drawn differently per feature, clickable from rich text.

The operator's "market features page" is **Regime Lab** (`/regime-lab`,
`pages/RegimeLab.tsx`), whose Feature evidence table shows numbers only.
**Not started.** Suggested build:

- state-api has no feature-history route. Add a proxy to market-data
  `GET /feature-histories/{venue}/{symbol}?feature_ids=&window=1h|4h|24h|7d&points=`
  (see `services/market-data/app/main.py` around line 783).
- One chart per catalog feature (`config/features/market-feature-catalog-v1.json`,
  21 features): the feature series against price (1 h candles over the same 7 days),
  the normalisation centre and dispersion as a band, and the current score and
  direction marked at the right edge. Style by `signal_kind` and `score_mode`:
  directional as a line around zero; liquidity suitability as a line with a band;
  positioning (funding, open interest, premium) as a histogram coloured by sign.
- Expand a row to show its chart; give each an anchor so thesis text can link to it.
- Constraints: Redis keeps 7 days; the four liquidity features are often
  "unavailable" (median absolute deviation zero); lightweight-charts 4.2 has no panes.
- The Timeframes feature charts (4B) are the daily-horizon counterpart and can
  share components.

### 4D. Earlier requests still open

- StrikeZone quant lab is in TradeSync (Signal ledger page). Member-facing
  publishing still goes to Discord by design.
- The operator praised the combined thesis judgement (breadth across markets);
  keep it.

## 5. Known defects to fix

- Hermes briefing shows mojibake (`â€™`) and `BriefingCard` collapses paragraphs
  into one `<p>`.
- `GET /state/market/context` funding history returns the **oldest** 500 hours of
  the window (Hyperliquid caps a call at 500 rows): paginate newest-first; the
  premium field is dropped.
- market-data candles: `limit=1000` returns 1001; no `1w` interval; state-api
  `/state/market/candles` ignores `start_ms`/`end_ms`; nothing stores candles, and
  Hyperliquid serves only about 5,000 candles per interval (1 h is about 208 days).
- Screenshots in the in-app browser time out when the window is not drawing; use
  page text for checks.

## 6. What to review and improve (Codex, please)

1. **Statistics.** Confirm there is no look-ahead in any state (each day uses data
   up to that day only). Check that using the pre-2023 backfill in records is
   acceptable, or split records by era. Consider block-bootstrap confidence
   intervals for the share up and median, as the skill gate does
   (`tradesync_core/edge_evidence.py`), and hold-out checks before any lean is
   shown as meaningful. Six-month records have about 12 independent windows at
   most: make that impossible to miss.
2. **Performance.** Volatility ranking and momentum loop over lookbacks per day
   (roughly n × 365 per horizon). Vectorise or cache; measure how long a cold
   `/state/market/horizons` takes for BTC.
3. **UI.** Hold it to section 7. Check the Timeframes page reads as an overview
   first, and that charts are legible on a laptop and a phone.
4. **Hermes wiring.** Consider surfacing each job's live state from `GET /api/jobs`
   on the Fleet page instead of the five-minute bridge snapshot.
5. **Tests.** Add browser-level checks for the Timeframes links and fleet controls.

## 7. Operator standards (from repeated reviews)

- Mission Control fits one screen; a thin readiness line; Market Thesis above Market
  Pulse; inline charts per market row; collapsible panels; no generic chrome.
- Trader-grade content: overall direction, BTC and ETH reads, economic events with
  measured reactions and how to manage risk, links to sources.
- Real statuses only (Hermes by port and seconds since seen). Rich formatting,
  never text dumps. Verify in the browser at 1366x768 and 375 px.

## 8. Change records to read

`docs/changes/2026-09-13_signal-ledger-and-lab-health.md`,
`docs/changes/2026-09-13_market-thesis-outlook-hermes-link-and-layout.md`, and
`docs/MARKET_COMMAND_PLAN_2026-09-11.md` (progress section).
