# 2026-09-01 — Market Feature and Normalization Foundation

## Repo-truth delta

Before this change, the regime rulebook accepted already-normalized block inputs but there was no source-governed feature catalog or replayable raw-history normalization contract. The market-data model also lacked the `DERIVED` enum used by its sample contract, and hourly funding annualization omitted the 24 periods per day.

After this change, TradeSync has a 17-feature Hyperliquid-only paper-shadow catalog, ordinary and robust rolling normalization, timestamp/look-ahead validation, objective sample/freshness quality, CLI comparison, persistence schema, an applied Year 2 lab, and corrected funding/derived truth labels.

## Implemented

- `config/features/market-feature-catalog-v1.json`
- `libs/tradesync_core/tradesync_core/market_features.py`
- `fixtures/features/spread-robust-normalization.json`
- `tests/test_market_features.py`
- `tests/test_market_data_math.py`
- `ops/migrations/003_market_features.sql`
- `docs/contracts/MARKET_FEATURE_V1.md`
- `docs/quant-learning/labs/LAB_01_ROLLING_NORMALIZATION.md`
- `docs/diagrams/market-feature-normalization.mmd`
- `MetricStatus.DERIVED` and derived microstructure labelling
- corrected simple annualization `mean hourly rate * 24 * 365`
- coverage-aware legacy Regime Summary confidence and condition guards

## Source and metric decisions

- observed/transparent-derived Hyperliquid features may become paper score candidates;
- proxy, context-only, planned, and unavailable features cannot produce a generic score;
- funding, OI, and volume are playbook-specific and do not automatically emit direction;
- direct liquidation flow, direct CVD, Coinbase premium, and ETF flow remain unavailable until admitted sources exist;
- shorter-horizon volume estimates derived by dividing rolling 24h volume are not admitted features;
- freshness/sample quality is separate from provenance authority.

## Untouched boundaries

- active legacy regime and opportunity scoring;
- persistent PostgreSQL state;
- Docker service state;
- wallet, secrets, approvals, orders, deployment, and live execution;
- canonical ChaseOS vault and knowledge graph.

## Verification

Passed in the isolated E:-based Python 3.11 test environment:

```powershell
$env:PYTHONPATH = "libs\tradesync_core"
.cache\regime-test-venv\Scripts\python.exe -m unittest `
  tests.test_regime_weights `
  tests.test_market_features `
  tests.test_market_data_math -q

.cache\regime-test-venv\Scripts\python.exe -m tradesync_core.market_features `
  validate-catalog config\features\market-feature-catalog-v1.json

.cache\regime-test-venv\Scripts\python.exe -m tradesync_core.market_features `
  normalize config\features\market-feature-catalog-v1.json `
  fixtures\features\spread-robust-normalization.json

.cache\regime-test-venv\Scripts\python.exe `
  services\market-data\tests\fixture_runner.py
```

Results:

- `26` unit/contract tests passed;
- offline pipeline parsed `3` assets and `12` normalized events without a live provider;
- funding-only fixture snapshots now report `UNKNOWN` condition and `low` confidence;
- proxy required inputs reduce confidence but cannot create a market-condition label;
- catalog valid: `17` features, `10` implemented definitions, `7` implemented scoring-eligible definitions;
- catalog SHA-256 `e030ec1132075f696c950cdf8f21ddc5f7d20fc03015f3928e540a00c8599961`;
- rulebook compatibility passes while correctly identifying `macro_flows` and `spot_premium` as uncovered;
- robust spread fixture: centre `0.47`, scaled MAD `0.037065`, z-score `11.601241062997`, inverse score `-0.999981690729`, data quality `0.166666666667`.

Unverified:

- PostgreSQL migration `UP`/`DOWN` transaction execution. Docker Desktop's Linux engine remains unavailable, so migrations `002` and `003` were not applied or transaction-tested.

## Remaining work

- extract catalog features from committed market events;
- persist observations/normalizations through an approved migration run;
- aggregate admitted feature values into versioned block scores;
- expose paper-shadow comparison through State API and Regime Lab;
- backfill enough time-ordered history to meet declared lookbacks.
