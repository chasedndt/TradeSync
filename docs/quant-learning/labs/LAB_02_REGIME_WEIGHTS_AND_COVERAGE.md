# Applied Lab 2 — Regime Weights and Coverage

## Year 2 connection

Primary topic: weighted averages in Mathematical Methods and descriptive
statistics in Probability and Statistics.

TradeSync application: compare an immutable baseline and a draft challenger
on exactly the same recorded decisions.

## Formula

```text
weighted score =
  sum(weight × data quality × block score)
  ------------------------------------------------
  sum(weight × data quality)
```

The capital Greek letter sigma, `Σ`, means “add every term in this set.” The
denominator re-scales the result when some evidence is missing.

Coverage is `sum(block weight × block data quality)`. It measures how much
requested evidence is usable. It is not the probability a trade wins.

## Operator exercise

1. Open `/regime-lab` and choose one Hyperliquid market.
2. Read the health strip and the feature table: which feeds are fresh, and why
   each feature is or is not scoring.
3. Write a falsifiable “if / then / because” hypothesis.
4. Change at least two weights while keeping each block at or below `0.40`.
5. Make all five weights sum to `1.00`.
6. Evaluate: replay a 24-hour or 7-day window of stored decisions.
7. Explain why admissions changed while directions did not.
8. Compare hit rate and skill only together with their sample counts.
9. Save the draft only when PostgreSQL is healthy.

## Hand calculation

```text
liquidity:   weight 0.30, quality 0.50, score -0.40
positioning: weight 0.20, quality 1.00, score  0.25

numerator   = (0.30 × 0.50 × -0.40) + (0.20 × 1.00 × 0.25)
            = -0.01
denominator = (0.30 × 0.50) + (0.20 × 1.00)
            = 0.35
score       = -0.01 / 0.35 = -0.02857
coverage    = 0.35 = 35%
```

## Completion boundary

Saving stores a draft and its replay judgement, not an activation. One replay
window cannot show a challenger is better in general; guardrails and operator
approval remain separate future gates.
