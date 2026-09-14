# 2026-09-14 — Timeframes rebuild, liquidity and liquidations, canvas drawing, market-data outage

Paper-only throughout: no execution flag, gate, signer or wallet changed. Every feature added here is
context: none carries a scoring weight until it earns one.

## Why

Operator review of 14 September: the short-term timeframe addition was "trading horizons, not the
actual lower timeframe analysis"; theses had no timestamp or refresh; the timeframe charts were
unusable and did not use the integration pipeline; the Market page always said data was stale and that
the direct Hyperliquid liquidation feed was unavailable; the liquidity heatmap could not show where
liquidity builds up; nothing liquidity-related fed the thesis; the canvas could not be drawn on.

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

## Market Canvas drawing (merged, deployed)

TradingView-style drawing layer as a lightweight-charts series primitive: tool rail, trendline, ray,
extended and horizontal lines, vertical line, rectangle, fib retracement, measure, pencil, text; select,
drag, style bar, undo, drawings shown on every interval (merge `c13e882`, migration `027`).

## Tests (latest runs)

- Root 697 passed; one expected failure (`test_migrations` contiguous numbering) until migrations 028
  (opportunity learning) and 029 merge or are reassigned.
- State API 197, market-data 141, Cockpit unit tests 59, `npm run build` clean.

## Incident: Docker Desktop

Docker Desktop crashed under load and would not restart: stale AF_UNIX socket files
(`%LOCALAPPDATA%\Docker\run\sailor-ingest.sock`, `docker-secrets-engine\engine.sock`) could not be
removed. Recovered by renaming both folders aside (never factory reset: it would erase Postgres). WSL
was restarted with operator approval; the Hermes gateway came back once a hidden keep-alive WSL session
(`wsl.exe -d Ubuntu --exec sleep infinity`) was started. That session ends at logoff or reboot.

## Not yet done

- Regime Lab rebuild and opportunity learning (attribution, proposals, wording) are on their branches,
  awaiting merge, migration 028 and deploy.
- The Cockpit build with the timeframe wording fixes and the funding and premium chart colours is not yet
  deployed.
- Longer heatmap windows (7 and 30 days) fill in as recorded history accumulates.
