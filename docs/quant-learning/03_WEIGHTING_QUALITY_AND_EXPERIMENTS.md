# Chapter 3 — Weighting, Data Quality, Risk Caps, and Experiments

## What a weight means

A weight states the planned relative influence of one block in a specific rulebook. It is not a claim that the block causes the market move.

Book 1 proposes these provisional intraday weights:

| Block | Weight | Why it exists |
|---|---:|---|
| price and volatility | `0.30` | direct market state and direction |
| liquidity | `0.25` | tradeability and fragility |
| positioning | `0.20` | funding, open interest, and crowding |
| spot premium | `0.15` | spot-demand confirmation |
| macro and flows | `0.10` | slower context and verified external risk |

The weights add to `1.00`, which is the same as `100%`.

These are hypotheses for paper testing, not fitted production facts. No single block may exceed `0.40` in the Book 1 contract.

## The simple weighted score

For block `i`:

- `w_i` is its weight;
- `s_i` is its normalized score;
- `Σ` means “sum all the following terms.”

```text
weighted score = Σ(w_i * s_i)
```

Worked example:

| Block | Score `s_i` | Weight `w_i` | Contribution `w_i × s_i` |
|---|---:|---:|---:|
| price and volatility | `0.8` | `0.30` | `0.24` |
| liquidity | `-0.4` | `0.25` | `-0.10` |
| positioning | `0.2` | `0.20` | `0.04` |
| spot premium | `0.6` | `0.15` | `0.09` |
| macro and flows | `-0.5` | `0.10` | `-0.05` |

```text
total = 0.24 - 0.10 + 0.04 + 0.09 - 0.05
total = 0.22
```

The result is mildly positive, not a trade instruction.

## Data quality is separate from priority

A block can be important but currently unreliable. TradeSync therefore adds `q_i`, a quality value between `0` and `1`:

- `1.0`: fresh, complete, authoritative, and correctly aligned;
- `0.5`: usable but incomplete, stale within tolerance, or proxy-dependent;
- `0.0`: unavailable or rejected.

The quality-adjusted score is:

```text
score = Σ(w_i * q_i * s_i) / Σ(w_i * q_i)
```

The denominator renormalizes the evidence that is actually available. `Σ(w_i * q_i)` is also the data-coverage value because configured weights total `1`.

Why this matters: setting a missing block's score to zero without adjusting the denominator would pretend that missing means neutral. Sometimes it means “we do not know.” Quality zero removes its directional contribution and lowers coverage.

## Direction, suitability, and risk are different outputs

TradeSync must not collapse three questions into one number:

1. **Direction/state:** what is the measured market condition?
2. **Playbook suitability:** does a named playbook fit that condition?
3. **Risk permission:** how much of an already-approved paper-risk budget is permitted?

A strong technical setup can coexist with high external risk. The setup score can remain strong while the risk permission falls.

## What `paper risk 1.0 -> 0.45` means

It does not mean risking `100%` or `45%` of the account.

`1.0` means `100%` of a separately defined, pre-approved **paper-risk budget**. If that base paper budget is `$100`:

```text
base paper risk = $100
external_risk_high cap = 0.45
permitted paper risk = $100 × 0.45 = $45
```

Book 1 uses a deterministic **minimum cap wins** rule:

```text
paper risk multiplier = minimum(base multiplier, every active risk cap)
```

Examples:

- no flags: `min(1.0) = 1.0`;
- `external_risk_high`: `min(1.0, 0.45) = 0.45`;
- external risk plus fragile liquidity: `min(1.0, 0.45, 0.35) = 0.35`;
- no usable block data: `min(1.0, 0.0) = 0.0`, so paper action is blocked;
- stale critical data: `min(1.0, 0.0) = 0.0`, so paper action is blocked.

An unknown risk flag caps the multiplier at `0.0`. This fail-closed behavior forces a human to define the new condition before the engine can permit paper risk.

## Deterministic rulebook example

```text
IF critical market data is stale
THEN paper_risk_multiplier = 0.0
AND block new paper actions
BECAUSE the system cannot establish current market state.
```

```text
IF verified external-risk severity is high
THEN cap paper_risk_multiplier at 0.45
BUT do not assign bullish or bearish direction
UNLESS measured market blocks independently establish direction.
```

A deterministic rule has named inputs, exact comparators, thresholds, output, reason, precedence, missing-data behavior, and a version.

## How weights change without destroying history

The system is configurable, but individual historical versions are not overwritten.

```text
v1.0.0 remains exactly reproducible
v1.1.0 contains the proposed change
an activation record points paper-shadow evaluation to v1.1.0
rollback moves the pointer back to v1.0.0
```

This is similar to source-code versioning. “Mutable system” means new versions can be created and activated. It does not mean old experiment evidence changes after the result is known.

## Champion/challenger testing

- **Champion:** current paper baseline.
- **Challenger:** one proposed version.
- **Hypothesis:** why the change should improve a named decision.
- **Evaluation window:** fixed before the test.
- **Primary metric:** one measure tied to the decision, such as playbook-conditioned expectancy on completed paper outcomes.
- **Driver metrics:** calibration error and opportunity coverage.
- **Guardrails:** maximum drawdown, turnover, stale-input action rate, and regime-transition stability.

Change one or two related choices per challenger. If weights, normalization, thresholds, and labels all change together, the result cannot tell us what helped.

Do not use future observations to calculate a score for the past. That is look-ahead bias.

## Storage and Docker

The implementation separates storage roles:

| Store | Role |
|---|---|
| JSON in Git | reviewable seed/draft configuration |
| PostgreSQL | canonical rulebook versions, activations, experiments, and score records |
| Redis Streams | distribute active-version changes and score events |
| Qdrant | no authority over weights; optional semantic retrieval only |

PostgreSQL runs in Docker, but its named `pgdata` volume persists independently of a replaced container. Containers are processes and packaging; the named volume is the persistent data location managed by Docker.

The authored migration is `ops/migrations/002_regime_rulebooks.sql`. It is not automatically applied by Compose and has not been promoted to the running database by this foundation.

## Terminal workflow implemented in Book 1

From the repository root:

```powershell
$env:PYTHONPATH = "libs\tradesync_core"

python -m tradesync_core.regime_weights validate `
  config\regime\regime-rulebook-v1.json

python -m tradesync_core.regime_weights explain `
  config\regime\regime-rulebook-v1.json

python -m tradesync_core.regime_weights score `
  config\regime\regime-rulebook-v1.json `
  fixtures\regime\example-block-inputs.json

python -m tradesync_core.regime_weights diff `
  config\regime\regime-rulebook-v1.json `
  path\to\challenger-rulebook.json
```

The later Regime Lab panel will call the same validation and calculation library. It will not implement a second browser-only formula.
