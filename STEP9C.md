# Step 9C — Hyperliquid Digital Twin / Paper Ledger

Status: fixture-driven proof implemented; live execution remains disabled.

## Purpose

Step 9C consumes a review-only `trade_candidate_v1`, evaluates its activation and invalidation conditions against closed fixture candles, and writes one deterministic append-only paper-ledger result. It does not call Hyperliquid or any private venue endpoint.

## Human-approval invariant

Any future live execution remains human approval gated. The blueprint requires an approval bound to one order or a bounded batch, including candidate, symbol, side, size, leverage, and expiry. Autonomous approval is forbidden.

Current authority:

```text
paper_only=true
execution_enabled=false
wallet_enabled=false
private_api_enabled=false
credential_access_enabled=false
```

## Run the fixture proof

```bash
python3 tools/run_step9c_paper_fixture.py \
  --output-dir artifacts/step9c-fixture-run
```

Running the same candidate and fixture twice is idempotent: the JSONL ledger retains one deterministic row.

## Test

```bash
pytest -q tests/test_step9c_paper_ledger.py
pytest -q tests/test_hyperliquid_only.py
```

Focused proof: 6 Step 9C tests passed. Hyperliquid-only invariant proof: 5 tests passed.

## Outputs

- `artifacts/step9c-fixture-run/paper_result.json`
- `artifacts/step9c-fixture-run/paper_ledger.jsonl`
- `artifacts/step9c-fixture-run/execution_blueprint.json`
- `artifacts/step9c-fixture-run/run_metadata.json`

The fixture result is a paper fill at `65050` for `BTC-USD-PERP`. This is deterministic simulation evidence, not a trade, recommendation, account event, or performance claim.
