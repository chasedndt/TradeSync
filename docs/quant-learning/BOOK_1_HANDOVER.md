# TradeSync Quant Foundations — Book 1 Handover

## Outcome

Book 1 converts the initial regime-weight discussion into a teachable and testable foundation:

- mathematical notation is defined before use;
- normalization is separated from weighting;
- data quality is separated from intended priority;
- market/playbook score is separated from paper-risk permission;
- weight changes use new versions instead of overwriting historical evidence;
- PostgreSQL is specified as durable truth, Redis as transport, and Qdrant as non-authoritative;
- a local CLI validates, explains, scores, and diffs rulebooks;
- an additive SQL migration defines future persistence without silently modifying the running database.

## Current implementation

| Artifact | Status |
|---|---|
| `config/regime/regime-rulebook-v1.json` | draft paper-shadow seed |
| `tradesync_core.regime_weights` | implemented deterministic library and CLI |
| example five-block fixture | implemented |
| unit tests | implemented |
| `002_regime_rulebooks.sql` | authored, not applied to persistent runtime |
| current market-data regime classifier | unchanged legacy heuristic |
| current scorer regime bonuses | unchanged legacy fixed values |
| Regime Lab UI | specified, not implemented |
| ordinary/robust paper-shadow normalization library | implemented |
| live feature extraction and history persistence | not implemented |
| paper champion/challenger runner | not implemented |
| wallet/live execution | out of scope and disabled |

## Mathematical contract

1. A raw observation `x_t` is compared with a declared historical window.
2. A z-score describes distance from the selected mean in standard deviations.
3. `tanh(z_t / k)` converts it to a bounded score; Book 1 uses provisional `k = 2`.
4. Each block produces a score `s_i` in `[-1, 1]` and quality `q_i` in `[0, 1]`.
5. The engine calculates `Σ(w_i q_i s_i) / Σ(w_i q_i)`.
6. Data coverage equals `Σ(w_i q_i)` when configured weights sum to one.
7. Separate deterministic risk flags cap the paper-risk budget using the most conservative active cap.
8. The event stores the version and digest required to replay the result.

## How configuration will be managed

The terminal workflow is available now. A later Regime Lab panel should provide:

- view active champion and draft challenger;
- edit draft block weights with numeric fields and sliders;
- show running total and block changes;
- refuse invalid totals or maximum-weight violations;
- preview `tanh` compression curves for candidate `k` values;
- replay a selected historical window;
- compare primary metric, drivers, and guardrails;
- submit paper activation for operator approval;
- activate by creating an activation record, never by editing the old version;
- roll back the active pointer;
- export the exact JSON and digest.

The panel must never contain wallet secrets or a live-execution shortcut.

## Next safe implementation sequence

1. Extract `market_feature_v1` values from committed market events using the catalog.
2. Persist observations and normalization traces after an approved migration test.
3. Aggregate admitted features into versioned block scores without changing opportunities.
4. Add a repository/service layer for feature, rulebook, and score events.
5. Run the new engine beside the legacy regime summary without changing opportunities.
6. Build Regime Lab read-only comparison, then draft editing.
7. Start the first fixed-window champion/challenger paper experiment.
8. Promote only after outcome and guardrail evidence is complete.

## Remaining decisions

- exact Year 2 module names and assessment topics;
- lookback window and sampling interval for each feature;
- ordinary versus robust z-score by feature;
- exact Coinbase/spot comparator and free provider reliability;
- primary paper outcome metric and minimum sample;
- whether weights are shared across BTC/ETH or versioned by asset class;
- who may draft, approve, activate, and retire paper rulebooks.

## Safety state

This foundation does not use secrets, mutate the canonical ChaseOS vault, apply a database migration, change the running scorer, or enable execution. `EXECUTION_ENABLED=false` and `DRY_RUN=true` remain the governing runtime boundary.
