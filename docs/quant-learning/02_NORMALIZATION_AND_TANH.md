# Chapter 2 — Normalization, Z-Scores, and `tanh`

## The problem normalization solves

Market inputs use incompatible units:

- return may be a percentage;
- order-book depth may be dollars;
- spread may be basis points;
- ETF flow may be millions of dollars;
- funding may be a small decimal rate.

Adding those raw values would be meaningless. Normalization converts them into comparable scores while retaining sign and relative magnitude.

## Step 1: define the measurement and history

Suppose `x_t` is the current value of one measurement. Before calculating anything, the rulebook must define:

- source and field;
- timeframe;
- lookback window;
- sampling interval;
- missing-data treatment;
- outlier treatment;
- whether the window excludes the current observation.

These choices prevent look-ahead bias and make the calculation reproducible.

## Step 2: calculate a z-score

```text
z_t = (x_t - μ) / σ
```

Example:

```text
current premium x_t = 8 bps
historical mean μ = 2 bps
historical standard deviation σ = 3 bps

z_t = (8 - 2) / 3
z_t = 2
```

The current premium is two standard deviations above the chosen historical mean.

Important: the z-score describes unusualness relative to the selected history. It does not prove the data is normally distributed, and it does not itself predict price direction.

## Step 3: compress the z-score

The exact TradeSync Book 1 formula is:

```text
s_t = tanh(z_t / 2)
```

This is **not**:

```text
tan(z_t) / 2
```

`tan` is the trigonometric tangent function. `tanh` is the **hyperbolic tangent** function. They have different definitions and behavior.

## What `tanh` means

For an input `u`:

```text
tanh(u) = (e^u - e^(-u)) / (e^u + e^(-u))
```

Read the symbols as:

- `e`: Euler's number, approximately `2.71828`;
- `e^u`: `e` raised to the power `u`;
- `e^(-u)`: `e` raised to the negative power `u`.

The denominator is always positive and larger in magnitude than the numerator. Therefore the result cannot reach or pass `-1` or `1` for any finite input.

Properties useful to TradeSync:

- `tanh(0) = 0`;
- positive inputs produce positive outputs;
- negative inputs produce negative outputs;
- `tanh(-u) = -tanh(u)`, so it is symmetric;
- extreme inputs approach the bounds gradually instead of dominating without limit.

## Where did the `/ 2` come from?

It was selected, not discovered as a universal market law.

The general design is:

```text
s_t = tanh(z_t / k)
```

`k` is a positive **compression constant**. Book 1 sets `k = 2`.

- smaller `k`: scores approach `-1` and `1` faster, so moderate z-scores look more extreme;
- larger `k`: scores stay nearer zero, so the engine is more conservative;
- `k = 2`: a provisional, readable starting point for paper experiments.

Because `k` changes behavior, it is stored in the versioned rulebook. It must later be calibrated on out-of-sample paper data, not changed until a chart “looks right.”

## Numeric examples

| `z_t` | calculation | `s_t`, approximately | meaning |
|---:|---|---:|---|
| `-3` | `tanh(-3 / 2)` | `-0.905` | strongly below history |
| `-2` | `tanh(-2 / 2)` | `-0.762` | materially below history |
| `-1` | `tanh(-1 / 2)` | `-0.462` | moderately below history |
| `0` | `tanh(0 / 2)` | `0.000` | at the mean |
| `1` | `tanh(1 / 2)` | `0.462` | moderately above history |
| `2` | `tanh(2 / 2)` | `0.762` | materially above history |
| `3` | `tanh(3 / 2)` | `0.905` | strongly above history |

Mathematically, the output is strictly inside `(-1, 1)`. Documentation often says “between `-1` and `1`” for convenience, but finite real-number inputs do not produce the exact endpoints. Computers use finite-precision floating-point arithmetic and can round a very extreme result to exactly `-1` or `1`; the Book 1 function explicitly moves that rounded value one machine step back inside the interval.

## Why not simply clip?

Clipping could use `s = max(-1, min(1, z))`. That has a sharp boundary: every `z >= 1` becomes exactly `1`, losing the difference between moderately and extremely unusual values. `tanh` changes smoothly and keeps some ordering among extremes.

This does not make `tanh` automatically best. It makes it a plausible candidate with explainable properties. Later experiments compare calibration choices using fixed data windows and guardrails.

## Robust alternative: median and MAD

Market data can contain outliers. A robust z-score can use the median and median absolute deviation (`MAD`):

```text
median = middle value after sorting
MAD = median(abs(x_i - median))
robust_z_t = (x_t - median) / (1.4826 * MAD)
```

`abs` means absolute value: distance from zero without a sign. The constant `1.4826` makes `MAD` comparable with standard deviation when data follows a normal distribution. It is not an arbitrary trading weight.

TradeSync Book 1 implements ordinary `z -> tanh(z / k)` compression but does not yet calculate rolling z-scores from live history. Ordinary versus robust estimation is a later champion/challenger experiment.

## Guardrails

- A normalized score never becomes approval authority.
- A missing standard deviation or `σ = 0` must return unavailable, not divide by zero.
- Every stored score includes its lookback, source lineage, rulebook version, and digest.
- News/event severity cannot manufacture a directional sign; market blocks must confirm direction.
- Transformation changes the scale, not the truth status of the underlying source.
