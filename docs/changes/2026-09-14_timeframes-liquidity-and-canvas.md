# 2026-09-14 — Timeframes, liquidity and liquidations, canvas drawing, Regime Lab, opportunity learning

Paper-only throughout: no execution flag, gate, signer or wallet changed. Every feature added here is
context: none carries a scoring weight until it earns one, and no weight moves without an operator.

## Why

Operator review of 14 September: the short-term timeframe addition was "trading horizons, not the
actual lower timeframe analysis"; theses had no timestamp or refresh; the timeframe charts were
unusable and did not use the integration pipeline; the Market page always said data was stale and that
the direct Hyperliquid liquidation feed was unavailable; the liquidity heatmap could not show where
liquidity builds up; nothing liquidity-related fed the thesis; the canvas could not be drawn on;
opportunities still said demo, observe mode and dry run, and nothing recorded why a call failed or which
part of the taxonomy or weighting caused it; the Regime Lab was poor and its Learning Gate could not be
typed in.

## Outage found on the way (fixed, deployed)

- Market-data's Redis was full (160 MB, `noeviction`): every write had failed since about 08:30, so all
  ten snapshots froze and features went stale. Limit raised to 700 MB (container 1 GB, 1 CPU), RDB
  snapshots turned off on top of the append-only log (`ops/compose.market-command.yml`; commits
  `2e9d19b`, `648e7f0`). After the Docker Desktop incident below, Redis was recreated from compose so the
  limits persist.
- The Market page's stale banner read `data_age_ms` (the oldest metric, never refreshed); it now reads
  `snapshot_age_ms`. The permanent "Direct Hyperliquid liquidation feed unavailable" card is gone.
- Feature observations and open-interest rows now carry the time their metric was read, not when the
  snapshot was assembled (`351987b`).
- The Bybit liquidation collector no longer dies on a Redis error (`648e7f0`).

## Timeframes (deployed)

- Engine on bars (`eccdb24`): 1 hour and 4 hours on 15-minute candles, 8 hours and 1 day on hourly
  candles, 3 days to 6 months on daily candles. Every horizon gets the same analysis: trend, momentum,
  the record for today's state, the ordinary range, levels, and every feature with its record.
- Earned weights (`horizon_weights.py`): states learned on the older 70% of history, tested on the newest
  30%; skill is the hit rate above what chance scores given the test period's own up-share; weight only
  when skill is one standard error above chance, shrunk for few test windows. The combined lean divides
  by at least one full unit of weight, so a single weak feature cannot read as a strong lean.
- The day or bar still trading ends no record window; participation reads through the last closed bar.
- Measurements: short term every 5 minutes from topped-up candles, daily hourly; a stale measurement is
  served while it re-measures; `POST /state/market/horizons/refresh` measures now (`55a8271`).
- Hermes readings per band (short, lower, medium, higher), stored with start, finish and the measurement
  they read (migration `030_horizon_readings.sql`); the page shows the exact time, keeps the last good
  reading during a new one, and flags a reading older than the numbers.
- Page rebuilt (`3bf9917`, wording `a24556e`): strip of all ten horizons, selected horizon in words, the
  band's reading, one large chart with feature toggles, synced lower panes and values under the
  crosshair, and an evidence table with out-of-sample hit rates and weights.
- Funding and premium (`b851bff`): Hyperliquid's hourly funding rate and oracle premium aligned to each
  horizon's bars (rate in force at a short bar's close, the day's mean for daily bars), ranked against
  their own range, with records and weights like any feature.
- Live check (BTC, 18:41 and 18:58 BST): 4 hours ahead weighted "balanced" −0.07 (Drawdown 0.17, Momentum
  0.16, Trend 0.09 earned); funding +10.9% a year, percentile 95 of 30 days, weight 0 so far.
- Live check after the final deploy (BTC, 19:45 BST): "refresh now" showed "measuring…" and moved both
  measurement times (19:41 and 19:37) to 19:45 within 10 seconds; 4 hours ahead then read weighted lower
  −0.20. The 4-hour chart shows 15-minute candles, the 12-hour average, one ordinary 4-hour move above
  and below, the record cone (median, middle half, 10th to 90th) and an RSI pane.

## Liquidity and liquidations (deployed)

- Durable history (migration `029_market_history.sql`, `32a4e17`): aggregated Hyperliquid books at 3 and
  2 significant figures (websockets, one per aggregation), Hyperliquid open interest, and liquidations
  received from Bybit and Binance, recorded once a minute by state-api's `market_recorder`; books kept a
  minute apart for 3 days then every 15 minutes to 90 days. Recording began 14 September 11:38 UTC.
- `GET /state/market/liquidity-heatmap`, `/liquidation-map`, `/liquidations` (`5d9caf0`); Market page
  panels (`3da2b93`): resting-liquidity heatmap behind candles with the largest walls marked; estimated
  liquidation heatmap (Binance open-interest changes placed at Hyperliquid prices with a stated leverage
  mix, cleared when price trades through) with its clusters; received liquidations by side.
- Binance's legacy `/ws` stream route accepts a connection and sends nothing; the collector uses
  `/market/ws` (`f6bf0c3`). Live: 50 Binance and 58 Bybit liquidations recorded by 18:56 BST.
- Feature catalog 1.8.0 (`53fef11`): resting-liquidity balance, bid and ask wall distances, received
  liquidations net, liquidation-map skew and largest clusters, recorded at their own times, all
  non-scoring context; three of them added to the thesis context Hermes reads.
- Live check (BTC): bid wall 78,700 ($33.7m, −0.19%), ask wall 79,200 ($37.1m, +0.44%); estimated
  clusters 84,557 (+7.3%) and 73,278 (−7.0%).
- Live check after the final deploy (BTC, about 19:50 BST): resting liquidity over 24 hours, ask wall
  79,500 ($106.7m) and bid wall 79,100 ($32.0m, −0.19%); estimated liquidations over 7 days, clusters
  84,557 (+7.0%, $195.4m) and 73,278 (−7.3%, $139.5m), balance within 3% +0.87; received liquidations
  over 24 hours, 159 events, shorts $4.1m and longs $14k.

## Market Canvas drawing (merged, deployed)

TradingView-style drawing layer as a lightweight-charts series primitive: tool rail, trendline, ray,
extended and horizontal lines, vertical line, rectangle, fib retracement, measure, pencil, text; select,
drag, style bar, undo, drawings shown on every interval (merge `c13e882`, migration `027`).

- Live check: Trend line selected and dragged across the BTC 15-minute chart; the drawing was saved
  (`POST /state/canvas/drawings` 200) and listed; Ctrl+Z removed it (`DELETE` 200); after a reload the
  four drawings recorded on 8 September were unchanged.

## Regime Lab (merged, deployed)

Rebuilt (merge `a41148d`): the Learning Gate is gone; statistics are cached and computed off the event
loop (the overview answered in 0.12 s); challengers are judged by replaying a fixed window; each section
fails on its own without blanking the page. Live check (BTC): 23 of 28 readings fresh, scoring coverage
70%, sections Feature evidence, Challenger and Saved drafts; the page states that nothing in it can
activate a rulebook or place an order.

## Opportunity learning (merged, deployed)

Merge `4a46401`, migration `028_opportunity_learning.sql`:

- Opportunities expire (15 minutes by default) instead of piling up as "new".
- Every outcome at 15 minutes, 1 hour and 4 hours is attributed: clean win, win after drawdown, no
  follow-through, reversed or wrong direction, after a 0.12% round trip, with the readings that supported
  or misled the call in plain words (for example a SOL short "misled by Coinbase premium, CVD order flow
  and depth within 25 bp while price rose; entry regime rising").
- Verdicts per feature, block, entry regime and symbol: the misled rate against chance, with a 95%
  interval on an effective sample that counts calls in the same horizon-long window as one cluster.
- Walk-forward weight proposals, learned on older decisions and replayed on the newest; an operator
  adopts, rejects or reverts, and the name is recorded. Nothing is adopted automatically.
- Opportunities page: "demo", "observe mode" and "dry run" wording removed; a Learning view shows the
  scoreboard after costs, weight proposals, the latest failures and what the evidence says.
- Live scoreboard (14 days to 14 September, 8,689 attributed horizons): 15 minutes won 25.6% (21.2% to
  30.7%), mean net −0.119%; 1 hour 35.6% (25.9% to 46.6%), −0.113%; 4 hours 42.5% (24.9% to 62.4%),
  −0.127%. The walk-forward at 19:36 BST (2,998 decisions) found no feature or block with a verdict at
  1 hour, so no weight moved: every interval still includes chance (Coinbase premium misled 51.4%, CVD
  51.0%, 1-hour return 47.4%, each on about 80 effective samples).

## Why calls are refused (measured 14 September)

Seven days to 18:48 UTC: 19,945 admitted, 17,632 refused. A refusal can carry several reasons: direction
too weak to call 10,864; data coverage below the 0.3 floor 7,387; directional coverage below the 0.5
floor 5,982; no admitted evidence 2,805; paper risk fully capped 2,805; no directional evidence 2,674.

- The directional-coverage refusals cluster in outage and restart windows, when the 1-hour return had no
  comparator for nearly every verdict: 11 September 21–23 UTC, 12 September 06–08 and 11–15,
  13 September 12–15, 14 September 06–11 (the Redis outage) and 17–18 (the recreate). In ordinary hours
  they run at 0 to 50 an hour.
- Positioning (weight 0.20) and macro flows (0.10) have no admitted features, so their quality is always
  0. Coinbase premium, the only spot-premium feature, exists for BTC, ETH and SOL only, so the other seven
  symbols can reach at most two of three directional readings: each is admitted about 1,100 to 1,200
  times a week against about 4,000 for BTC, ETH and SOL.

## Tests (fully merged tree)

- Root 803, state-api 282, market-data 141, exec-hl-svc 3, signer-svc 10 passed.
- Cockpit unit tests 61 passed; `npm run build` clean (0 TypeScript errors).
- Migrations 026 to 030 applied and contiguous (market history renumbered from 031 to 029 in the merge;
  the database also keeps a harmless 031 record from before the rename).

## Deploys

State-api and core-scorer rebuilt after the merges (healthy; background loops include
`opportunity_expiry` and `opportunity_learning`); Cockpit rebuilt at 19:38 BST (healthy). No errors in the
state-api, core-scorer or market-data logs in the following 15 minutes. In the browser, Timeframes,
Market, Opportunities (both views), Regime Lab and Market Canvas show none of "demo", "observe mode",
"dry run", "Learning Gate", "data is stale" or "feed unavailable".

## Incident: Docker Desktop

Docker Desktop crashed under load and would not restart: stale AF_UNIX socket files
(`%LOCALAPPDATA%\Docker\run\sailor-ingest.sock`, `docker-secrets-engine\engine.sock`) could not be
removed. Recovered by renaming both folders aside (never factory reset: it would erase Postgres). WSL
was restarted with operator approval; the Hermes gateway came back once a hidden keep-alive WSL session
(`wsl.exe -d Ubuntu --exec sleep infinity`) was started. That session ends at logoff or reboot.

## Not yet done

- Hermes readings per band run on demand ("ask Hermes"), not on a schedule, given the Hermes compute
  review; the short band currently reads "Not read yet".
- Longer heatmap windows (7 and 30 days) fill in as recorded books accumulate; the estimated liquidation
  map already reaches back to 25 August through Binance open-interest history.
- After a market-data restart the 1-hour return has no comparator for an hour, so most calls are refused
  for that time.
- Positioning and macro flows carry no admitted scoring features; admitting one stays an operator
  decision on its evidence card.
