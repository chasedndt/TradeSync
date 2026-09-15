# Evidence combination — appendix: live tables, reproduction, exercise answers

Companion to [the design](2026-09-15_evidence-combination.md). Figures are from the local, read-only run
of 15 September 2026 at 01:19 UTC (method digest `96539f87…51e6`); the deployed endpoint returns the
same fields.

## Sources at every horizon

LR with its 95% interval; "eff" is effective fitting windows; C marks a regime-conditioned ratio (up call
shown); weight is the mean share of face value kept on test decisions.

### 15 minutes (fit 2,046 decisions, 273.4 effective windows)

| Source | Calls · eff | Up call | Down call | Regimes | Test calls · weight |
|---|---|---|---|---|---|
| hl_return_1h_pct | 1,951 · 262.8 | 1.076 (0.845–1.371) | 0.935 (0.747–1.169) | falling C 1.260, rising C 1.020 | 835 · 0.77 |
| hl_direct_cvd | 1,966 · 263.0 | 0.994 (0.788–1.255) | 1.006 (0.798–1.268) | falling C 1.020, rising C 0.979 | 871 · 0.76 |
| coinbase_premium_bps | 1,215 · 300.1 | 0.989 (0.884–1.106) | 1.043 (0.680–1.598) | falling C 1.031, rising C 0.947 | 306 · 0.73 |
| binance_funding_rate_8h | 1,020 · 94.4 | 0.937 (0.753–1.167) | 1.197 (0.652–2.198) | falling C 0.928, rising C 0.927 | 877 · 0.81 |
| funding_spread_vs_binance_bps | 998 · 94.0 | 0.988 (0.806–1.210) | 1.040 (0.542–1.997) | falling C 1.010, rising C 0.955 | 696 · 0.79 |
| gdelt_news_tone | 49 · 20.5 | 0.655 (0.255–1.685); plain 0.363 | 1.205 (0.805–1.804) | none | 0 |
| hl_resting_liquidity_imbalance | 0 | — | — | — | 256, contributes nothing |
| liq_map_skew_3pct | 0 | — | — | — | 252, contributes nothing |

### 1 hour (fit 2,219 decisions, 61.6 effective windows)

| Source | Calls · eff | Up call | Down call | Regimes | Test calls · weight |
|---|---|---|---|---|---|
| hl_return_1h_pct | 2,123 · 59.0 | 0.992 (0.638–1.542) | 1.008 (0.655–1.549) | falling C 1.025, rising C 0.990 | 925 · 0.46 |
| hl_direct_cvd | 1,861 · 70.0 | 0.982 (0.652–1.480) | 1.018 (0.677–1.531) | falling C 1.044, rising C 0.929 | 961 · 0.64 |
| coinbase_premium_bps | 1,190 · 80.6 | 1.009 (0.830–1.225) | 0.966 (0.447–2.091) | falling C 1.025, rising C 1.001 | 336 · 0.54 |
| binance_funding_rate_8h | 911 · 23.2 | 0.956 (0.688–1.329) | 1.153 (0.408–3.259) | none (falling 19.99 eff) | 967 · 0.61 |
| funding_spread_vs_binance_bps | 890 · 23.3 | 0.981 (0.701–1.373) | 1.060 (0.385–2.915) | none | 783 · 0.47 |
| gdelt_news_tone | 50 · 8.2 | 0.939 (0.349–2.525) | 1.034 (0.616–1.735) | none | 0 |
| hl_resting_liquidity_imbalance | 0 | — | — | — | 257, contributes nothing |
| liq_map_skew_3pct | 0 | — | — | — | 253, contributes nothing |

### 4 hours (fit 2,148 decisions, 18.2 effective windows)

| Source | Calls · eff | Up call | Down call | Regimes | Test calls · weight |
|---|---|---|---|---|---|
| hl_return_1h_pct | 2,065 · 17.6 | 0.895 (0.466–1.718) | 1.111 (0.605–2.039) | none | 893 · 0.58 |
| hl_direct_cvd | 1,790 · 18.1 | 0.973 (0.517–1.830) | 1.027 (0.557–1.893) | none | 929 · 0.33 |
| coinbase_premium_bps | 1,161 · 20.9 | 1.061 (0.782–1.441) | 0.795 (0.242–2.611) | none | 324 · 0.56 |
| binance_funding_rate_8h | 836 · 5.6 | 0.974 (0.627–1.513) | 1.079 (0.303–3.849) | none | 935 · 0.32 |
| funding_spread_vs_binance_bps | 815 · 5.6 | 0.974 (0.605–1.567) | 1.068 (0.330–3.462) | none | 795 · 0.30 |
| gdelt_news_tone | 50 · 6.1 | 1.111 (0.409–3.013) | 0.944 (0.540–1.648) | none | 0 |
| hl_resting_liquidity_imbalance | 0 | — | — | — | 138, contributes nothing |
| liq_map_skew_3pct | 0 | — | — | — | 134, contributes nothing |

## Dependence pairs at 1 hour

Residual correlation of calls within outcome classes, polarity product, and the value shrunk toward
redundancy with 20 prior windows (redundancy is that value floored at 0).

| Pair | Shared decisions · eff | Residual ρ | Polarity | Shrunk |
|---|---|---|---|---|
| coinbase_premium_bps ~ gdelt_news_tone | 26 · 6.5 | −0.374 | −1 | 0.846 |
| gdelt_news_tone ~ hl_return_1h_pct | 44 · 7.6 | +0.044 | +1 | 0.738 |
| gdelt_news_tone ~ hl_direct_cvd | 49 · 7.9 | +0.070 | +1 | 0.737 |
| binance_funding_rate_8h ~ gdelt_news_tone | 50 · 8.2 | none (a call never varied within an outcome on the shared windows) | +1 | 0.710 |
| funding_spread_vs_binance_bps ~ gdelt_news_tone | 49 · 8.0 | −0.197 | +1 | 0.659 |
| coinbase_premium_bps ~ funding_spread_vs_binance_bps | 285 · 23.9 | −0.176 | −1 | 0.552 |
| funding_spread_vs_binance_bps ~ hl_return_1h_pct | 840 · 22.3 | +0.073 | +1 | 0.512 |
| binance_funding_rate_8h ~ hl_return_1h_pct | 860 · 22.2 | +0.009 | +1 | 0.478 |
| binance_funding_rate_8h ~ hl_direct_cvd | 894 · 23.2 | −0.011 | +1 | 0.457 |
| funding_spread_vs_binance_bps ~ hl_direct_cvd | 874 · 23.2 | −0.035 | +1 | 0.444 |
| binance_funding_rate_8h ~ funding_spread_vs_binance_bps | 890 · 23.3 | −0.157 | +1 | 0.378 |
| binance_funding_rate_8h ~ coinbase_premium_bps | 289 · 23.8 | +0.149 | −1 | 0.375 |
| hl_direct_cvd ~ hl_return_1h_pct | 1,798 · 67.7 | +0.072 | +1 | 0.283 |
| coinbase_premium_bps ~ hl_return_1h_pct | 1,117 · 77.0 | −0.033 | −1 | 0.232 |
| coinbase_premium_bps ~ hl_direct_cvd | 1,171 · 80.2 | +0.087 | −1 | 0.130 |

At 15 minutes the most redundant well-measured pair was binance_funding_rate_8h ~ coinbase_premium_bps
(+0.248 over 86.0 shared effective windows, shrunk 0.390); hl_direct_cvd ~ hl_return_1h_pct measured
+0.082 over 253.3 but with opposite polarities, shrunk −0.003, redundancy 0. At 4 hours every pair had
between 4 and 21 shared effective windows and shrunk values of 0.45 to 0.83.

## Other comparisons

| Horizon | Candidate − baseline | Brier | Log loss |
|---|---|---|---|
| 15 min | combined − base rate | +0.0011 (−0.0060 to +0.0082) | +0.0022 (−0.0121 to +0.0165) |
| | combined − rulebook | +0.0013 (−0.0059 to +0.0085) | +0.0026 (−0.0119 to +0.0171) |
| | independent − combined | +0.0005 (−0.0011 to +0.0020) | +0.0009 (−0.0022 to +0.0041) |
| 1 hour | combined − base rate | +0.0002 (−0.0076 to +0.0079) | +0.0004 (−0.0152 to +0.0159) |
| | combined − rulebook | −0.0022 (−0.0180 to +0.0136) | −0.0044 (−0.0360 to +0.0272) |
| | independent − combined | +0.0003 (−0.0038 to +0.0044) | +0.0006 (−0.0076 to +0.0089) |
| 4 hours | combined − base rate | +0.0032 (−0.0160 to +0.0223) | +0.0071 (−0.0349 to +0.0491) |
| | combined − rulebook | +0.0135 (−0.0292 to +0.0562) | +0.0289 (−0.0625 to +0.1202) |
| | independent − combined | +0.0023 (−0.0124 to +0.0170) | +0.0056 (−0.0274 to +0.0387) |

Every row is not distinguishable.

**Rulebook calibration:** 15 min a = −0.0387, b = +0.0793 (2,046 scored, 273.4 eff); 1 hour a = −0.1390,
b = −0.0734 (1,996 scored, 75.7 eff); 4 hours a = −0.3787, b = +0.0444 (1,925 scored, 19.6 eff). A brute-force
grid of the same penalised likelihood agreed with Newton's optimum (1 hour: grid a = −0.140, b = −0.070;
Newton's objective was the higher).

**Reliability bins of combined sources at 1 hour** (mean forecast → share that rose, 95% interval,
effective windows): 47.7% → 52.2% (31.4–72.3, 19.0); 48.5% → 51.0% (29.7–71.9, 17.7); 49.8% → 51.4%
(30.2–72.1, 18.0); 50.7% → 50.0% (27.6–72.4, 15.3); 52.8% → 53.1% (29.1–75.8, 13.7).

## Reproduction

Read-only, per horizon H in 15, 60 and 240, inside `BEGIN READ ONLY`: the two queries in
`services/state-api/app/evidence_combination.py` (`DECISIONS_SQL`, `READINGS_SQL`) with $1 = H and
$2 = 14, then `build_response(H, decision_rows, reading_rows, cost_pct=0.12, days=14)`. After deployment
the same body comes from `GET /state/research/evidence-combination?horizon=H`; the first call for a horizon
answers 202 while it is measured behind the request.

## Exercise answers

1. Plain: P(up | rose) = 45/60 = 0.75 and P(up | fell) = 30/60 = 0.50, so LR(up) = **1.5** and LR(down) =
   0.25/0.50 = **0.5**. Shrunk: m = 76/122 = 0.623; θ_R = (45 + 10 × 0.623)/70 = 0.7319; θ_F = (30 + 6.23)/70 =
   0.5176; LR(up) = **1.414**, LR(down) = 0.2681/0.4824 = **0.556**.
2. Odds 0.52/0.48 = 1.0833; × 1.2 × 1.3 = 1.69; p = 1.69/2.69 = **62.8%**.
3. Counted once: 1.0833 × 1.2 = 1.30; p = **56.5%**. Counting the copy would have given 60.9%.
4. No. LR 0.8 makes an up call evidence for a *fall*: the source is contrarian, and its down call will
   usually carry an LR above 1. A useless source has LR 1, not LR below 1.
5. A long must exceed (0.35 + 0.12)/0.60 = **78.3%**; a short must stay under (0.35 − 0.12)/0.60 = **38.3%**.
6. Brier (55 × 0.16 + 45 × 0.36)/100 = **0.25**; gap 60% − 55% = **5 points**; the Wilson 95% interval for
   55 of 100 is 45.2% to 64.4%, which holds 60%: **not detectable**.
7. The pooled ratio already contains that regime's windows. Shrinking toward it would use them twice and let
   the regime's ratio sit further from 1 than its own evidence supports.
