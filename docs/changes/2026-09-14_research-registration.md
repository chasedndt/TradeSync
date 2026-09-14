# Research registration — API locally deployed

## Populated forward API acceptance — 02:00 BST

Expanded `tools/qa_research_registry_api.py` and ran against the deployed API
implementation in an isolated PostgreSQL schema. Passed a synthetic clean closed
entry, open outcome and pre-registration entry: one eligible, one pending, one
outside population. Baseline 100 bps, missing-context filter abstention zero;
state remains collecting and promotion false. These are fixture arithmetic checks,
not actual trading returns. Entire schema rolled back.

Live readback: zero public trials, zero managed positions; paper worker error null;
mobile configured=false and worker error null. No build/deployment needed for this
QA-only change. Existing dirty branch preserved; E: 342 GB free. No secret, phone
send, wallet, real registration/order, commit or push.

The implementation and fixture acceptance for this registration slice are now
complete. Real operator registration, later entries and elapsed forward outcomes
remain unverified; the wider integration goal is not complete.

## Dashboard controls — 01:58 BST

Explicit protocol registration, confirmation, frozen specification inspection and
on-demand evaluation are now in Signal Ledger. Copy distinguishes registration
from scheduling/trading and operational review floors from significance. The
dashboard guidance informed visible missing-result and authority boundaries.

`npm run build` passed (Vite 22.27s; existing warnings). cockpit-ui alone rebuilt
and replaced. `tools/qa_research_trials_ui.cjs`: real empty registry and fixture
registration/evaluation/specification passed at 1366/375px; cancelling registration
sends nothing; no document overflow/page errors. Phone screenshot inspected under
`E:/Visual QA/TradeSync Visual QA/Current Reviews/2026-09-14-research-trials`.
No public trial created. No backend change, secret, send, wallet, commit or push.

Remaining: populated forward API acceptance, real operator registration/entries,
full trading-day/phone/wallet acceptance and wider source evaluation. A completed
UI does not supply the elapsed-time research evidence a trial still needs.

## Integrated acceptance and deployment — 01:55 BST

`tools/qa_research_registry_api.py` invoked actual API handlers against a unique
PostgreSQL schema. Passed invalid-style rejection, registration, duplicate ID/time
preservation, parsed listing, empty forward evaluation and missing-trial 404.
No network/trading actions; full schema/transaction rolled back.

Migration 025 then applied through the standard runner with only that pending
file staged. State API rebuilt and locally replaced. Live `/state/research-trials`
returns an empty list and research-only authority. **No public trial registered.**
The prior source-only paragraphs below are historical. UI explicit registration
and populated forward acceptance still remain. No wallet, secret, phone send,
strategy promotion, commit or push. Existing work preserved, E: 342 GB free.

## Evaluation API wiring — 01:52 BST

Added read-only `/state/research-trials/{id}/evaluation`. It verifies the stored
specification fingerprint, selects post-registration records and invokes the
matching evaluator. More than 10,000 candidate records returns incomplete instead
of silently truncating and presenting a review-ready result. Empty trials remain
collecting; altered fingerprints fail before querying outcomes.

New route tests cover empty/unmeasured, over-limit refusal and fingerprint mismatch.
Root suite passed **659 tests**, 17 integration deselected, two existing warnings;
State API result is recorded in task output. Source remains undeployed until full
registry route/migration acceptance. No new database or external mutations.

## Database acceptance and evaluator — 01:51 BST

`tools/qa_research_registry.py` passed against real PostgreSQL in a unique schema:
migration UP/DOWN/UP, database-assigned timestamp, duplicate preservation, rejected
specification/time edits and DELETE. Entire transaction/schema rolled back; no
public trial registration or migration applied. E: remained 342 GB free.

Added pure forward evaluator: accepts only supported universe/style entries
strictly after registration and within the 30-day window; future exit times and
open positions remain pending. States distinguish collecting, awaiting outcomes,
insufficient clean sample and manual review readiness. A stored definition must
match the evaluator exactly; changed definitions cannot silently reuse it.
Review readiness still grants no promotion/authority or statistical significance.

Eleven focused trial/source-comparison tests passed in 1.27s. New tests cover
registration boundary, future outcomes, unresolved positions after window end,
insufficient sample and changed-spec refusal. This evaluator remains source-only;
API result wiring, authenticated/action acceptance, UI and deployment remain next.
No real trial, secret, notification, wallet, order, commit or push was created.

14 September 2026, 01:47–01:49 BST. Codex / Axiom-Codex; preserved dirty branch,
E: 342 GB free. Project-local activity/build record. No canonical writeback.

Added fixed research specifications per scalp/intraday/swing, canonical JSON
fingerprints, proposed migration 025 and GET/POST research-trial routes. Database
registration time is assigned by PostgreSQL. Same-spec retries return the same
registration rather than resetting its time. Proposed trigger rejects UPDATE and
DELETE; this is application-data protection, not proof against a DB administrator.

The protocol declares 30-day entry windows, evaluation after admitted positions
resolve, the paired per-opportunity metric, missing-context/gap policies, scenario
costs and a 100-clean-entry review floor. The floor is an operational choice, not
a statistical power calculation. Operator selection and overlapping positions
remain limitations. Registration does not schedule jobs, open trades or promote.

Verification: eight focused trial-definition/source-comparison tests passed in
0.78s. API regression suite was run; its result is recorded in the task output.
New registration routes still need dedicated real SQL/API acceptance. Migration
025 is **not applied** and the new source is **not deployed** in this slice.

Next: isolated migration UP/DOWN and immutable/idempotent registration tests;
forward-only cohort evaluator; UI explicit registration; deployment/readback.
No trial has actually been registered. No secrets, messages, wallets, real orders,
commits or pushes. Full integration goal and physical-device acceptance remain.

[Protocol](../research/2026-09-14_source-comparison-v1.md) ·
[Documentation index](../README.md) · [Roadmap](../../roadmap.md).
