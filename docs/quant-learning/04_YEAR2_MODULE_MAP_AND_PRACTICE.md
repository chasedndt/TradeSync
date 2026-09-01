# Chapter 4 — Year 2 Module Map and Practice Gates

Exact module names differ by university. This map uses common Year 2 subject areas; it must be matched to the operator's real syllabus when the module handbook is available.

## Topic map

| TradeSync work | Mathematical topic | Typical module | Why it matters |
|---|---|---|---|
| mean, variance, standard deviation, z-score | descriptive statistics | Probability and Statistics | describes location, spread, and unusualness |
| robust median and MAD | robust statistics | Applied Statistics / Data Analysis | reduces sensitivity to outliers |
| weighted block score | weighted averages and linear combinations | Linear Algebra / Statistics | combines comparable signals transparently |
| `tanh` compression | functions, exponentials, transformations | Calculus / Mathematical Methods | maps unbounded inputs smoothly to a bounded scale |
| correlation and covariance | dependence | Probability and Statistics | detects redundant blocks and unstable relationships |
| linear/logistic regression | statistical modelling | Regression / Machine Learning | estimates relationships without hand-picking every weight |
| hypothesis tests and confidence intervals | statistical inference | Probability and Statistics | evaluates whether a challenger improvement may be noise |
| matrices and vectors | linear algebra | Linear Algebra | expresses many assets, features, and weights efficiently |
| constrained weight selection | optimization | Operational Research / Numerical Methods | searches weights subject to limits and guardrails |
| regime transition probabilities | Markov chains | Stochastic Processes | models probability of moving between market states |
| autocorrelation and rolling estimates | time-series analysis | Time Series / Econometrics | handles ordered observations and dependence through time |
| expectancy, variance, drawdown | probability and risk | Financial Mathematics / Quantitative Methods | evaluates paper-playbook outcomes |

## Practice Gate 1 — Read the notation

Write each line in plain English:

1. `x_t = 8 bps`
2. `μ = 2 bps`
3. `σ = 3 bps`
4. `z_t = (x_t - μ) / σ`
5. `s_t = tanh(z_t / 2)`

Completion standard: distinguish the subscript `t`, Greek mu, Greek sigma, z-score, and bounded score without referring to them all as “the score.”

## Practice Gate 2 — Calculate by hand

Given `x_t = 14`, `μ = 10`, and `σ = 2`:

1. calculate `x_t - μ`;
2. calculate `z_t`;
3. use the chapter table to approximate `s_t`;
4. explain what the positive sign means;
5. explain what it does **not** prove.

Self-check: `z_t` should be `2`, and `s_t` should be approximately `0.762`.

## Practice Gate 3 — Reproduce the weighted example

Using the five Book 1 blocks:

1. calculate each `weight × score` contribution;
2. add the five contributions;
3. confirm the result `0.22`;
4. change macro/flows from `-0.5` to `0.5` and calculate the new total;
5. state why the change is exactly `0.10`.

Self-check: the new total is `0.32` because a `1.0` change multiplied by the `0.10` weight changes the total by `0.10`.

## Practice Gate 4 — Quality and missing data

Use only:

```text
price score = 1.0, weight = 0.30, quality = 1.0
liquidity score = -1.0, weight = 0.25, quality = 0.5
all other blocks unavailable
```

Calculate:

1. numerator `Σ(w_i q_i s_i)`;
2. coverage/denominator `Σ(w_i q_i)`;
3. quality-adjusted score;
4. the Book 1 paper-risk cap caused by coverage below `0.70`.

Self-check: numerator `0.175`, coverage `0.425`, score approximately `0.4118`, and risk multiplier `0.50`.

## Practice Gate 5 — Write a deterministic comparator

Write a specification for a premium measure containing:

- measured venue and symbol;
- comparator venue/index and symbol;
- quote currency;
- formula in decimals;
- conversion into basis points;
- maximum timestamp mismatch;
- stale/missing behavior;
- provenance label.

Completion standard: another developer can implement the comparator without guessing.

## Practice Gate 6 — Design the first challenger

Create a proposed `v1.1.0` with only one change: move `0.05` weight from price/volatility to liquidity.

Before running it, write:

1. hypothesis;
2. fixed sample or time window;
3. primary outcome metric;
4. at least two guardrails;
5. promotion rule;
6. rollback rule.

Do not activate it. Run the terminal `diff` command and inspect the exact delta first.

## Later advanced gates

The following are deliberately not used to fit live weights yet:

- covariance matrix and multicollinearity check;
- regularized regression for candidate weights;
- walk-forward validation;
- bootstrap confidence intervals;
- Markov transition matrix;
- constrained optimization with maximum-weight and turnover penalties.

Each becomes a new chapter and implementation task only after its prerequisites and data quality are verified.

## Learning evidence to retain

For each completed gate, retain:

- the question;
- handwritten or typed working;
- final answer;
- any code used to check it;
- what the result means in TradeSync;
- one limitation or failure case.

These can later be converted into a reusable quant-learning repository and approved ChaseOS knowledge-graph nodes. This repository remains the first applied book; extraction is future work, not part of this foundation.
