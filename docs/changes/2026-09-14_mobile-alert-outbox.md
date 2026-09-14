# 14 September — mobile notification foundation

## Repo-truth delta / changes

Codex / Axiom-Codex continued the active goal at 00:33 BST on the existing dirty
dashboard-overhaul branch. E: 342 GB free. This is the project-local activity,
build and handover record; canonical ChaseOS writeback remains governed.

Migration 022 adds device enrollment and a durable delivery outbox. State API
adds authenticated enrollment, subscription-details retrieval, generic test
enqueue, disable and operator-attested receipt. The lifespan starts a bounded
worker with dedupe, leases, expiry, retries and verified provider acceptance.
Status exposes setup state and worker heartbeat/error without device topics.
Settings adds Android/iPhone enrollment and a delivery ledger. No custom iOS
build or wallet access is involved. [Setup/runbook](../runbooks/MOBILE_ALERTS.md).

## Untouched boundaries

No real device enrolled, no control key generated/disclosed, no external message
sent, no trading or signing authority. No unrelated services stopped, no source
or user data removed, no push/commit/public deployment. Only newly created QA
schema/tables were rolled back. Existing dirty work preserved.

## Verification

- Migration UP and DOWN exercised inside an isolated QA schema/transaction,
  then rolled back; UP applied transactionally to live PostgreSQL and recorded
  as version 022. Existing versions 001–021 already applied.
- State API suite: **145 passed**. Covers default-disabled controls, wrong-key
  denial, template/topic restrictions, provider acceptance readback and expiry/
  dedupe query contract.
- `tools/qa_mobile_outbox.py` inside State API container: real PostgreSQL temporary
  tables, fake transport, full rollback. Verified enqueue dedupe, provider accepted
  distinct from phone receipt, no repeat of accepted send, expiry and three-attempt
  failure. Readback of real tables afterwards: **0 devices / 0 outbox events**.
- `npm run build`: passed (21.08s initial mobile build); existing bundle warnings.
- Local State API/Cockpit images built/replaced. Runtime status: configured false,
  Android/iOS listed, worker running. No claim that disabled delivery works on a phone.
- `tools/qa_mobile_alerts.cjs`: real setup-required panel plus explicitly labelled
  fixture enrollment/test/receipt controls at **1366 / 375px**; no page overflow
  or uncaught errors. Dismissing the receipt confirmation sends zero confirmation
  requests. Fixture tests do not contact ntfy or insert real device rows.

QA: `E:/Visual QA/TradeSync Visual QA/Current Reviews/2026-09-14-mobile-alerts`.

Final follow-up: subscription-details recovery and worker heartbeat/error reporting
included in rebuilt/replaced services. Final frontend build passed (18.94s),
responsive QA repeated successfully at both widths; phone setup/fixture screenshots
visually inspected. At 00:48 BST the worker heartbeat was current with no error,
delivery remained unconfigured, and all healthchecked containers were healthy.
`git diff --check` passed (line-ending warnings only).
Final regression: **640 root / 145 State API passed**; root also reports 17
integration deselections, two warnings and 10 passing subtests.

## Remaining unknowns / next safe action

Follow the runbook for private control-key setup and physical-device acceptance.
The existing non-blocking operator question asks which phone will be tested first.
Source event producers, quiet hours/preferences and delivery budgets remain open;
this is a functioning outbox/control foundation, not completed market-alert wiring.
In parallel, continue durable entry-time evidence and managed paper positions so
notifications will represent real lifecycle events rather than synthetic alerts.

The complete integration goal remains active; no profitability or live-trading
readiness is implied. Topic randomness is not authentication, provider acceptance
is not device receipt, and retryable transport is not exactly-once delivery.
