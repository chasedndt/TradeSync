# The one-hour return's restart gap, and positioning candidates tested for scoring

Date: 2026-09-15
Branch: `claude/feature-edge` from `db27305`. Paper mode only; nothing deployed from this branch.
Scope: `services/market-data/app/{return_1h,candle_anchor,snapshot_values,feature_extractor}.py`,
`config/features/market-feature-catalog-v1.json` (1.8.1: the one-hour return's source, comparator
and caveats only), `tools/{positioning_candidates.py,positioning/,return_anchor_candle_gap.py}`,
`docs/research/2026-09-15_positioning-candidates.md`, tests.

## Why the one-hour return disappeared after a restart

The brief expected an empty `mark_price_history` after a restart. The history is not emptied, and
persisting it would not have removed any measured spike:

- `mark_price_history` is market-data's own feature store, the Redis sorted set
  `market:feature:hyperliquid:<symbol>:hl_mark_price_usd` (one sample per 15-second bucket, seven
  days), written from every snapshot. `resolve_derived_features` reads its last 66 minutes.
- It survives restarts. Redis was recreated at 17:40:55 UTC on 14 September and market-data at
  17:57:30. Afterwards CVD still had 168 points of history, and the return came back at 18:41 with its
  own 168 points intact, including points from before the outage.
- What is missing after an **outage** is the market itself: nothing observes it while market-data,
  Redis or Docker is down. For the hour after recovery the anchor band (t − 65 min to t − 60 min)
  lies inside that hole, so each spike lasts the outage plus one hour:
  - 13 September: outage 12:33–14:48, return back 15:37.
  - 14 September: Docker Desktop outage 12:47–17:41, return back 18:41.
  - **15 September, live during this work:** verdicts stopped 06:20–09:40 with no container
    restart. From 09:40 to 10:40 CVD was ready in every verdict and the return in none; 379 of
    455 verdicts were refused, against about a quarter in ordinary hours.
- The same hour follows a market's first observation. On 12 September at 06:00 the universe went
  from three markets to ten.
- Verdicts with CVD ready but no return, per UTC day, and how many of them were refused for
  directional coverage:

  | Day | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 (to 10:55) |
  |---|---:|---:|---:|---:|---:|---:|---:|---:|
  | CVD ready, no return | 198 | 9 | 27 | 212 | 1,056 | 386 | 1,038 | 475 |
  | of those refused | 89 | 7 | 27 | 7 | 905 | 314 | 806 | 335 |

  Hours with **both** CVD and the return missing (775 on 12 September, 536 on the 13th, 1,185 on
  the 14th) are the outages themselves, for example Redis refusing writes on 14 September from
  06:00 to 12:00. No anchor fix touches those.

## What changed

1. **Unchanged move** (`0497cc2`). The derivation, its anchor selection and
   `attach_derived_features` moved to `return_1h.py`, and the two value helpers moved to
   `snapshot_values.py`. `feature_extractor` re-exports the names `main.py` imports. The return
   tests moved to `test_return_1h.py`.
2. **Venue candle anchor across a gap** (`fbe53b2`). The comparator stays: the newest *observed*
   mark price at or before t − 1 h, within the 5-minute tolerance. Only when no observed sample
   qualifies does `candle_anchor.py` supply the close of the newest Hyperliquid 1-minute candle
   that closed at or before the same target, within the same tolerance. The window never widens
   and never reaches forward. How it behaves:
   - **Provenance.** Each derivation records `comparator.anchor_source` (`observed_mark_price` or
     `venue_candle_close`, with the candle's open time and interval). A candle-anchored value's
     `source_event_id` starts `return1h-candle:`. An INFO log line names each market that took
     candle anchors.
   - **No waiting on the snapshot path.** The first snapshot after a gap schedules one
     `candleSnapshot` request per market, and a snapshot seconds later finds the anchor. One
     request answers every target up to the moment it was made, which is the whole hour a gap
     lasts.
   - **Failures.** A failed or empty fetch leaves the return absent and is retried after 60 s.
   - **Rate limit.** Requests share the venue rate limiter.
3. **Catalog 1.8.1** (`2558f95`). The one-hour return's source, comparator and
   caveats now state the fallback, where its provenance is recorded, and the measured difference
   below. Numbers, eligibility, blocks and weights are unchanged. Nothing reads the version except
   as a stamp on new records. The scorer compares catalog digests only when an adopted rulebook is
   active, and none is (`regime_weight_activations` is empty).
4. **Positioning candidates** (`9d13c22` declaration, `bd2c9b9` tooling,
   `cb5505c` results). See "Positioning candidates" below.

## Candle close against mark price (measured before relying on it)

`tools/return_anchor_candle_gap.py`, read-only through the state API, at 01:14 UTC on
15 September, covering about 17 hours of each market (5,037 candles, 15,453 one-hour returns
computed both ways):

| Market | Close − mark, median abs (bps) | p90 abs (bps) | Mean signed (bps) | Return difference, median abs (pp) | p90 abs (pp) | Same sign |
|---|---:|---:|---:|---:|---:|---:|
| BTC | 0.51 | 3.16 | +0.10 | 0.013 | 0.053 | 98.4% |
| ETH | 1.18 | 4.72 | +0.22 | 0.020 | 0.084 | 96.5% |
| HYPE | 1.74 | 7.42 | +0.39 | 0.025 | 0.106 | 97.9% |
| ZEC | 2.57 | 12.18 | +0.61 | 0.050 | 0.218 | 98.4% |
| SOL | 0.97 | 3.88 | +0.14 | 0.019 | 0.079 | 98.2% |
| XRP | 1.43 | 8.43 | +0.52 | 0.040 | 0.156 | 96.2% |
| NEAR | 2.08 | 9.90 | +0.09 | 0.049 | 0.191 | 97.8% |
| PUMP | 2.72 | 10.98 | +1.50 | 0.054 | 0.184 | 94.3% |
| LINK | 0.88 | 5.27 | +0.11 | 0.026 | 0.100 | 98.8% |
| UNI | 2.54 | 9.81 | +0.38 | 0.052 | 0.189 | 98.5% |
| **Pooled** | **1.61** | **7.76** | **+0.41** | **0.029** | **0.137** | **97.5%** |

A candle close is the last trade of its minute, and the mark price is the venue's median of oracle,
book and last-trade prices. The difference is a few basis points, a small fraction of a typical
one-hour move. The stored feature series does not carry `anchor_source`, so research over stored
values mixes up to one hour of candle-anchored returns after each outage. The catalog says so.

## Tests

All suites ran with the project venv through `tools/run_tests.py`, on the final tree:

| Suite | At `db27305` | After |
|---|---|---|
| market-data | 141 passed | **153 passed** |
| root | 803 passed, 17 deselected | **814 passed**, 17 deselected, 2 warnings, 49 subtests passed |
| state-api | not run at the base | **284 passed** (no state-api code changed; run because its tests read catalog 1.8.1) |

New tests:

- `services/market-data/tests/test_candle_anchor.py` (7):
  - only closed, well-formed 1-minute candles are kept;
  - the anchor is the newest close at or before the target and never beyond the tolerance;
  - one fetch answers every later target up to its own time;
  - a failed or empty fetch leaves no anchor and is retried only after the interval;
  - with no running event loop a request starts no I/O;
  - candles older than the keep window are dropped.
- `services/market-data/tests/test_return_1h_fallback.py` (5):
  - an observed mark anchor always wins;
  - without one, the candle close stands in and the comparator says so;
  - a stranded observed anchor does not block the candle;
  - without the cache the derivation stays on observed marks;
  - **restart after a five-hour outage:** the first snapshot schedules one venue request, the
    next snapshot eight seconds later has a return (asserted within two minutes), and every
    snapshot after it keeps one: candle-anchored for the first hour, observed after.
- `tests/test_positioning_candidates.py` (11):
  - the twenty declared readings match the committed declaration;
  - z parameters come from the catalog except the two declared gaps;
  - whole-second samples never land before entry;
  - the entry rule and its tolerance;
  - z uses only earlier samples;
  - the four-hour change needs 3 h 30 min of reach;
  - recorded against store readings, and the price product;
  - row building and abstains;
  - the Holm bar and window counts;
  - the failure reasons;
  - only an earned z reading with an edge after costs is admitted.

The 13 existing return tests moved unchanged to `services/market-data/tests/test_return_1h.py`.

## Positioning candidates

Twenty readings of nine candidates were declared and committed before any outcome was joined
(`9d13c22`). Each was tested in both polarities at 15, 60 and 240 minutes: 120 cells in one Holm
family, costs 0.12% per call, over 3,599 opportunities from 7 to 15 September (122,459
reading-outcome rows). Method, coverage and every cell are in
`docs/research/2026-09-15_positioning-candidates.md`.

**No candidate earned admission, so no scoring configuration changed.** Catalog eligibility,
rulebook blocks and weights are untouched.

- **Nothing reached detectability.** No cell reached |z| ≥ 2 in either direction. The strongest,
  `binance_open_interest_usd` as a z reading at 15 minutes, had z = +0.71 (one-sided p = 0.24)
  against a first-ranked Holm bar of z = 3.53.
- **Hold-out and costs never decided.** With no positive skill anywhere, neither condition was
  reached for any candidate.
- **Positive after costs was not skill.** Eleven cells were positive after costs, ten of them at
  240 minutes, where the market fell in 60–92% of windows. Short-leaning calls made money there
  without skill: skill +0.002 to +0.049, z at most +0.50.

| Candidate | History used | Best z (reading, horizon, polarity) | Reasons 15m / 60m / 240m | More days for a 0.10 / 0.05 edge: 15m; 60m; 240m |
|---|---|---|---|---|
| `hl_funding_hourly_rate` | store from 8 Sep | +0.50 (z, 240m, inverted) | C S / C S W / S W | 0 / 14; 12 / 68; 57 / 247 |
| `hl_funding_apr_24h` | store from 8 Sep | +0.35 (raw, 240m, inverted) | C S / C S W / C S W | 0 / 14; 12 / 68; 59 / 255 |
| `funding_spread_vs_binance_bps` | recorded from 12 Sep, z from 13 Sep | +0.26 (z, 240m, as read) | C S W / C S W / S W | 2 / 17; 14 / 66; 49 / 204 |
| `binance_funding_rate_8h` | recorded from 12 Sep, z from 13 Sep | +0.42 (z, 15m, inverted) | C S W / C S W / S W | 2 / 17; 14 / 66; 49 / 204 |
| `hl_open_interest_4h_pct` | store from 8 Sep | +0.21 (z, 15m, as read) | C S / C S W / C S W | 0 / 14; 12 / 68; 57 / 247 |
| `binance_open_interest_usd` | store from 13 Sep | +0.71 (z, 15m, as read) | C S W / C S W / C S W | 3 / 18; 15 / 65; 50 / 205 |
| `liq_map_skew_3pct` | recorded from 14 Sep 18:34 | +0.19 (raw, 60m, inverted) | C S W / C S W / C S W | 4 / 17; 15 / 61; 51 / 204 |
| `cex_liquidations_net_1h_usd` | store from 14 Sep 17:41 | +0.29 (raw, 15m, inverted) | C S W / C S W / C S W | 4 / 17; 15 / 59; 41 / 162 |
| `hl_oracle_premium_bps` | store from 8 Sep | +0.21 (z, 240m, inverted) | C S / C S W / C S W | 0 / 14; 12 / 68; 57 / 247 |

Reason codes:

- **W:** fewer independent windows than a 0.10 skill edge needs to clear the Holm bar (312).
- **S:** no Holm-adjusted positive skill.
- **C:** negative mean after costs.

A "0" means the horizon already had enough windows for a 0.10 edge and none appeared. The
liquidation-map and CEX-liquidation features have history only since the evening of 14 September.

## What remains

- **Outages still cost their duration.** Only the extra hour after recovery is removed.
- **A Redis loss also loses the return's own history** and every other feature's. With candle
  anchors the value comes back within a minute or two. Normalization still needs 30 points (30 minutes),
  and quality ramps to 1 over 168 minutes. Durable feature history belongs in Postgres, as the
  compose file notes, and is not built here.
- **Mark-price sampling has thinned since the 09:40 recovery.** BTC samples: median spacing 20 s,
  p90 65 s, largest gap 295 s, against 15 s, 20 s and 71 s on 14 September 19:00–22:00. The venue
  rate limiter reports no backoff. The cause is not established. A gap past 300 s now would remove
  the return an hour later; once this change is deployed, a candle covers it.
- **No admitted feature in two blocks.** Positioning (weight 0.20) and macro flows (0.10) still
  have none, so their quality stays 0. All nine candidates keep recording.
- **When the candidates become testable.** At the current rate of independent windows:

  | Horizon | A 0.10 skill edge | A 0.05 skill edge |
  |---|---|---|
  | 15 minutes | within about 4 days, every candidate | about 2½ weeks |
  | 60 minutes | within about 15 days | about 2 months |
  | 4 hours | after 41–59 days | 5–8 months |

- **Re-run once, at a fixed date.** Use the same declaration and tooling
  (`tools/positioning_candidates.py export`, `assess`, `report`). Re-running every few days until
  something passes is optional stopping and would need its own correction. A new reading is a new
  declaration and a new family.

## Deploy (for the lead)

**Rebuild:**

- `market-data`: the code change.
- `state-api` and `core-scorer`: so all three images carry catalog 1.8.1. The catalog is copied
  into each image, and mixed digests would matter once an adopted rulebook is active.

Nothing else ships for the candidates: none was admitted, so no rulebook or scoring change goes
out, and the analysis tools run from a checkout.

**Check afterwards:**

1. Within two minutes of market-data starting, `GET /state/market/snapshots` shows
   `derived.return_1h_pct` for all ten markets. With Redis intact and less than 5 minutes down,
   `comparator.anchor_source` is `observed_mark_price` throughout.
2. After any outage longer than 5 minutes, the first hour shows `venue_candle_close`, then
   `observed_mark_price`. The market-data log shows
   `1h return for <symbol>: no mark-price sample at t-1h; N closed 1m venue candles held as anchors`.
3. New `regime_paper_*` signals list `hl_return_1h_pct` in
   `features->'evidence'->'directional'->'ready_feature_ids'` within minutes of recovery, not an
   hour later.
4. `GET /state/market/status` keeps the Hyperliquid backoff at 1.0.
5. New signals stamp `catalog_version` 1.8.1.
