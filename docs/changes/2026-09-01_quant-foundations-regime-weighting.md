# 2026-09-01 — Quant Foundations and Regime Weighting

## Repo-truth delta

Before this change, TradeSync documented a future regime rebuild but the active code still relied on fixed heuristic thresholds and hard-coded regime bonuses. Mathematical notation, weight governance, data-quality renormalization, paper-risk caps, and an experiment persistence model were not defined as one contract.

After this change, the repository contains a notation-first Book 1, a draft paper-only rulebook, deterministic library/CLI, example fixture, targeted tests, SQL migration contract, canonical flow diagram, and updated roadmap/indexes.

## Implemented

- `config/regime/regime-rulebook-v1.json`
- `libs/tradesync_core/tradesync_core/regime_weights.py`
- `fixtures/regime/example-block-inputs.json`
- `tests/test_regime_weights.py`
- `ops/migrations/002_regime_rulebooks.sql`
- `docs/quant-learning/*`
- `docs/architecture/REGIME_RULEBOOK_V1.md`
- `docs/contracts/REGIME_WEIGHT_CONFIG_V1.md`
- `docs/diagrams/regime-rulebook-flow.mmd`

## Decisions

- `tanh(z / k)` is a configurable normalization choice; `k = 2` is provisional.
- block score, data quality, and paper-risk permission are separate outputs.
- unknown risk flags fail closed.
- external event risk cannot produce direction without market confirmation.
- weight changes create new versions; activation changes a pointer and preserves historical replay.
- PostgreSQL is durable authority, Redis is transport, and Qdrant has no configuration authority.
- targets for experiment metrics remain unset until the outcome-data baseline is audited.

## Untouched boundaries

- no wallet, secret, signer, order, deployment, spend, or live-execution setting;
- no canonical ChaseOS vault write;
- no change to the legacy market-data classifier or opportunity scorer;
- no migration applied to persistent PostgreSQL;
- no Regime Lab UI or running-service rebuild.

## Verification

Passed in an isolated E:-based Python 3.11 environment containing the core library's declared `pydantic==2.9.2` dependency:

```powershell
$env:PYTHONPATH = "libs\tradesync_core"
.cache\regime-test-venv\Scripts\python.exe -m unittest tests.test_regime_weights -q
.cache\regime-test-venv\Scripts\python.exe -m tradesync_core.regime_weights validate config\regime\regime-rulebook-v1.json
.cache\regime-test-venv\Scripts\python.exe -m tradesync_core.regime_weights score config\regime\regime-rulebook-v1.json fixtures\regime\example-block-inputs.json
```

Results:

- `9` tests passed;
- configuration valid, `5` blocks, weight sum `1.0`;
- worked fixture score `0.22`, coverage `1.0`, external-risk paper cap `0.45`;
- configuration SHA-256 `d44e7c2b8c8468b45389346b11fa171a71f84ffc936c84175c958b0e0056838f`.

Unverified:

- PostgreSQL migration `UP`/`ROLLBACK` execution. The Docker Desktop Linux engine was not running (`dockerDesktopLinuxEngine` named pipe unavailable), so the SQL was not applied or transaction-tested against PostgreSQL.

## Next safe action

Define the versioned market-feature contract and implement paper-shadow rolling normalization without routing its output into opportunity or execution decisions.
