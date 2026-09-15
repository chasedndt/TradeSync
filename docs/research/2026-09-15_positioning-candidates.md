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

Pending: appended after the run.
