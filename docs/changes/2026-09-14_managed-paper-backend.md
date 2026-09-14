# 14 September — managed paper backend and research protocol

## Repo-truth delta / changes

Codex / Axiom-Codex continued on the preserved dirty dashboard-overhaul branch,
00:49–01:02 BST; E: about 342 GB free. This is the project-local activity/build
record, not canonical ChaseOS writeback.

Implemented `managed_paper.py` core and State API routes/worker, migration 023,
immutable entry/plan update protection, separate lifecycle events, scalp/intraday/
swing profiles, observed-side fills, declared costs, portfolio caps, operator
close, expiry and observation-gap flags. No source has automatically opened a
position. No managed-paper UI has been added in this slice yet.

Primary-source review also corrected the existing rehearsal maker-fee sign:
base perp maker fee **+0.015%**, not a rebate. Source date and test updated;
taker simulation remains 0.045%. Historical stored rehearsals are untouched.

[Frozen research protocol and mathematics exercises](../research/2026-09-14_managed-paper-protocol.md)
explain parameters, assumptions, the fee correction, funding limitations and
the reviewed backtest-overfitting paper. No CSCV/PBO implementation, statistical
edge or profitability is claimed.

## Untouched boundaries

No live order, wallet/signature, strategy promotion, secret setup, public publish,
commit or push. Only State API was rebuilt/replaced; unrelated services retained.
QA schema/tables were isolated and rolled back; no real portfolio entries created.
Existing old Signal Ledger trades and external source weights were not rewritten.

## Verification

- Focused lifecycle/rehearsal tests: **15 passed** after correcting the expected
  fee-source date. Tests cover long/short exit sides, targets/stops, adverse gap
  fills, manual/time exits, frozen inputs, depth/staleness refusal and closed ATR.
- `.venv/Scripts/python.exe tools/run_tests.py root state-api`:
  **648 root / 149 API passed**, 17 integration deselected, two warnings,
  10 passing subtests. New API tests reject invalid/stale sources, preserve
  idempotency and explicitly keep an empty portfolio execution-disabled.
- Migration 023 UP/DOWN tested in an isolated transaction/schema; QA rollback
  succeeded. UP then committed to live PostgreSQL and migration registry.
- `tools/qa_managed_paper.py` in State API container: temporary tables using the
  real PostgreSQL entry-protection trigger. Mutating entry/initial plan rejected;
  lifecycle state progressed open→closed; original evidence preserved. Rollback
  succeeded. Real portfolio count afterwards: **zero**.
- Live `/state/paper-positions`: empty positions, current worker tick, no worker
  error, `execution_authority=false`. This verifies startup/readback, not a
  completed live-data forward trade or profitable strategy.
- Docker State API built and locally replaced. No frontend change in this slice,
  so no new frontend/visual acceptance claimed.

## API / next safe action

- `GET /state/paper-positions`: latest 100 and worker health.
- `POST /state/paper-positions`: opportunity UUID, style, notional; freezes entry.
- `GET /state/paper-positions/{id}/evidence`: original snapshot and digest.
- `POST /state/paper-positions/{id}/close`: observed-price simulated close.

Next: dashboard candidate selection/open/close/evidence inspection; feed eligible
lifecycle events into notification delivery with explicit per-device opt-in and
quiet-hour/budget controls. Then real-data paper lifecycle acceptance, durable
direct external as-of entry joins, settled-funding evidence and pre-registered
forward comparisons. Current funding remains a scenario; observation gaps are
not silently repaired. Candidate parameters have not earned strategy weight.

The entire integration goal remains active. Mobile credential/device acceptance,
event producers/preferences, operator wallet acceptance, source contribution
evaluation, full trading-day checklist and remaining prior handover items are
still open. This backend slice is not a declaration of trading-day readiness.
