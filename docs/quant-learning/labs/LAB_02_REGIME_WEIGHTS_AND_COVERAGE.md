# Applied Lab 2 — Regime Weights and Coverage

## Year 2 connection

Primary topic: weighted averages in Mathematical Methods and descriptive
statistics in Probability and Statistics.

TradeSync application: compare an immutable baseline and a draft challenger
using exactly the same market evidence.

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
2. Record which features are admitted, collecting history, planned, or unavailable.
3. Write a falsifiable “if / then / because” hypothesis.
4. Change at least two weights while keeping each block at or below `0.40`.
5. Make all five weights sum to `1.00`.
6. Enter `1.0` for the arithmetic learning gate.
7. Explain in your own words why coverage is not win probability.
8. Evaluate the challenger.
9. Explain why score delta is not evidence of better trading performance.
10. Save the draft only when PostgreSQL is healthy.

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

Completing this lab makes a draft eligible for storage, not activation. Fixed
historical replay, outcome KPIs, guardrails, and operator approval remain
separate future gates.
