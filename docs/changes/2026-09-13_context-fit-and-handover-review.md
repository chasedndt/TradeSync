# Context card fit and handover continuation — 13 September 2026

## Repo-truth delta

The evening timeframe/Hermes handover was read against the running workstation.
The checkout started clean at `f6ea9d8`; a fetch found no newer remote content.
E: had approximately 318 GiB free. Another worker subsequently changed and
committed timeframe calculations in the shared checkout. Those changes are not
attributed to this slice and were not reverted.

## Changes owned by this slice

- ContextPanel gets scoped, panel-width-driven columns. Provider descriptions
  sit below their names; values and labels can wrap without clipping. No feed
  is removed to make the card fit.
- RSI defines an entirely flat price series as neutral (50), not overbought
  (100). Long-horizon RSI is explicitly 98 daily bars, not 14 weekly candles.
- New prefix-invariance tests exercise all seven feature states at all six
  horizons: adding future bars must not change historical states.
- `tools/qa_context_timeframes.cjs` checks context bounds at 1366, 1024, 768
  and 375 px, plus ETH feature-link scrolling and page overflow at 1366/375 px.

## Boundaries untouched

No credentials, wallet authority, execution configuration, Discord delivery,
job schedules, publishing runs, canonical vault content or Cloudflare settings
were changed. Backend RSI edits are source/test changes until a coordinated
State API deployment; do not restart the concurrently edited backend blindly.

## Tests and verification

- `.venv/Scripts/python.exe tools/run_tests.py`: root 615, state-api 117,
  market-data 119, executor 3 and signer 10 passed (864 total); 17 root tests
  deselected, integration suites not requested. This is a point-in-time result
  while another worker continued editing, not certification of later changes.
- `PYTHONPATH=libs/tradesync_core .venv/Scripts/python.exe -m pytest
  tests/test_horizon_causality.py tests/test_horizon_features.py -q`: 15 passed.
- `npm run build`: passed. Existing bundle-size, Browserslist-age and Rollup
  annotation warnings remain; no dependency upgrade performed.
- Expanded horizon regression (causality, features, outlook and rolling):
  27 passed in 7.02 s.
- Live browser acceptance passed on port 3000: populated context values and
  descriptions fit at 1366/1024/768/375 px. ETH feature links changed to 3 days,
  scrolled to the Trend card and displayed a drawn chart at 1366/375 px; no
  page overflow or uncaught browser errors. Screenshots were visually inspected.
  Evidence: `E:/Visual QA/TradeSync Visual QA/Current Reviews/2026-09-13-context-timeframes/live/acceptance.json`
  and the adjacent six PNGs. An initial attempt raced container recreation and
  received connection refused; the rerun above passed after startup.

## Live Fleet review

The jobs endpoint reported `control.gateway_api=true`, gateway status `live`.
The bridge snapshot was 22:12:05 BST. The health watchdog's 22:04 run was `ok`.
The five other repaired jobs still showed pre-repair errors: their next runs
were 23:16 tonight and 07:30, 07:50, 08:00 and 19:00 tomorrow. These are not
new repair failures, nor verified recoveries. Weekly recap remains due Monday
10:00; check its input before that run. No publishing job was manually run.

## Remaining review gaps / next safe actions

1. Coordinate the source-only RSI correction with the other worker's backend
   changes, rerun the suites, and deploy State API as one reviewed build.
   Update: the other worker deployed State API during acceptance; the live
   horizon endpoint now returns the corrected RSI description. This task did
   not initiate that backend deployment.
   Direct container check also returned neutral `50.0` for both flat 14-day
   and 98-day RSI series.
2. Non-overlapping windows reduce overlap but do not establish independence.
   Historical match counts are not a held-out edge. Keep descriptive labels,
   thin-sample warnings, and zero earned weighting; reserve confidence claims
   for a separately tested hold-out/uncertainty implementation.
3. The cone's square-root interpolation is a modelling convention, not measured
   intermediate-time quantiles. Its label must not imply a calibrated forecast.
4. Pre-2023 backfill and live-trading data are different eras. An era split,
   block-bootstrap uncertainty and held-out comparisons remain work, not delivered
   by the new causality tests.
5. Verify a completed Hermes prose reading separately; live gateway health is
   not evidence that a generated reading completed successfully.
6. Check the scheduled repair outcomes and weekly-recap input. Governance
   closeout artifacts must not be fabricated; do not raise all script timeouts
   merely to hide the graph-hygiene timeout.

## Reproduce visual acceptance

Use installed Playwright via `NODE_PATH`, set `TRADESYNC_QA_DIR` to
`E:/Visual QA/TradeSync Visual QA/Current Reviews/2026-09-13-context-timeframes`,
then run `node tools/qa_context_timeframes.cjs`. It only reads pages and clicks
feature navigation; it cannot run jobs or submit orders.

## Low-memory deployment path

The normal Docker compilation was stopped after State API and market-data
health probes began timing out. Free host RAM had fallen below 1 GiB. Both
services recovered without a restart after the task's build was stopped.
The already-built local frontend was packaged instead; this avoids a second
TypeScript/Vite compilation inside the live Docker VM:

```powershell
# First compile and test the intended source snapshot on the host:
# cd services/cockpit-ui; npm run build; cd ../..
docker build -f ops/cockpit-prebuilt.Dockerfile -t tradesync/cockpit-ui:dev services/cockpit-ui
docker compose --env-file E:/Projects/TradeSync/dashboard-runtime/runtime.env -f ops/compose.full.yml -f ops/compose.market-command.yml up -d --no-build --no-deps cockpit-ui
```

The Dockerfile-specific ignore file sends only `dist` and `nginx.conf`, not
credentials or dependencies. This packages an existing artifact, so it does
not prove later source edits were included. The ordinary source-building
Dockerfile remains unchanged. The temporary port-3013 preview was stopped.

Final runtime note: market-data briefly failed its 3-second `/readyz` probe
again during acceptance, then recovered to `healthy` without intervention.
Cockpit and State API were healthy. Host-memory contention remains an
operational risk; passing visual acceptance does not establish continuous
feed availability under load.
