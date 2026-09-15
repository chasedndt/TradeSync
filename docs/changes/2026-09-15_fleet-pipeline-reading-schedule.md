# 2026-09-15 — Fleet run progress and output, feed heartbeats, an opt-in reading schedule, heatmap coverage

Branch `claude/ops-refinements` from `db27305`. Paper-only: no execution flag, gate, signer or wallet changed.
No Hermes job changed and no directive sent. **Implemented and tested locally; not deployed; migration 033 not
applied.** Live numbers below were read from the running stack without writing to it.

## 1. Fleet page: run progress and output

- `GET /state/fleet/activity` (state-api `fleet_activity.py`, shaping in `fleet_activity_view.py`): per job, runs
  the ledger has claimed or started and not finished, with elapsed time, flagged when the newest run snapshot no
  longer carries them; the last five runs with status, duration and error; the latest model call (silent or
  delivered, target, error); the latest stored output with its time, file time, fleet-host stamp, size, lines,
  delivery target, intake verdict and first lines; later runs that left no stored output; and the age of the run
  snapshot, job snapshot, newest model call and newest stored output.
- `GET /state/fleet/jobs/{job_id}/outputs` and `GET /state/fleet/outputs/{id}`: a job's recent stored outputs and
  one output's full text.
- Cockpit: a running marker with elapsed time in the job row; the expanded row shows running now, last runs and
  latest output; a drawer reads the full text and switches between recent outputs; the header shows snapshot ages.
  Directive controls unchanged.
- **Finding:** the output bridge stores Hermes output text unredacted (`tools/hermes_output_bridge.py` and
  `tradesync_core.hermes_output` do not call `redact`), and the fleet bridge does not redact run errors from the
  execution ledger either; the Knowledge Intake page shows raw payloads. The new routes serve text and errors with
  token-, key- and webhook-shaped strings masked (`job_errors.redact` gains `limit=None`) and state how many;
  nothing is added. Redacting in the bridge itself is left for a decision.
- Finding each job's newest output by scanning stored payloads took 0.41 s for 770 outputs and grows daily, so an
  in-memory index reads the last eight days once and then only newly received rows (a 15-minute read took 3.8 ms).

Live, read-only (Postgres, 11:09 UTC): run snapshot 11:06:59 (2 min 9 s old), job snapshot 11:06:55, newest model
call 10:18:23, newest stored output 11:01:56. Nothing running at 11:09; two runs had no finish time at 00:50. The
last-five-runs query returns 249 rows for 71 jobs. The index's first read covers 850 outputs from 59 of 85 jobs
(74 enabled), 15 refused at intake. Latest model call: 29 jobs, 17 silent, 12 delivered, 0 errors. Stored outputs
with webhook-, prefixed-key-, 64-hex- or labelled-secret-shaped text: 0.

## 2. Integration pipeline: feed heartbeats

- `tradesync_core.feed_heartbeat`: state, since when, last message, last success, counts over the last hour in
  one-minute buckets, attempts and reconnects, last error as its type and HTTP status, and what the data is for.
- market-data `GET /feeds/status`: the l2Book depth websockets at 2 and 3 significant figures, the Binance USD-M and
  Bybit liquidation streams, the Binance open-interest history fetch, the Hyperliquid funding-history route (moved
  unchanged into `funding_history_route.py` first) and the liquidity context loop.
- state-api adds `market_recorder` (passes, rows) and the Timeframes warm loop (moved unchanged into
  `horizons_warm.py` first), and `GET /state/integration-pipeline` gains a `feeds` section collected beside the
  stage probes. When market-data does not answer, its feeds are left out with the reason. Heartbeats change no
  node status and no Tier A readiness.
- Cockpit: a Feed heartbeats section (component moved out of `Pipeline.tsx` first) with state, last delivery and
  age at the read, last-hour counts, reconnects, last error and a "context only · no scoring influence" marker.
  Every feed is marked: the feature catalog has every liquidity feature `scoring_eligible: false`, and funding
  history feeds only the Timeframes records.

Live, read-only (11:09 UTC, existing routes; heartbeats not deployed, `/feeds/status` answers 404): books at 2 and
3 significant figures 2.0 s old, not stale; Bybit connected, 6 liquidations in the last hour; Binance connected, 23
of 29 merged liquidations; Binance open interest 500 hourly rows, newest 11:00; funding history 48 rows for 48
hours, newest 11:00. Recorder, last hour: 1,128 book rows, 413 open-interest rows, 81 liquidations; newest book row
11:08. BTC Timeframes measured 11:06:41 (short) and 10:42:35 (daily).

## 3. Timeframes: Hermes readings on a schedule, off by default

- Migration `033_horizon_reading_schedule.sql`: `horizon_reading_schedules` (market, band, enabled, daily time in
  UTC, who changed it and when, last slot and result) and `horizon_reading_schedule_audit` (who, when, previous
  value, new value). It creates no schedule.
- `GET`/`PUT /state/market/horizons/reading-schedule` (`reading_schedule.py`, rules and store in their own
  modules); the change and its audit row are written in one transaction.
- The `horizon_reading_schedule` loop checks once a minute, claims a due slot only while the schedule is still
  enabled and unchanged (a restart never starts a slot twice), starts the reading through
  `horizon_reading.start`, and records a skip with its reason: a reading of the current measurement exists, one is
  running, nothing is measured, or the gateway is not configured. A schedule acts from the first slot after it was
  changed; a slot missed by more than 30 minutes is recorded as missed, not started late.
- Cockpit: beside each band's reading, the next scheduled reading or "Schedule off", the last slot's result, the
  last change with who, when and what it replaced, and an editor that asks for confirmation.
- Migration verified on a throwaway local PostgreSQL 17.10 cluster (data in the session scratch directory on E:):
  UP, a schedule and audit row, an unknown band refused, `enabled` defaulting to false, UP again, DOWN (no tables
  left), UP after DOWN.
- `tests/test_migrations.py` reserves 032 for a parallel branch, like 031. The lead may renumber 033 at merge.

Live: BTC had no Hermes reading in any band at 11:06 UTC.

## 4. Heatmap coverage

- Retention keeps books every minute for 3 days and every fifteenth minute to 90 days; the 7-day and 30-day windows
  use the 2-significant-figure book in two-hour and eight-hour buckets. A new root test records a book a minute,
  applies retention, and confirms every bucket holds at least 8 (two-hour) or 32 (eight-hour) books once history
  covers the window, and that before then a window fills from the bucket where recording began.
- The panel said only "Recording since … Longer windows fill in as history builds." It now states "Recorded books
  since … · N of M two-hour buckets filled in this window."
- Live (BTC, 11:09 UTC): books since 14 September 11:38 UTC; 7 days, 12 of 84 buckets filled (16 to 120 books each);
  30 days, 4 of 90 (62 to 383); 892 books. 14 September 13:00 to 17:00 UTC recorded nothing, which leaves one empty
  two-hour bucket. At the current recording rate the 7-day window is full from 21 September and the 30-day window
  from 14 October.

## Verification

- `tools/run_tests.py root state-api market-data`: root 811 passed, 17 deselected, 2 warnings, 49 subtests passed;
  state-api 305 passed; market-data 148 passed.
- Cockpit `npm test`: 73 passed, 0 failed. `npm run build`: passed in 28.8 s, with the existing chunk-size warning
  and a Rollup annotation warning from `node_modules/ox`.
- Not done: browser checks of the new sections, which need a deploy. `services/market-data/app/main.py` (1,133
  lines) and `services/state-api/app/main.py` (3,384 lines) remain over 300 lines: only registration lines were
  added, plus the pipeline handler collecting feeds beside the probes.

## Deploy

1. Apply migration 033.
2. Rebuild `market-data`, `state-api` and `cockpit-ui` in the bounded profile.
3. Check: state-api's startup log lists `horizons_warm` and `horizon_reading_schedule`; market-data `/feeds/status`
   lists seven feeds with both l2Book streams connected; `/state/integration-pipeline` carries nine feeds with
   market-data reported ok; `/state/fleet/activity` answers (its first call reads eight days of outputs);
   `/state/market/horizons/reading-schedule?symbol=BTC-PERP` shows all four bands off; the heatmap panel states its
   buckets filled. Heartbeat counts start from zero at the restart.
