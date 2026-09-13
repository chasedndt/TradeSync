# Signal Ledger: the StrikeZone quant lab inside TradeSync, and background loops that actually start

Date: 2026-09-13
Scope: migration `019_strikezone_quant_lab.sql`;
`libs/tradesync_core/tradesync_core/{strikezone_ledger,strikezone_summary,strikezone_scorecards,job_errors}.py`;
`services/state-api/app/{background,strikezone_ingest,strikezone_lab,strikezone_queries,fleet,editions,event_outlook,main}.py`;
`tools/{strikezone_quant_bridge,hermes_fleet_bridge}.py`; Cockpit `pages/SignalLedger` with
`components/ledger/*`, Sidebar, Mission Control readiness chip, fleet job errors;
`ops/compose.market-command.yml` (charts mount).

## The background loops never ran

The Hermes heartbeat, the event-reaction refresher and the edition scheduler
were registered with `@app.on_event("startup")`. The state API is built with
a lifespan handler, and FastAPI ignores startup-event hooks when one is
given, silently. So the Hermes link sat at "checking", event reactions were
never computed and no scheduled edition was built, while the gateway
answered in a third of a second.

Fix: `app/background.py` keeps a registry of named loops. Modules register
their loop there; the lifespan starts every registered loop once the pool
exists and cancels them on shutdown. A loop that raises is contained and
logged by exception type. `STATE_API_BACKGROUND_LOOPS=false` keeps them off.
A test fails if any module under `app/` uses a startup-event hook again.

Verified live after redeploy: the startup log lists
`hermes_link, event_outlook, thesis_editions`, and `/state/hermes/status`
reads `live` on port 8642, version 0.21.0, last answer seconds ago.

## Signal Ledger

The operator asked for the Discord control plane's quant systems inside
TradeSync, the signal-ledger forward test first. The lab runs in the Hermes
fleet in WSL and writes plain files under
`runtime/strikezone/quant_eval`: an append-only signal ledger (every
closed-candle call on BTC, ETH and SOL at 15m, 30m and 1h, including no-trade
calls), an append-only outcome ledger (fills, fees, slippage, funding, net
P&L), daily scorecards with regime cohorts, an integrity health report, the
methodology state and cost assumptions. The fleet inspector keeps its own
state file.

**Bridge.** `tools/strikezone_quant_bridge.py` runs on the Windows host
(pythonw, Task Scheduler, every five minutes) because Docker Desktop cannot
mount the distro. It posts the ledger lines appended since the byte offset it
last stored, posts each document when its modification time changes (the
scorecards without superseded methodologies, the fleet state without Discord
receipts), and copies the charts of the newest trade calls and outcomes to a
host folder mounted read-only into the state API. Storage is idempotent and a
cursor advances only after the rows were stored. It never writes to the lab,
never posts to Discord and never runs a job.

**Normalisation lives in one place.** The bridge sends raw lines;
`tradesync_core.strikezone_ledger` turns them into rows. Neither lab record
carries a status, so it is derived: a trade call is resolved when an outcome
names it, open until it expires, resolving during the hour the resolver needs,
and overdue after that. Numbers arrive as decimal strings and are parsed
without accepting booleans or non-finite values.

**Routes.** `POST /state/strikezone/ingest` (bridge only),
`GET /state/strikezone/forward-test` (matrix, totals, equity),
`GET /state/strikezone/ledger` (filters: asset, timeframe, view),
`GET /state/strikezone/scorecards`, `GET /state/strikezone/health`, and
`GET /state/strikezone/charts/{signals|outcomes}/{name}.png`, which serves
only names matching the lab's id shapes. Every read is scoped to the active
methodology.

**Page.** Signal ledger in the sidebar:

- a header with the last call's age, the integrity state, failing jobs,
  calls, trades and resolved, open and overdue;
- the forward-test matrix: each asset by timeframe with its latest call, age
  (stale after two missed runs), last trade with levels and status, calls and
  trades in 24 hours, open trades and the last week's results;
- paper equity: cumulative net P&L after costs, win rate, maximum drawdown;
- the ledger itself, filterable, each row opening fills, costs, regime and
  the charts at the call and at the exit;
- strategy scorecards with the lab's sample floors, each row opening results
  by side, session and regime, exits and costs, and independence against the
  floors; regime cohorts below, thin cohorts dimmed;
- lab health: the integrity issues in plain words, every lab job with the
  reason it failed, and the fleet inspector's standing issues.

Mission Control's readiness line gains a Forward test chip.

## Why a job failed, in words

`fleet_jobs` now stores each job's last error and last delivery error,
redacted on the host by `tradesync_core.job_errors.redact` (token, key,
webhook and private-key shapes) and cut to 1,500 characters.
`diagnose` names recognisable causes: Windows line endings in a shell script,
a DNS failure inside WSL, the integrity watchdog's deliberate hold, a Python
exception (or a traceback cut off before it), and a script that reported ok
but exited non-zero. The Fleet page shows the raw error under each job.

## Verified after deploy

The first bridge pass stored the whole lab in about a minute: 12,977 calls,
644 outcomes, the five documents and 60 charts. Read back through the routes:

| Measure (methodology v1_3) | Value |
|---|---|
| Calls / trade calls / resolved | 11,129 / 595 / 595 |
| Net paper P&L after costs | −$867.45 |
| Win rate | 33.1% |
| Maximum drawdown | $876.54 |
| Scorecards / regime cohorts | 9 / 47 |

A chart route returned a 127 kB PNG. The bridge is registered as
`TradeSync-StrikeZone-Quant-Bridge` (pythonw, hidden, every five minutes) and
copies up to 60 charts a pass until the newest 200 of each kind are local.

## What the lab showed

These are fleet-side faults, reported here and not changed by TradeSync:

- the StrikeZone health watchdog and the unified paper-approval bridge fail
  because their scripts have Windows (CRLF) line endings, as do other
  StrikeZone scripts;
- the quant integrity watchdog held on three issues at 14:02 UTC (stale
  ledger, incomplete matrix, stale funding archive); by 15:36 UTC only the
  stale funding archive remained;
- two lab jobs last ended "interrupted by shutdown before terminal completion";
- Discord delivery failed with DNS lookups failing inside WSL;
- the fleet inspector's standing issues (31, then 25) have kept the same
  fingerprint since 2026-07-27;
- the 3.5-day and weekly self-review jobs write into `chaseos_obsidian`,
  which is not the canonical vault.

## Tests

Root: `test_strikezone_ledger.py`, `test_strikezone_summary.py` (matrix with
missing and stale pairs, equity drawdown and downsampling, health wording,
scorecards and cohorts), `test_job_errors.py` (redaction and each diagnosis).
State API: `test_background.py`, `test_strikezone_lab.py` (ingest
normalisation, unknown documents refused, charts by exact name only, ledger
status, reward to risk and chart links).
