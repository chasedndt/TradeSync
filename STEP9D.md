# Step 9D — ChaseOS / Strike Zone / TradeSync Control Envelope

Status: FOUNDATION HARDENED; paper-only contract plus durable local approval consumption, not cross-system runtime wiring.

## Boundary

This step defines the first explicit handoff contract among:

- Strike Zone Crypto: creates the review-only market candidate.
- ChaseOS (`C:\Users\chaseos\Documents\chaseos_obsidian`): records the authenticated, single-use operator decision.
- TradeSync: validates the immutable packet before one paper-ledger evaluation.
- Hyperliquid: venue vocabulary only in this step; no private API request occurs.

The envelope cryptographically binds the candidate, its expiry, the ChaseOS approval identifiers, and a closed authority declaration. Any payload change, authority expansion, post-expiry approval, non-Hyperliquid venue, or non-paper mode fails closed.

## Current authority

```text
paper_evaluation_authorized=true
live_execution_authorized=false
wallet_authorized=false
credential_access_authorized=false
signing_authorized=false
private_api_authorized=false
authority_escalation_allowed=false
```

An approval represented by this contract authorizes only one paper evaluation. It cannot authorize an order, wallet access, signing, credentials, or private Hyperliquid connectivity.

`ApprovalConsumptionStore` now makes `scope=once` durable and atomic on the current single-host paper bridge. The approved-envelope evaluator consumes before evaluation; replay, concurrent consumption, conflicting aliases and expired use fail closed. This SQLite store is not authority for a distributed or live executor.

## Test

```bash
pytest -q tests/test_step9d_control_envelope.py tests/test_step9c_paper_ledger.py tests/test_hyperliquid_only.py
```

## Next pass

Add a local adapter that independently verifies and translates the existing Strike Zone governed paper-proposal receipt into `trade_candidate_v1`, then submits this envelope to the consumption-gated TradeSync paper ledger. Keep the adapter fixture-driven until lineage, receipt authenticity, replay, idempotency and rejection evidence pass end to end.
