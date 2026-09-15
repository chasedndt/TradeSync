# Positioning candidates as scoring inputs: funding, open-interest change, liquidation skew

Date: 2026-09-15
Status: **pre-declared.** Everything above "Results" was written and committed before any
outcome was joined to any reading. Results are appended below that line, never edited into
the declaration.

## Why

Paper calls lose after a 0.12% round trip at every horizon (14 September scoreboard: 15m won
25.6%, 1h 35.6%, 4h 42.5%). The rulebook's positioning block (weight 0.20) and macro-flows block
(0.10) have no admitted directional feature, so their quality is always 0. This tests whether any
positioning candidate already recorded by market-data earns admission by the repository's rule
(`docs/MARKET_COMMAND_PLAN_2026-09-11.md` §5.1): positive skill after the multiple-test
adjustment that also held out of sample, after costs.

## Data

- **Outcomes:** `opportunity_outcomes` rows with `status = 'measured'` at 15, 60 and 240 minutes,
  every LONG/SHORT opportunity from the first (7 September 23:54 UTC) to the export time. A
  reading's call is scored against the forward return; the opportunity's own direction is not used.
- **Entry readings recorded by the outcome job** (`opportunity_entry_features`, written once at
  entry): `binance_funding_rate_8h`, `funding_spread_vs_binance_bps`, `liq_map_skew_3pct`, and
  `hl_return_1h_pct` (used only inside the open-interest-with-price readings).
- **Entry readings reconstructed** (catalog `signal_kind` is `none`, so the job never selects
  them): `hl_funding_hourly_rate`, `hl_funding_apr_24h`, `hl_open_interest_4h_pct`,
  `hl_oracle_premium_bps`, `cex_liquidations_net_1h_usd`, `binance_open_interest_usd`. Rebuilt
  with the job's own rule, `tradesync_core.entry_features.reading_at_entry` with
  `tolerance_ms(spec)` (the feature's `fresh_after_ms` plus `sampling_interval_ms`), from the
  market-data feature store read through `GET /state/regime-lab/feature-history` (the newest
  2,000 samples per feature: the whole seven-day store for hourly and five-minute features,
  roughly the last 33 to 43 hours for one-minute features). The proxy reports whole seconds, so
  each sample is treated as observed at the last millisecond of its second: a sample that could
  have been taken after entry is never used.
- **z readings** use the same store series: the samples strictly before the entry reading's own
  sample, the last `lookback_points` of them, at least `minimum_history_points`, through
  `tradesync_core.feature_statistics.z_score_statistics`, the scorer's own code.
- **Costs:** `services/state-api/app/skill_gate.py` `COSTS`: taker fee both ways at the venue's
  base tier (0.09%), 2 bps spread, 1 bps slippage; 0.12% per call. Funding not included.

## Method

`tradesync_core.feature_evidence.assess_feature_cards`, unchanged, with each declared reading as
its own card: the reading's sign is a call (positive LONG, negative SHORT, zero abstains), scored
in both polarities (`as_read`, `inverted`) against the forward return. Independence is counted
from non-overlapping windows with symbols pooled; the standard error is the larger of that
binomial error and a 400-draw block bootstrap (seed 0); skill is the hit rate minus the rate a
guesser with the same long share scores on the period's own up-share; the latest 30% of each
cell is held out; one Holm step-down (one-sided, α = 0.025) runs across **every cell of every
declared reading together**.

## Pre-declared readings

Every reading is tested `as_read` and `inverted` at 15, 60 and 240 minutes: 6 cells each.
**20 readings, 120 cells, one family.** A cell with no observations enters no test and is reported
as empty. "Expected" names the polarity the economic story predicts; it does not change the test.

| # | Reading | Value whose sign is the call | as_read means | inverted means | Expected |
|---|---|---|---|---|---|
| 1 | `hl_funding_hourly_rate:raw` | Hyperliquid funding rate at entry | follow the side that pays | fade it (crowded) | inverted |
| 2 | `hl_funding_hourly_rate:z` | robust z, 168 prior samples, min 30 (catalog) | funding above its week: follow | fade | inverted |
| 3 | `hl_funding_apr_24h:raw` | 24-hour mean funding, annualized | follow | fade | inverted |
| 4 | `hl_funding_apr_24h:z` | robust z, 24 prior samples, min 12 † | follow | fade | inverted |
| 5 | `funding_spread_vs_binance_bps:raw` | Hyperliquid 8h funding minus Binance 8h funding | Hyperliquid crowd longer than the market: follow | fade | inverted |
| 6 | `funding_spread_vs_binance_bps:z` | robust z, 240 prior samples, min 20 † | follow | fade | inverted |
| 7 | `binance_funding_rate_8h:raw` | Binance funding rate | follow | fade | inverted |
| 8 | `binance_funding_rate_8h:z` | robust z, 240 prior samples, min 20 † | follow | fade | inverted |
| 9 | `hl_open_interest_4h_pct:raw` | 4-hour open-interest change | leverage building: LONG | leverage building: SHORT | none |
| 10 | `hl_open_interest_4h_pct:z` | ordinary z, 168 prior samples, min 30 (catalog) | as row 9 | as row 9 | none |
| 11 | `hl_open_interest_4h_pct:with_price` | 4h OI change × `hl_return_1h_pct` | OI confirms the move: continue (OI up follows price, OI down fades it) | the opposite | as_read |
| 12 | `binance_open_interest_usd:change_4h` | % change from the earliest store sample in [t−4h, t], which must be at or before t−3h30m | building: LONG | building: SHORT | none |
| 13 | `binance_open_interest_usd:change_4h_with_price` | row 12 × `hl_return_1h_pct` | continue | reverse | as_read |
| 14 | `binance_open_interest_usd:z` | robust z of the USD level, 240 prior samples, min 20 † | as row 12 | as row 12 | none |
| 15 | `liq_map_skew_3pct:raw` | estimated short levels within 3% above minus long levels within 3% below, over both | more to liquidate above: price drawn up | the heavier side holds: fade | as_read |
| 16 | `liq_map_skew_3pct:z` | robust z, 288 prior samples, min 48 (catalog) | as row 15 | as row 15 | as_read |
| 17 | `cex_liquidations_net_1h_usd:raw` | long minus short notional liquidated on Bybit/Binance, last hour | longs flushed: bounce (LONG) | cascade continues (SHORT) | as_read |
| 18 | `cex_liquidations_net_1h_usd:z` | robust z, 240 prior samples, min 60 (catalog) | as row 17 | as row 17 | as_read |
| 19 | `hl_oracle_premium_bps:raw` | mark minus oracle | perp buyers paying up: follow | rich perp reverts: fade | inverted |
| 20 | `hl_oracle_premium_bps:z` | robust z, 168 prior samples, min 30 (catalog) | follow | fade | inverted |

† The catalog normalization is `none`, so admission would first have to choose one: robust z
with the catalog's own `lookback_points` and `minimum_history_points` is declared here, except
`hl_funding_apr_24h`, whose catalog minimum of 1 cannot support a z-score (12 of its 24 is used).

Value ranges were looked at before declaring (not outcomes): Hyperliquid BTC funding never
exceeded the 0.00125%/h interest level in the store, BTC's oracle premium was negative in 1,509 of
1,510 samples, and Binance BTC funding was always positive. A raw sign that rarely changes cannot
beat a guesser with the same bias, which is why every candidate also carries its z reading.

## Decision rule (binding)

1. A cell **earns** when it has `positive_skill` (Holm across all 120 cells, z ≥ 2) and a positive
   hold-out skill (`feature_evidence.earned_by`) **and** `economic_edge` (mean return after the
   0.12% costs above zero).
2. A candidate is **admitted** only when an earning cell belongs to a reading the scorer can
   implement for that feature id: its `z` reading, as `score_mode` `direct` (as_read) or `inverse`
   (inverted). The scorer calls direction from the normalized score, not from the raw sign, so a
   raw, with-price or change reading that earns without its z reading is reported as earned and
   not admitted; implementing it would need a separate catalog change.
3. On admission: catalog version bump, `scoring_eligible` with the declared direction, the feature
   listed in its rulebook block, block weights unchanged, tests updated.
4. If nothing earns, no scoring configuration changes. For each candidate the doc states which
   reasons apply at each horizon: *too few independent windows* (fewer than a 10-point skill edge
   would need to clear the Holm bar), *no positive skill*, *failed hold-out*, *negative after
   costs*; and roughly how much more data it needs: the independent windows n* for a true skill of
   s to reach the Holm bar, n* = (z_Holm / 2s)² with z_Holm the one-sided normal quantile at
   0.025/120 (binomial error, first-ranked cell), at s = 0.05 and s = 0.10, and the days that
   implies at the reading's observed rate of independent windows per day.

## Results

Run on 15 September. The export (`2026-09-15T11:00:58Z`) ran from commit `bd2c9b9`, where the tooling
was committed after the declaration. The assessment used 400 bootstrap draws, seed 0, and the
catalog 1.8.0 parameters. Catalog 1.8.1, committed later the same day, changes only the one-hour
return's text.

- **Outcomes.** 3,599 LONG/SHORT opportunities opened from 7 September 23:54 to 15 September
  10:42 UTC with a measured outcome: 10,484 outcomes (15m 3,321, 60m 3,584, 240m 3,579) and
  122,459 reading-outcome rows. The period's own up-share was 48.3% at 15 minutes, 49.1% at 60 and
  37.3% at 240. There are no opportunities from 06:20 to 09:40 on 15 September, when the paper
  scorer stopped.
- **Store reach.** One-minute store series reached back to about 10:45 on 13 September: roughly 48
  hours including the 3 h 20 min stop, a little more than the declaration's rough 33 to 43 hours.
  Five-minute and hourly series held fewer than 2,000 samples, so the whole store was read.
- **Reconstruction check.** For the three candidates the outcome job records at entry, the store
  rule used for the other six chose the job's own sample in:
  - 1,406 of 1,429 entries (Binance funding);
  - 1,408 of 1,431 (funding spread);
  - 595 of 597 (liquidation-map skew).

  Every other entry had an adjacent sample of the same sign, or no reading on either side. None
  had a different sign, and none was a reading the job did not have.

### Decision

**No candidate earns admission. No scoring configuration changes.**

- **Nothing is detectable.** No cell reached |z| ≥ 2 in either direction. The largest one-sided z
  was +0.71: `binance_open_interest_usd:z` at 15 minutes, as read, with 129 independent windows,
  skill +0.031, hold-out +0.010 and −0.100% after costs. Its p = 0.24 is far from the first-ranked
  Holm bar of p ≤ 0.00021 (z ≥ 3.53).
- **Nothing is earned.** No cell has Holm-adjusted positive skill, so nothing is earned and nothing
  has an economic edge. The hold-out and cost conditions never had to decide a verdict.
- **Positive after costs is not skill here.** Eleven cells show a positive mean after costs. Ten
  are at 240 minutes, where the market fell in 60% to 92% of windows, so calls leaning short made
  money without skill. Against a guesser with the same lean, their skill is +0.002 to +0.049 and z
  is at most +0.50. This is the base-rate trap that the chance-adjusted measure exists to catch.
- **No declared expectation held.** None showed positive skill at any horizon: inverted funding,
  inverted oracle premium, liquidations and skew as read, or open interest confirming price.
  Hyperliquid open interest with price, as read, was negative at every horizon (z −0.10, −0.04,
  −0.08); the Binance version stayed within ±0.20.

### Why each candidate was not admitted, and how much more data it needs

A 0.10 skill edge needs 312 pooled independent windows to reach the Holm bar, and a 0.05 edge
needs 1,246. The table uses each candidate's reading with the most windows, at its current rate:

| Candidate | Horizon | Independent windows now (best reading) | Span (days) | Windows per day | More days for skill 0.10 (312) | More days for skill 0.05 (1,246) |
|---|---:|---:|---:|---:|---:|---:|
| `hl_funding_hourly_rate` | 15m | 422 | 6.8 | 61.6 | 0 | 14 |
| `hl_funding_hourly_rate` | 60m | 115 | 6.8 | 16.8 | 12 | 68 |
| `hl_funding_hourly_rate` | 240m | 33 | 6.7 | 4.9 | 57 | 247 |
| `hl_funding_apr_24h` | 15m | 413 | 6.9 | 60.1 | 0 | 14 |
| `hl_funding_apr_24h` | 60m | 112 | 6.7 | 16.7 | 12 | 68 |
| `hl_funding_apr_24h` | 240m | 32 | 6.7 | 4.8 | 59 | 255 |
| `funding_spread_vs_binance_bps` | 15m | 204 | 3.2 | 64.5 | 2 | 17 |
| `funding_spread_vs_binance_bps` | 60m | 57 | 3.1 | 18.2 | 14 | 66 |
| `funding_spread_vs_binance_bps` | 240m | 18 | 3.0 | 6.0 | 49 | 204 |
| `binance_funding_rate_8h` | 15m | 205 | 3.2 | 64.8 | 2 | 17 |
| `binance_funding_rate_8h` | 60m | 57 | 3.1 | 18.2 | 14 | 66 |
| `binance_funding_rate_8h` | 240m | 18 | 3.0 | 6.0 | 49 | 204 |
| `hl_open_interest_4h_pct` | 15m | 419 | 6.9 | 60.9 | 0 | 14 |
| `hl_open_interest_4h_pct` | 60m | 114 | 6.8 | 16.7 | 12 | 68 |
| `hl_open_interest_4h_pct` | 240m | 33 | 6.7 | 4.9 | 57 | 247 |
| `binance_open_interest_usd` | 15m | 129 | 2.0 | 64.6 | 3 | 18 |
| `binance_open_interest_usd` | 60m | 37 | 2.0 | 18.9 | 15 | 65 |
| `binance_open_interest_usd` | 240m | 11 | 1.8 | 6.1 | 50 | 205 |
| `liq_map_skew_3pct` | 15m | 49 | 0.7 | 72.9 | 4 | 17 |
| `liq_map_skew_3pct` | 60m | 13 | 0.6 | 20.5 | 15 | 61 |
| `liq_map_skew_3pct` | 240m | 3 | 0.5 | 6.1 | 51 | 204 |
| `cex_liquidations_net_1h_usd` | 15m | 51 | 0.7 | 72.8 | 4 | 17 |
| `cex_liquidations_net_1h_usd` | 60m | 14 | 0.7 | 21.1 | 15 | 59 |
| `cex_liquidations_net_1h_usd` | 240m | 4 | 0.5 | 7.7 | 41 | 162 |
| `hl_oracle_premium_bps` | 15m | 420 | 6.9 | 61.1 | 0 | 14 |
| `hl_oracle_premium_bps` | 60m | 114 | 6.8 | 16.7 | 12 | 68 |
| `hl_oracle_premium_bps` | 240m | 33 | 6.7 | 4.9 | 57 | 247 |

- **Hyperliquid funding (hourly and 24-hour APR), Hyperliquid open-interest change, oracle premium.**
  At 15 minutes each already had more windows than a 0.10 edge needs, and none showed positive
  skill (best z +0.21), so an edge that large at 15 minutes is unlikely. At 60 and 240 minutes:
  too few windows, and no skill.
- **Funding spread against Binance, Binance funding.** Recorded at entry since 12 September; their
  z readings run from 13 September. Too few windows at every horizon, no positive skill.
- **Binance open interest** (store reach from 13 September). Its best cell is the strongest overall
  (above): too few windows, no Holm-positive skill, negative after costs.
- **Liquidation-map skew and CEX net liquidations.** History only since the evening of
  14 September: 49 to 51 independent windows at 15 minutes, 13 to 14 at 60 and 3 to 4 at 240. No
  positive skill, and far too few windows to say anything either way.

Generated by `tools/positioning_candidates.py report`:

Export 2026-09-15T11:00:58Z (commit `bd2c9b9`), catalog 1.8.0: 3599 opportunities with a measured outcome, 122459 reading-outcome rows. 120 of the 120 declared cells had calls and entered the Holm family; first-ranked bar z = 3.53; independent windows needed for a true skill of 0.10 / 0.05: 312 / 1246. Costs 0.12% per call.

### Coverage

| Reading | Entry value from | Entries with a reading | Zero (abstains) | Calls 15m / 60m / 240m | First – last entry (UTC) |
|---|---|---:|---:|---|---|
| `hl_funding_hourly_rate:raw` | feature store | 3235 | 0 | 3235 / 3232 / 3227 | 08 Sep 13:40 – 15 Sep 10:00 |
| `hl_funding_hourly_rate:z` | feature store | 2794 | 0 | 2794 / 2791 / 2786 | 09 Sep 18:00 – 15 Sep 10:00 |
| `hl_funding_apr_24h:raw` | feature store | 3191 | 0 | 3191 / 3176 / 3176 | 08 Sep 13:40 – 15 Sep 10:42 |
| `hl_funding_apr_24h:z` | feature store | 2810 | 0 | 2810 / 2795 / 2795 | 09 Sep 01:01 – 15 Sep 10:42 |
| `funding_spread_vs_binance_bps:raw` | entry record | 2272 | 237 | 2035 / 2020 / 2018 | 12 Sep 06:47 – 15 Sep 10:42 |
| `funding_spread_vs_binance_bps:z` | entry record | 1385 | 7 | 1378 / 1363 / 1361 | 13 Sep 10:45 – 15 Sep 10:42 |
| `binance_funding_rate_8h:raw` | entry record | 2276 | 0 | 2276 / 2261 / 2259 | 12 Sep 06:47 – 15 Sep 10:42 |
| `binance_funding_rate_8h:z` | entry record | 1299 | 0 | 1299 / 1284 / 1282 | 13 Sep 11:01 – 15 Sep 10:42 |
| `hl_open_interest_4h_pct:raw` | feature store | 3195 | 18 | 3177 / 3163 / 3161 | 08 Sep 13:40 – 15 Sep 10:42 |
| `hl_open_interest_4h_pct:z` | feature store | 3167 | 0 | 3167 / 3153 / 3151 | 08 Sep 15:28 – 15 Sep 10:42 |
| `hl_open_interest_4h_pct:with_price` | feature store | 3063 | 29 | 3034 / 3034 / 3034 | 08 Sep 13:52 – 15 Sep 06:22 |
| `binance_open_interest_usd:change_4h` | feature store | 1155 | 0 | 1155 / 1147 / 1145 | 13 Sep 15:51 – 15 Sep 10:20 |
| `binance_open_interest_usd:change_4h_with_price` | feature store | 1126 | 4 | 1122 / 1122 / 1122 | 13 Sep 15:51 – 15 Sep 06:22 |
| `binance_open_interest_usd:z` | feature store | 1427 | 1 | 1426 / 1411 / 1409 | 13 Sep 10:45 – 15 Sep 10:42 |
| `liq_map_skew_3pct:raw` | entry record | 600 | 4 | 596 / 581 / 576 | 14 Sep 18:34 – 15 Sep 10:42 |
| `liq_map_skew_3pct:z` | entry record | 437 | 5 | 432 / 417 / 412 | 14 Sep 21:49 – 15 Sep 10:42 |
| `cex_liquidations_net_1h_usd:raw` | feature store | 616 | 24 | 592 / 577 / 575 | 14 Sep 17:41 – 15 Sep 10:42 |
| `cex_liquidations_net_1h_usd:z` | feature store | 593 | 7 | 586 / 571 / 566 | 14 Sep 18:42 – 15 Sep 10:42 |
| `hl_oracle_premium_bps:raw` | feature store | 3190 | 63 | 3127 / 3113 / 3111 | 08 Sep 13:40 – 15 Sep 10:42 |
| `hl_oracle_premium_bps:z` | feature store | 3162 | 0 | 3162 / 3148 / 3146 | 08 Sep 15:28 – 15 Sep 10:42 |

### Every cell

| Reading | h | Calls | Indep. pooled (per symbol) | Hit as read | Up-share | Chance as read | Skill as read / inverted | z as read / inverted | Holm-positive | Hold-out skill as read / inverted (n) | Net after costs as read / inverted | Verdict |
|---|---:|---:|---|---:|---:|---:|---|---|---|---|---|---|
| `hl_funding_hourly_rate:raw` | 15 | 3235 | 422 (2194) | 48.3% | 48.2% | 48.8% | -0.005 / -0.009 | -0.19 / -0.35 | none | -0.000 / -0.011 (971) | -0.122% / -0.118% | not earned: S C |
| `hl_funding_hourly_rate:raw` | 60 | 3232 | 115 (651) | 46.6% | 47.6% | 48.3% | -0.017 / +0.012 | -0.37 / +0.26 | none | -0.005 / +0.002 (970) | -0.164% / -0.076% | not earned: W S C |
| `hl_funding_hourly_rate:raw` | 240 | 3227 | 33 (204) | 39.3% | 40.3% | 43.3% | -0.040 / +0.038 | -0.46 / +0.44 | none | +0.000 / -0.001 (969) | -0.317% / +0.077% | not earned: W S |
| `hl_funding_hourly_rate:z` | 15 | 2794 | 320 (1914) | 48.8% | 47.9% | 49.5% | -0.007 / -0.007 | -0.25 / -0.25 | none | -0.009 / -0.003 (839) | -0.112% / -0.128% | not earned: S C |
| `hl_funding_hourly_rate:z` | 60 | 2791 | 89 (574) | 47.0% | 46.1% | 49.1% | -0.021 / +0.014 | -0.39 / +0.27 | none | -0.017 / +0.014 (838) | -0.135% / -0.105% | not earned: W S C |
| `hl_funding_hourly_rate:z` | 240 | 2786 | 26 (183) | 42.3% | 39.2% | 47.4% | -0.051 / +0.049 | -0.53 / +0.50 | none | +0.032 / -0.033 (836) | -0.249% / +0.009% | not earned: W S |
| `hl_funding_apr_24h:raw` | 15 | 3191 | 413 (2168) | 48.2% | 48.3% | 48.7% | -0.005 / -0.009 | -0.18 / -0.36 | none | -0.003 / -0.009 (958) | -0.122% / -0.118% | not earned: S C |
| `hl_funding_apr_24h:raw` | 60 | 3176 | 112 (640) | 47.0% | 47.4% | 48.0% | -0.011 / +0.005 | -0.22 / +0.10 | none | -0.012 / +0.009 (953) | -0.161% / -0.079% | not earned: W S C |
| `hl_funding_apr_24h:raw` | 240 | 3176 | 32 (199) | 39.2% | 40.2% | 42.5% | -0.033 / +0.031 | -0.37 / +0.35 | none | -0.010 / +0.009 (953) | -0.361% / +0.121% | not earned: W S |
| `hl_funding_apr_24h:z` | 15 | 2810 | 372 (1902) | 50.0% | 48.2% | 49.7% | +0.004 / -0.017 | +0.14 / -0.65 | none | +0.018 / -0.031 (843) | -0.109% / -0.131% | not earned: S C |
| `hl_funding_apr_24h:z` | 60 | 2795 | 101 (560) | 50.7% | 47.2% | 49.5% | +0.012 / -0.018 | +0.24 / -0.35 | none | +0.027 / -0.031 (839) | -0.091% / -0.149% | not earned: W S C |
| `hl_funding_apr_24h:z` | 240 | 2795 | 30 (173) | 47.5% | 38.7% | 47.9% | -0.004 / +0.002 | -0.04 / +0.02 | none | +0.061 / -0.063 (839) | -0.163% / -0.077% | not earned: W S C |
| `funding_spread_vs_binance_bps:raw` | 15 | 2035 | 204 (1431) | 47.4% | 48.1% | 48.8% | -0.014 / -0.002 | -0.39 / -0.04 | none | -0.011 / -0.003 (611) | -0.125% / -0.115% | not earned: W S C |
| `funding_spread_vs_binance_bps:raw` | 60 | 2020 | 57 (439) | 47.4% | 46.9% | 48.1% | -0.007 / +0.001 | -0.10 / +0.01 | none | +0.003 / -0.006 (606) | -0.156% / -0.084% | not earned: W S C |
| `funding_spread_vs_binance_bps:raw` | 240 | 2018 | 18 (151) | 42.2% | 38.2% | 42.6% | -0.005 / +0.003 | -0.04 / +0.03 | none | +0.023 / -0.023 (606) | -0.247% / +0.007% | not earned: W S |
| `funding_spread_vs_binance_bps:z` | 15 | 1378 | 130 (960) | 49.1% | 49.9% | 50.0% | -0.009 / -0.001 | -0.22 / -0.02 | none | -0.015 / +0.006 (414) | -0.123% / -0.117% | not earned: W S C |
| `funding_spread_vs_binance_bps:z` | 60 | 1363 | 37 (290) | 49.2% | 50.5% | 50.0% | -0.007 / +0.005 | -0.09 / +0.06 | none | -0.017 / +0.012 (409) | -0.164% / -0.076% | not earned: W S C |
| `funding_spread_vs_binance_bps:z` | 240 | 1361 | 11 (94) | 54.4% | 40.2% | 50.5% | +0.040 / -0.041 | +0.26 / -0.27 | none | -0.001 / +0.001 (409) | +0.034% / -0.274% | not earned: W S |
| `binance_funding_rate_8h:raw` | 15 | 2276 | 205 (1592) | 47.4% | 47.9% | 48.9% | -0.015 / +0.001 | -0.44 / +0.02 | none | +0.006 / -0.013 (683) | -0.128% / -0.112% | not earned: W S C |
| `binance_funding_rate_8h:raw` | 60 | 2261 | 57 (483) | 46.8% | 46.6% | 48.2% | -0.013 / +0.008 | -0.20 / +0.12 | none | +0.003 / -0.006 (679) | -0.169% / -0.071% | not earned: W S C |
| `binance_funding_rate_8h:raw` | 240 | 2259 | 18 (157) | 41.0% | 37.8% | 43.4% | -0.024 / +0.022 | -0.20 / +0.19 | none | -0.004 / +0.004 (678) | -0.328% / +0.088% | not earned: W S |
| `binance_funding_rate_8h:z` | 15 | 1299 | 129 (902) | 47.1% | 50.6% | 50.0% | -0.029 / +0.018 | -0.66 / +0.42 | none | -0.051 / +0.040 (390) | -0.138% / -0.102% | not earned: W S C |
| `binance_funding_rate_8h:z` | 60 | 1284 | 37 (273) | 51.0% | 51.3% | 50.1% | +0.009 / -0.012 | +0.11 / -0.14 | none | -0.021 / +0.018 (386) | -0.109% / -0.131% | not earned: W S C |
| `binance_funding_rate_8h:z` | 240 | 1282 | 11 (90) | 47.1% | 41.2% | 49.4% | -0.023 / +0.022 | -0.15 / +0.15 | none | -0.012 / +0.012 (385) | -0.273% / +0.033% | not earned: W S |
| `hl_open_interest_4h_pct:raw` | 15 | 3177 | 419 (2154) | 49.2% | 48.3% | 50.1% | -0.009 / -0.005 | -0.35 / -0.19 | none | +0.040 / -0.051 (954) | -0.120% / -0.120% | not earned: S C |
| `hl_open_interest_4h_pct:raw` | 60 | 3163 | 114 (645) | 48.9% | 47.5% | 50.1% | -0.012 / +0.006 | -0.26 / +0.14 | none | +0.069 / -0.072 (949) | -0.126% / -0.114% | not earned: W S C |
| `hl_open_interest_4h_pct:raw` | 240 | 3161 | 33 (202) | 49.4% | 40.4% | 50.5% | -0.011 / +0.009 | -0.13 / +0.10 | none | +0.173 / -0.174 (949) | -0.126% / -0.114% | not earned: W S C |
| `hl_open_interest_4h_pct:z` | 15 | 3167 | 413 (2146) | 50.5% | 48.1% | 49.9% | +0.005 / -0.018 | +0.21 / -0.75 | none | +0.034 / -0.045 (951) | -0.113% / -0.127% | not earned: S C |
| `hl_open_interest_4h_pct:z` | 60 | 3153 | 113 (640) | 50.7% | 47.1% | 49.9% | +0.007 / -0.013 | +0.16 / -0.28 | none | +0.080 / -0.083 (946) | -0.091% / -0.149% | not earned: W S C |
| `hl_open_interest_4h_pct:z` | 240 | 3151 | 33 (202) | 50.3% | 40.1% | 49.7% | +0.006 / -0.008 | +0.07 / -0.09 | none | +0.153 / -0.154 (946) | -0.052% / -0.188% | not earned: W S C |
| `hl_open_interest_4h_pct:with_price` | 15 | 3034 | 398 (2074) | 49.2% | 48.0% | 49.5% | -0.003 / -0.011 | -0.10 / -0.42 | none | +0.001 / -0.010 (911) | -0.113% / -0.127% | not earned: S C |
| `hl_open_interest_4h_pct:with_price` | 60 | 3034 | 109 (629) | 49.1% | 47.1% | 49.3% | -0.002 / -0.004 | -0.04 / -0.08 | none | +0.032 / -0.035 (911) | -0.133% / -0.107% | not earned: W S C |
| `hl_open_interest_4h_pct:with_price` | 240 | 3034 | 31 (197) | 46.7% | 39.9% | 47.4% | -0.007 / +0.005 | -0.08 / +0.06 | none | -0.000 / -0.001 (911) | -0.153% / -0.087% | not earned: W S C |
| `binance_open_interest_usd:change_4h` | 15 | 1155 | 101 (812) | 50.6% | 47.7% | 50.5% | +0.001 / -0.013 | +0.03 / -0.25 | none | -0.033 / +0.024 (347) | -0.116% / -0.124% | not earned: W S C |
| `binance_open_interest_usd:change_4h` | 60 | 1147 | 29 (249) | 54.4% | 48.2% | 50.4% | +0.040 / -0.044 | +0.43 / -0.47 | none | -0.031 / +0.026 (345) | -0.087% / -0.153% | not earned: W S C |
| `binance_open_interest_usd:change_4h` | 240 | 1145 | 9 (87) | 59.5% | 40.7% | 52.1% | +0.074 / -0.075 | +0.45 / -0.45 | none | +0.047 / -0.047 (344) | -0.099% / -0.141% | not earned: W S C |
| `binance_open_interest_usd:change_4h_with_price` | 15 | 1122 | 97 (794) | 48.3% | 47.8% | 49.3% | -0.010 / -0.001 | -0.20 / -0.02 | none | +0.061 / -0.067 (337) | -0.105% / -0.135% | not earned: W S C |
| `binance_open_interest_usd:change_4h_with_price` | 60 | 1122 | 28 (245) | 50.1% | 48.3% | 49.5% | +0.006 / -0.010 | +0.07 / -0.10 | none | +0.027 / -0.033 (337) | -0.087% / -0.153% | not earned: W S C |
| `binance_open_interest_usd:change_4h_with_price` | 240 | 1122 | 9 (86) | 48.6% | 40.3% | 46.9% | +0.016 / -0.017 | +0.10 / -0.10 | none | -0.037 / +0.037 (337) | +0.009% / -0.249% | not earned: W S |
| `binance_open_interest_usd:z` | 15 | 1426 | 129 (991) | 53.2% | 49.3% | 50.0% | +0.031 / -0.041 | +0.71 / -0.93 | none | +0.010 / -0.019 (428) | -0.100% / -0.140% | not earned: W S C |
| `binance_open_interest_usd:z` | 60 | 1411 | 37 (298) | 55.5% | 49.4% | 50.0% | +0.055 / -0.057 | +0.66 / -0.70 | none | -0.036 / +0.031 (424) | -0.060% / -0.180% | not earned: W S C |
| `binance_open_interest_usd:z` | 240 | 1409 | 11 (95) | 57.1% | 38.6% | 50.5% | +0.066 / -0.066 | +0.43 / -0.44 | none | -0.007 / +0.007 (423) | -0.133% / -0.107% | not earned: W S C |
| `liq_map_skew_3pct:raw` | 15 | 596 | 49 (403) | 51.2% | 41.4% | 52.6% | -0.014 / +0.007 | -0.19 / +0.10 | none | -0.018 / +0.001 (179) | -0.119% / -0.121% | not earned: W S C |
| `liq_map_skew_3pct:raw` | 60 | 581 | 13 (113) | 51.3% | 34.8% | 54.3% | -0.030 / +0.026 | -0.22 / +0.19 | none | +0.007 / -0.013 (175) | -0.144% / -0.096% | not earned: W S C |
| `liq_map_skew_3pct:raw` | 240 | 576 | 3 (30) | 58.5% | 7.6% | 61.6% | -0.031 / +0.031 | -0.11 / +0.11 | none | +0.004 / -0.004 (173) | -0.084% / -0.156% | not earned: W S C |
| `liq_map_skew_3pct:z` | 15 | 432 | 37 (291) | 56.2% | 40.7% | 57.2% | -0.010 / +0.003 | -0.12 / +0.03 | none | -0.036 / +0.020 (130) | -0.115% / -0.125% | not earned: W S C |
| `liq_map_skew_3pct:z` | 60 | 417 | 10 (83) | 60.4% | 32.4% | 63.6% | -0.031 / +0.027 | -0.20 / +0.17 | none | -0.051 / +0.051 (126) | -0.037% / -0.203% | not earned: W S C |
| `liq_map_skew_3pct:z` | 240 | 412 | 3 (28) | 82.8% | 8.5% | 81.8% | +0.009 / -0.009 | +0.03 / -0.03 | none | +0.016 / -0.016 (124) | +0.540% / -0.780% | not earned: W S |
| `cex_liquidations_net_1h_usd:raw` | 15 | 592 | 51 (397) | 45.1% | 42.6% | 47.8% | -0.027 / +0.021 | -0.39 / +0.29 | none | +0.008 / -0.025 (178) | -0.110% / -0.130% | not earned: W S C |
| `cex_liquidations_net_1h_usd:raw` | 60 | 577 | 14 (113) | 41.6% | 35.9% | 45.4% | -0.038 / +0.035 | -0.29 / +0.26 | none | -0.002 / -0.003 (174) | -0.163% / -0.077% | not earned: W S C |
| `cex_liquidations_net_1h_usd:raw` | 240 | 575 | 4 (33) | 36.2% | 8.5% | 36.4% | -0.002 / +0.002 | -0.01 / +0.01 | none | -0.014 / +0.014 (173) | -0.257% / +0.017% | not earned: W S |
| `cex_liquidations_net_1h_usd:z` | 15 | 586 | 49 (395) | 49.1% | 41.3% | 49.5% | -0.003 / -0.004 | -0.04 / -0.05 | none | +0.031 / -0.048 (176) | -0.067% / -0.173% | not earned: W S C |
| `cex_liquidations_net_1h_usd:z` | 60 | 571 | 13 (112) | 51.0% | 35.2% | 48.7% | +0.023 / -0.026 | +0.16 / -0.19 | none | +0.068 / -0.074 (172) | +0.001% / -0.241% | not earned: W S |
| `cex_liquidations_net_1h_usd:z` | 240 | 566 | 3 (30) | 48.9% | 7.8% | 45.8% | +0.031 / -0.031 | +0.11 / -0.11 | none | +0.040 / -0.040 (170) | -0.095% / -0.145% | not earned: W S C |
| `hl_oracle_premium_bps:raw` | 15 | 3127 | 420 (2122) | 50.6% | 48.4% | 51.4% | -0.008 / -0.005 | -0.32 / -0.22 | none | +0.009 / -0.020 (939) | -0.111% / -0.129% | not earned: S C |
| `hl_oracle_premium_bps:raw` | 60 | 3113 | 114 (638) | 52.0% | 47.6% | 52.1% | -0.001 / -0.005 | -0.02 / -0.11 | none | +0.030 / -0.033 (934) | -0.084% / -0.156% | not earned: W S C |
| `hl_oracle_premium_bps:raw` | 240 | 3111 | 33 (201) | 56.2% | 40.5% | 58.0% | -0.018 / +0.016 | -0.21 / +0.19 | none | -0.010 / +0.009 (934) | -0.008% / -0.232% | not earned: W S C |
| `hl_oracle_premium_bps:z` | 15 | 3162 | 413 (2142) | 49.1% | 48.1% | 49.9% | -0.008 / -0.005 | -0.33 / -0.21 | none | +0.037 / -0.048 (949) | -0.114% / -0.126% | not earned: S C |
| `hl_oracle_premium_bps:z` | 60 | 3148 | 113 (640) | 50.6% | 47.2% | 49.8% | +0.008 / -0.014 | +0.17 / -0.29 | none | +0.057 / -0.060 (945) | -0.101% / -0.139% | not earned: W S C |
| `hl_oracle_premium_bps:z` | 240 | 3146 | 33 (202) | 47.4% | 40.2% | 49.4% | -0.020 / +0.018 | -0.23 / +0.21 | none | +0.055 / -0.056 (944) | -0.114% / -0.126% | not earned: W S C |

### Per candidate

Reason codes: W too few independent windows, S no positive skill, H failed hold-out, C negative after costs, 0 no calls. Shown for the better polarity of each reading.

| Candidate | 15m | 60m | 240m | Admitted | Most independent windows in a cell (pooled) | Soonest more days, s = 0.10 / 0.05 |
|---|---|---|---|---|---:|---|
| `hl_funding_hourly_rate` | C S (best z -0.19) | C S W (best z +0.27) | S W (best z +0.50) | no | 422 | 0 (15m) / 13 (15m) |
| `hl_funding_apr_24h` | C S (best z +0.14) | C S W (best z +0.24) | C S W (best z +0.35) | no | 413 | 0 (15m) / 14 (15m) |
| `funding_spread_vs_binance_bps` | C S W (best z -0.02) | C S W (best z +0.06) | S W (best z +0.26) | no | 204 | 2 (15m) / 16 (15m) |
| `binance_funding_rate_8h` | C S W (best z +0.42) | C S W (best z +0.12) | S W (best z +0.19) | no | 205 | 2 (15m) / 16 (15m) |
| `hl_open_interest_4h_pct` | C S (best z +0.21) | C S W (best z +0.16) | C S W (best z +0.10) | no | 419 | 0 (15m) / 14 (15m) |
| `binance_open_interest_usd` | C S W (best z +0.71) | C S W (best z +0.66) | C S W (best z +0.45) | no | 129 | 3 (15m) / 17 (15m) |
| `liq_map_skew_3pct` | C S W (best z +0.10) | C S W (best z +0.19) | C S W (best z +0.11) | no | 49 | 4 (15m) / 16 (15m) |
| `cex_liquidations_net_1h_usd` | C S W (best z +0.29) | C S W (best z +0.26) | C S W (best z +0.11) | no | 51 | 4 (15m) / 16 (15m) |
| `hl_oracle_premium_bps` | C S (best z -0.21) | C S W (best z +0.17) | C S W (best z +0.21) | no | 420 | 0 (15m) / 14 (15m) |

### What this does not show

- **Power was limited.** Over two to seven days the tests could only detect large edges, mostly at
  15 minutes. Failing to earn is not proof that a candidate carries no information.
- **Other variants were not tested.** Combinations beyond the two declared open-interest-with-price
  products, regime-conditioned readings and other lookbacks were left out. Testing any of them later
  is a new declaration and a new family, paying its own adjustment.
- **The more-data estimates are optimistic.** They assume the current rate of pooled independent
  windows and the worst-case binomial error at the first Holm rank. The bootstrap error (used when
  larger) and lower Holm ranks both need more.
- **Re-runs need a schedule.** Repeating this run every few days until something passes is optional
  stopping and would need its own correction. Schedule one re-run at a fixed date.
