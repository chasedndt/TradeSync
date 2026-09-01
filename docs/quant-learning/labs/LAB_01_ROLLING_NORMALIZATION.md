# Applied Lab 1 — Rolling Normalization and Outliers

## Year 2 topic

This lab primarily uses **Probability and Statistics / Applied Statistics**:

- samples and populations;
- arithmetic mean;
- sample variance and sample standard deviation;
- median and median absolute deviation;
- z-scores;
- outliers and robust estimation.

It also uses **Mathematical Methods** when `tanh` transforms the z-score.

## Learning outcome

After the lab, you should be able to explain why the same current spread can appear ordinary under mean/standard-deviation normalization but extreme under median/MAD normalization when the history contains one large outlier.

## New term: rolling window

A rolling window is the most recent fixed number of past observations used for the next calculation.

For lookback `5` and observations:

```text
time:   1  2  3  4  5  6
value: 10 11 12 13 14 15
```

At time `6`, the five historical comparison values are observations `1..5`. The current value `15` is not included when calculating its own historical mean. After recording time `6`, the next evaluation can use observations `2..6`.

This is how we avoid letting future/current information leak into the comparison history.

## Why divide sample variance by `n - 1`?

When the history is treated as a sample from a wider process, using the same sample mean makes the observed spread slightly too small on average. Dividing by `n - 1` rather than `n` corrects that systematic underestimation. This is called Bessel's correction.

Book 1 does not require proving Bessel's correction yet. You must understand which formula the code uses and why a population and sample formula can differ.

## The TradeSync fixture

The fixture contains 20 previous spread observations. Most are around `0.47 bps`, but one is `4.8 bps`. The current spread is `0.9 bps`.

Run:

```powershell
$env:PYTHONPATH = "libs\tradesync_core"
python -m tradesync_core.market_features compare-methods `
  config\features\market-feature-catalog-v1.json `
  fixtures\features\spread-robust-normalization.json
```

### What ordinary statistics see

The `4.8 bps` outlier pulls the mean upward and makes the standard deviation much larger. That can make `0.9 bps` look relatively unexceptional.

Fixture output:

```text
mean = 0.6835
sample standard deviation = 0.969390883086
z = 0.223336121453
inverse liquidity score = -0.111206206458
```

### What robust statistics see

The median remains near the centre of the 19 ordinary observations. The MAD also remains small. The current `0.9 bps` is therefore very far above the robust historical centre.

Fixture output:

```text
median = 0.47
scaled MAD = 0.037065
robust z = 11.601241062997
inverse liquidity score = -0.999981690729
```

Because spread uses `inverse` score mode:

```text
wider-than-history spread -> positive normalized unusualness
inverse mode -> negative liquidity suitability score
```

The code is not saying “negative price direction.” It is saying “current liquidity suitability is worse.”

Robust is not automatically better. It resists the old outlier, but a very small MAD can make a new deviation look enormous and push `tanh` close to its limit. Ordinary and robust methods must therefore be compared on fixed paper data using outcome and stability guardrails. This fixture establishes the hypothesis; it does not promote robust normalization to a live strategy.

## Practice task A — ordinary z-score

Use history `2, 4, 6` and current value `8`.

1. Calculate the mean.
2. Subtract the mean from every historical value.
3. Square those differences.
4. Add them.
5. Divide by `n - 1`.
6. Take the square root to find sample standard deviation.
7. Calculate the current z-score.

Self-check:

```text
mean = 4
sample standard deviation = 2
z = (8 - 4) / 2 = 2
```

## Practice task B — robust z-score

Use history `1, 2, 3, 4, 5` and current value `6`.

1. Find the median.
2. Calculate each absolute distance from the median.
3. Find the median of those distances: MAD.
4. Multiply MAD by `1.4826`.
5. Calculate the robust z-score.

Self-check:

```text
median = 3
absolute distances = 2, 1, 0, 1, 2
MAD = 1
scaled MAD = 1.4826
robust z = (6 - 3) / 1.4826 ≈ 2.0235
```

## Practice task C — quality

The spread catalog requests 120 observations. The fixture provides 20. The current observation is completely fresh.

```text
sample_factor = 20 / 120 = 0.1667
freshness_factor = 1
data_quality = 0.1667 * 1 = 0.1667
```

Answer these in your own words:

1. Why can a calculation be mathematically valid but still have low data quality?
2. Why is `0.1667` not the probability that the signal is correct?
3. Why should a proxy liquidation estimate be blocked rather than given an invented quality multiplier?

## Completion evidence

Retain your written calculations, terminal output, and answers to the three quality questions. The next engineering gate—feature-to-block aggregation—should not be treated as understood until these distinctions are clear:

- raw value;
- historical centre;
- dispersion;
- normalized unusualness;
- score mode;
- data quality;
- provenance authority.
