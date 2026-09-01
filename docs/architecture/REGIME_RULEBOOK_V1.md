# Regime Rulebook v1 Architecture

## Decision

TradeSync will score **playbook suitability** from versioned market blocks and will represent geopolitical/news information as a risk/context overlay unless measured market data independently confirms direction.

This avoids the ambiguous rule “war means Bitcoin down” or “ETF inflow means buy.” The engine records what was observed, how reliable it was, which deterministic rule ran, and what action class remained permitted.

## Eight-axis market state

The long-term regime model retains separate axes:

1. direction;
2. volatility;
3. liquidity;
4. leverage/positioning;
5. spot demand;
6. institutional flow;
7. external risk;
8. data confidence.

Book 1 combines these into five provisional intraday scoring blocks for configuration simplicity. The stored evidence must retain underlying features so the axes can later be separated without losing history.

## Deterministic evaluation flow

```text
source event
  -> validate source, timestamp, unit, and provenance
  -> calculate named feature
  -> compare with declared history/comparator
  -> normalize to [-1, 1]
  -> calculate data quality [0, 1]
  -> calculate weighted block score and coverage
  -> evaluate independent risk caps
  -> evaluate named playbook permissions
  -> persist full trace with rulebook version and digest
  -> publish paper-shadow event
```

## Input authority

| Input | Direction allowed? | Initial role |
|---|---|---|
| Hyperliquid price/trades/book/funding/OI | yes, where field semantics support it | primary market truth |
| observed liquidations | yes, only with explicit observed direction | leverage evidence |
| inferred liquidation pressure | bounded proxy only | risk/context |
| Coinbase or broad spot premium | confirmation only | spot-demand context |
| ETF flows | no immediate direction by themselves | slow context |
| geopolitical event record | no direction by itself | external-risk cap |
| model/agent interpretation | no authority | explanation and proposal |

## Version lifecycle

```text
draft -> paper shadow -> evaluated -> paper active -> retired
```

Promotion requires a new activation record. A past configuration and past score event are never rewritten to match a new theory.

## KPI design for experiments

Candidate metrics are separated by decision role:

- primary outcome candidate: playbook-conditioned expectancy after fees/funding/slippage on completed paper outcomes;
- driver candidates: calibration error, eligible-opportunity coverage, and regime transition accuracy;
- guardrails: maximum paper drawdown, turnover, stale-input action rate, missing-lineage rate, and excessive regime flipping.

Targets are not set in v1 because current historical outcome coverage and data quality have not been audited. Setting a threshold before measuring the baseline would create false precision.

## Persistence

The intended tables are:

- `regime_rulebooks`: immutable configuration versions and digests;
- `regime_weight_activations`: time-bounded active pointers;
- `regime_experiments`: champion/challenger hypotheses and results;
- `regime_score_events`: replayable calculation traces.

The SQL contract is authored in `ops/migrations/002_regime_rulebooks.sql`. It is not yet applied to the running database.

## Outage behavior

- optional premium, ETF, macro, news, ChaseOS, and agent connectors may reduce quality/coverage but cannot stop core market observation;
- critical Hyperliquid market-state staleness blocks new paper actions;
- unknown risk flags fail closed for paper-risk permission;
- Redis interruption delays distribution, while committed PostgreSQL evidence remains durable;
- no optional context source can activate a rulebook.

## Current/legacy boundary

The market-data snapshotter and enhanced scorer still contain legacy fixed thresholds and bonuses. v1 runs separately until paper replay proves the replacement path. Documentation must not call the new rulebook the active opportunity scorer before that integration and evidence exist.

## References

- [Book 1](../quant-learning/README.md)
- [Rulebook configuration contract](../contracts/REGIME_WEIGHT_CONFIG_V1.md)
- [Canonical flow diagram](../diagrams/regime-rulebook-flow.mmd)
