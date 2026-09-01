# Chapter 1 — Mathematical Language and Notation

## Formula or equation?

An **equation** is any statement saying two expressions are equal. The equals sign, `=`, makes that claim.

```text
2 + 3 = 5
```

A **formula** is an equation used as a calculation rule. It tells us how to calculate one quantity from other quantities.

```text
average = sum of observations / number of observations
```

Therefore, `z_t = (x_t - μ) / σ` is both an equation and a formula. It is an equation because it contains `=`. It is a formula because we use it to calculate `z_t`.

An **expression** is a mathematical phrase without asserting equality. `tanh(z_t / 2)` is an expression. It becomes a formula when we write `s_t = tanh(z_t / 2)`.

## Read the symbols before calculating

### `t`

Read `t` as “time” or “time index.” It identifies which observation we mean.

If hourly Bitcoin funding observations are numbered in time:

```text
t = 1   first hour
t = 2   second hour
t = 3   third hour
```

In production, `t` normally corresponds to an actual timestamp such as `2026-09-01T16:00:00Z`.

### `x_t`

Read `x_t` as “x at time t.” The small `t` is a **subscript**. It is a label, not multiplication.

If `x` means Coinbase premium in basis points, then:

```text
x_t = Coinbase premium measured at the current observation time
```

The letter `x` is a general placeholder for a measured variable. In code, we use a descriptive name such as `coinbase_premium_bps`.

### `μ`

The symbol `μ` is the Greek letter **mu**, pronounced “mew.” It often represents the arithmetic mean, or ordinary average.

For observations `2, 4, 6`:

```text
μ = (2 + 4 + 6) / 3 = 4
```

It can resemble a curved lowercase `u`, but it is the Greek letter mu.

### `σ`

The symbol `σ` is the Greek lowercase letter **sigma**. It often represents standard deviation: a measure of how spread out observations are around their mean.

- small `σ`: observations usually remain close to the average;
- large `σ`: observations are more dispersed or volatile.

The exact population formula is:

```text
σ = square_root(sum((x_i - μ)^2) / N)
```

Read the new symbols as:

- `i`: the index of one observation;
- `x_i`: observation number `i`;
- `N`: total number of observations;
- `^2`: squared, meaning multiplied by itself;
- `square_root`: the non-negative value that produces the input when squared.

In market research we often estimate standard deviation from a sample and divide by `N - 1` instead of `N`. Book 1 uses the concept before that distinction; the practice chapter revisits it.

### `z_t`

Read `z_t` as “z-score at time t.” It tells us how unusual the current observation is compared with a selected history.

```text
z_t = (x_t - μ) / σ
```

Read it in words:

> current value minus historical average, divided by the historical standard deviation.

Interpretation:

- `z_t = 0`: the current value equals the historical average;
- `z_t = 1`: it is one standard deviation above average;
- `z_t = -2`: it is two standard deviations below average.

The sign gives direction relative to the average. The magnitude gives distance from the average in units of standard deviation.

### `s_t`

Read `s_t` as “bounded score at time t.” TradeSync uses it for the normalized output after compressing a z-score into a common range.

```text
s_t = tanh(z_t / 2)
```

The next chapter explains `tanh`, the division by `2`, and why this range is useful.

## Comparator

A **comparator** is the reference used to make a comparison. It is not automatically a specific company, exchange, or mathematical operator.

Examples:

- Coinbase BTC/USD compared with a broad BTC spot reference;
- Hyperliquid perpetual mid-price compared with a spot index;
- today's ETF flow compared with its 20-day history;
- a challenger weight set compared with the current champion weight set.

Every comparator must state:

1. the measured series;
2. the reference series;
3. timestamp alignment;
4. currency and unit;
5. what happens when either side is stale or missing.

Without those fields, “premium” is ambiguous.

## Basis points (`bps`)

`bps` means **basis points**. Basis points are a precise way to describe small percentage differences.

```text
1 basis point   = 0.01% = 0.0001 as a decimal
10 basis points = 0.10%
100 basis points = 1.00%
```

If a comparator price is `$100,000` and another price is `$100,050`:

```text
difference = 50
relative difference = 50 / 100,000 = 0.0005
percentage difference = 0.05%
premium = 5 bps
```

TradeSync does not invent what one basis point means. The unit is standard. TradeSync does define the exact comparator, timestamp tolerance, and threshold at which a premium becomes operationally meaningful. Those are versioned rulebook choices.

## Record

A **record** is one durable, structured account of something that happened or was configured. A row in PostgreSQL is a record.

A replayable regime-score record needs more than the final score. It includes:

- symbol and timeframe;
- observation timestamp;
- rulebook version and configuration digest;
- source event IDs;
- normalized block inputs;
- data-quality values;
- each weighted contribution;
- risk flags and the risk cap they applied;
- final score, coverage, and paper-risk multiplier.

This is stored in PostgreSQL because it is durable operational truth. Redis may distribute the active version and new score event, but Redis is not the permanent source of truth. The database can run in Docker while its named volume persists outside the life of an individual container.

## Book 1 notation dictionary

| Symbol | Name | Plain-English meaning | Unit or range |
|---|---|---|---|
| `t` | time index | which observation | timestamp/index |
| `x_t` | x at time t | current raw measurement | source unit |
| `μ` | mu | average of comparison history | same as `x` |
| `σ` | sigma | standard deviation of history | same as `x` |
| `z_t` | z-score | distance from average in standard deviations | unbounded |
| `s_t` | bounded score | compressed comparable signal | strictly between `-1` and `1` |
| `w_i` | weight | intended priority of block `i` | `0` to `1` |
| `q_i` | quality | reliability/availability of block `i` | `0` to `1` |
| `Σ` | capital sigma | add all specified terms | operator |
| `bps` | basis points | one hundredth of one percent | `1 bp = 0.01%` |
