# Mobile lifecycle policy — locally deployed

## Authenticated API and worker isolation — 01:28 BST

Codex continued on the same preserved checkout, E: 342 GB free. Expanded the
isolated SQL QA to invoke the actual authenticated preference and receipt routes.
It passed: unauthorized/unconfirmed opt-in rejected; fixture provider acceptance
then explicit fixture attestation allowed preferences; readback returned parsed
preferences without topic; opt-out cleared activation timestamp; invalid timezone
rejected. All rows rolled back. This is not physical phone receipt evidence.

Fixed worker coupling: paper-event intake failure no longer prevents delivery of
already-queued notifications. Both failures retain separate safe error categories;
cancellation still stops dispatch. `.venv/Scripts/python.exe tools/run_tests.py
state-api`: **162 passed in 13.51s**. State API rebuilt/replaced locally; runtime
mobile readback remains configured=false with running worker. No message or secret
setup, public portfolio write, wallet/live order, commit or push. Frontend unchanged.

Authenticated route acceptance is now complete in isolated SQL; private setup and
actual Android/iPhone receipt plus sustained delivery remain open. Next independent
development is timestamped external entry evidence, then source-contribution
evaluation without automatic strategy promotion.

## Acceptance update — 01:25 BST

Migration 024 is now applied and State API/cockpit-ui are locally rebuilt and
healthy. The earlier source-only notes below are historical.

- `tools/qa_mobile_lifecycle.py`: real PostgreSQL temporary tables, migration
  UP/DOWN/UP, default opt-out, dedupe, budget suppression, dispatch-time opt-out,
  all-day quiet, manual-test bypass and activation boundary **passed**. Fake
  provider only; all temporary changes rolled back. The script can be rerun after
  migration because it resets only the temporary table's added columns.
- `.venv/Scripts/python.exe tools/run_tests.py state-api`: **159 passed in 17.97s**.
- `npm run build`: TypeScript/Vite passed; existing bundle/dependency warnings.
- `tools/qa_mobile_alerts.cjs`: 1366/375px live setup-required readback and fixture
  controls passed, including blocked unconfirmed opt-in, preference save,
  dismissed receipt confirmation and no document overflow/page errors.
- Phone fixture screenshot inspected. Evidence under
  `E:/Visual QA/TradeSync Visual QA/Current Reviews/2026-09-14-mobile-lifecycle`.
- Runtime: configured=false, worker running with current tick and no error.
  No phone delivery, key setup, real device enrollment or provider send performed.

Remaining: private control setup, real Android/iPhone subscription/test/receipt,
and sustained lifecycle delivery acceptance. UI preference save was fixture-tested;
real authenticated preference routing still needs its own acceptance test. No
wallet/signature/live-execution, source-weight, commit or push changes.

## Initial source-only record

14 September 2026, 01:17 onward. Codex / Axiom-Codex. Existing dirty branch and
342 GB free E: workspace preserved. Project-local activity record only.

Implemented in source, **not yet deployed or migration-applied**:

- Migration 024 stores notification preferences and opt-in start timestamp.
- Authenticated preferences endpoint requires prior phone receipt attestation
  before paper-event opt-in. Defaults remain opted out.
- Paper open/close event producer reads recent durable lifecycle events without
  coupling notification failures to paper-position transactions.
- Per-device rolling 24-hour budget (default 10, maximum 50), IANA timezone and
  quiet hours. Equal start/end with quiet enabled means all-day quiet.
- Quiet and budget suppression are recorded as expired outbox rows with reasons;
  no morning replay or historical opt-in backfill. Explicit tests bypass quiet hours.
- Dispatch rechecks opt-out/quiet status before paper notification sends. An
  already in-flight provider request cannot be recalled.

Initial State API suite: **157 passed in 11.17s**, including eight pure policy
cases covering DST-aware quiet boundaries, daytime/all-day quiet, disabled quiet,
invalid zones/hours/budgets and naive timestamps. Two additional authorization/
disabled-producer tests were added after this run and await the next full run.
No claim of end-to-end producer acceptance yet.

Next required work before deployment: isolated PostgreSQL producer/policy tests,
preference UI and rendered QA, migration UP/DOWN verification, then local runtime
replacement and readback. Private control setup and actual Android/iPhone receipt
remain operator acceptance steps. No device, key or external message created.

[Mobile runbook](../runbooks/MOBILE_ALERTS.md) ·
[Readiness checklist](../runbooks/TRADING_DAY_READINESS.md) ·
[Documentation index](../README.md) · [Roadmap](../../roadmap.md).
