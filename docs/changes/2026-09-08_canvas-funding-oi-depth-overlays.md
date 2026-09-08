# Slot 5.4 — funding, open interest and depth on the Market Canvas

Date: 2026-09-08
Scope: `services/market-data`, `services/state-api`, `services/cockpit-ui`

## What was added

The canvas showed price and the paper evidence recorded against it. It now also
shows the three things you look at next when reading a perp: what it costs to
hold the position, whether anyone is putting on new ones, and where the size is
sitting right now.

- **Funding**, beneath price, from the venue's own `fundingHistory`.
- **Open interest**, beneath that, from our context poller.
- **Depth**, beside the chart, from the current L2 book, with resting walls
  drawn on the price axis.

## The design decision each one forced

### Funding and open interest do not have the same reach

Hyperliquid publishes funding history for as far back as the chart goes. It
publishes **only the current** open interest — there is no history endpoint, so
the only open-interest series that can exist is the one we recorded ourselves,
and `market:ts:*:oi` holds a rolling 24 hours.

On a 1h chart of 300 candles — 12.5 days — that means the open-interest line
covers the last 8% of the window and stops. Drawn without explanation that
reads as a data fault. Each pane therefore states its coverage in its header
(`24/301 buckets · 8%`) and its source, and the open-interest pane carries the
reason: *"Hyperliquid publishes only current open interest, so this is our own
recording and reaches back at most 24 hours."*

### Coverage has to be measured against the right denominator

Funding first reported 24.7% coverage on a 15m chart. Nothing was missing: it is
hourly, so it can never fill more than one bucket in four. Measured against a
15m grid a complete funding series can never score above 25%, and a number that
can never be good is not a measurement.

Funding is now measured against its own hourly grid and reports 96–100%. Open
interest, which really is sampled per candle, keeps the candle grid, and its
low percentages on wide windows are the honest signal they look like.

### A gap must not be drawn as a flat line

`bucket_series` omits a bucket that holds no sample, and the panes render those
slots as whitespace rather than joining across them. A collection outage and a
market that did not move look identical once a line is drawn through the hole,
and only one of them is true. The same rule the candle path already follows.

A malformed sample is dropped rather than defaulted to zero, for the same
reason: a zero funding rate is a claim about the market we do not have the
evidence to make.

### The poller writes the same value many times

Open interest arrives 500+ times per 15m bucket, because one context poll
produces several events, each event produces a snapshot, and each snapshot
appends a point. Collapsing with `last` per bucket removes the duplication as a
side effect of the alignment. The panes report `samples` per bucket so the
duplication is visible rather than hidden.

### Funding over a wide bucket is a total, not a sample

A 1d bucket spans 24 hourly rates. Reporting one of them would understate the
cost by 24×, so buckets wider than an hour sum, and the response labels the unit
`rate_summed_over_bucket` so the pane can say "funding paid per bucket" instead
of "funding rate".

### Depth is not a time series

The book is replaced wholesale on every poll. Drawing today's resting size
across yesterday's candles would assert it was there, so depth is a panel beside
the chart, not an overlay. What can go on the price axis is the walls, and they
are **dotted** where operator annotations are **dashed** — an operator's level
is theirs until they remove it, a wall vanishes the moment the order is pulled.

A wall must hold at least 15% of its **own side's** visible notional. Measuring
against both sides combined would let a thin ask book promote an ordinary bid
into a wall. An evenly spread book reports no walls at all, and the panel says
so rather than lowering the bar until something appears.

## Defect found and fixed

`GET /state/market/candles?venue=binance` returned **500 Internal Server Error**.
market-data correctly answers 404 for an unsupported venue, but the proxy fell
through to `resp.raise_for_status()`, which escaped as a server fault. Nothing
had failed — the operator asked for a venue this system does not carry.

All three market proxies now pass a 404 through as a 404 with the upstream
reason. Found by exercising refusal paths after building the happy path, which
is the second time in this project that has turned up a real bug.

## Files

New, pure and tested (18 tests):

- `services/market-data/app/context_series.py` — bucketing and coverage
- `services/market-data/app/depth.py` — cumulative ladder and wall detection

New endpoints:

- market-data `GET /context/{venue}/{symbol}`, `GET /depth/{venue}/{symbol}`
- state-api `GET /state/market/context`, `GET /state/market/depth`

Cockpit, split out of a `MarketCanvas.tsx` that had reached 359 lines:

- `components/canvas/ContextPane.tsx` — one synced pane
- `components/canvas/ContextPanes.tsx` — funding and open interest with headers
- `components/canvas/DepthLadder.tsx` — book, ladder, walls
- `components/canvas/CanvasToolbar.tsx`, `AnnotationList.tsx`
- `components/canvas/useCanvasLayers.ts` — markers, price levels, shapes
- `api/hooks/useMarketContext.ts`

`MarketCanvas.tsx` is now 253 lines of composition. Every file is under the
300-line limit.

### Pane alignment

The panes are separate charts synced to the price chart's visible **logical**
range. That works only because each pane emits one slot per candle including the
empty ones, so index *n* means the same candle in every chart. Both also pin
`rightPriceScale.minimumWidth` to 100 — without it the price axis grew to fit
`84000.00` while the funding axis stayed narrow, and the two plot areas were
offset by about 17px, which is exactly enough to read a spike against the wrong
candle.

## Verified

Live, against Hyperliquid, on 2026-09-08:

```
 15m bucket=   900s  funding  24 pts  96.0%  oi  84 pts  86.6%
  1h bucket=  3600s  funding  48 pts  98.0%  oi  24 pts  49.0%
  1d bucket= 86400s  funding   8 pts 100.0%  oi   2 pts  25.0%
```

Open-interest coverage falling as the window widens is the 24-hour recording
limit showing up exactly where it should.

Depth, live: mid 78,401.5, spread 0.13 bps, imbalance −7.8%, sweep to the tenth
bid $1.46M, and an ask wall holding 69% of its side. Ladder arithmetic checked
by hand against the response.

Refusal paths, live: unsupported venue → 404 on all three proxies; unsupported
interval → 400 naming the supported set; `limit=5000` → 422; a symbol with no
book → 503, never an empty ladder.

Tests: 406 passing across the four suites (`python tools/run_tests.py`).
`npm run build` clean.
