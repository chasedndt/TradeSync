# Paper approval consumption hardening — 2026-08-24

## Repository recovery

The orphaned `tradesync-hyperliquid-only` directory was reconciled against the authoritative GitHub repository. Its tracked source matched remote branch `tradesync-hyperliquid-only` at `7d6f671`, except for the later Market Command Compose update. Fourteen later paper/governance source files were untracked because the old worktree metadata had been lost. Those exact changes were reconstructed in an isolated E: worktree; generated paper artifacts were not imported.

## Security change

`scope=once` is now an enforced state transition rather than envelope wording. `ApprovalConsumptionStore` uses a `BEGIN IMMEDIATE` SQLite transaction, full synchronous durability, and unique approval, decision and envelope identities. The approved-envelope bridge consumes before evaluation. Replay, concurrent use, aliasing, expiry and digest-shape failures deny.

The current store is for the local single-host paper bridge. A distributed or live executor must use a separately reviewed shared transactional store and a distinct live-approval schema. Nothing in this change enables a wallet, signer, private API or live order.

## Recovery rule

If a process fails after consumption but before producing a result, the approval remains consumed and the operator must issue a new one. This favors duplicate-action prevention over automatic retry after an uncertain outcome.

The readiness test timeout was raised from 45 to 90 seconds because stopped Ollama/WSL probes currently take about 55 seconds. The audit itself still returns a fail-closed gate result; the longer harness timeout lets the test assert that result instead of failing before it arrives.

Runtime SQLite files and their WAL/SHM companions are ignored to prevent consumption-state artifacts from entering source control.
