# Persistent paper-entry control — source foundation

## Shared-lock acceptance and UI source — 02:08 BST

Two-connection PostgreSQL test passed: while the actual control API transaction
held advisory lock 230914, a separate connection could not acquire it. This proves
the shared lock is held; it is not a full multi-process stress/soak test. Isolated
schema rolled back, public control untouched.

Added UI reason/confirmation and paused/unavailable status; entry submission is
disabled unless persistent control explicitly allows it. Closing stays separate.
Updated browser QA to test cancelled resume and confirmed fixture resume before
paper entry. Build/rendered QA results remain pending at this record; source-only,
migration 026 not applied and runtime unchanged. No public resume or trade.

## SQL and entry/close acceptance — 02:06 BST

`tools/qa_paper_control.py` passed actual API calls in an isolated PostgreSQL
schema: migration UP/DOWN/UP, default pause, resume/pause readback, two audit rows,
missing-control GET/POST refusal. All schema changes rolled back. Used task-owned
source copy in `/tmp/paper-control-qa`, not the running service's source modules.

Updated `tools/qa_managed_paper_api.py` creates its own temporary paused control
row, verifies paused entry returns 409 without a position, unpauses only that
temporary row, opens with live market quotes, then pauses it again before closing.
Passed with fixture opportunity, entry 76784.3538, operator close 76752.6464,
unchanged evidence and duplicate prevention. All temporary rows rolled back;
public entry control/portfolio untouched. No real trade or performance claim.

Migration 026 and source are still not deployed. Next: concurrency/lock acceptance,
UI pause/resume confirmation and initial paused-state deployment. The previous
full API suite passed 180 tests; no new production code changed in this QA slice.
E: 342 GB free; dirty work preserved; no secret, send, wallet, commit or push.

14 September 2026, 02:02–02:04 BST. Codex / Axiom-Codex; preserved shared dirty
checkout, E: 342 GB free. Project-local activity record only.

Migration 026 proposes a singleton persistent entry-pause state (default paused)
and separate control-change audit rows. GET/POST paper-control routes expose and
change it with a meaningful reason. Entry admission reads the state under the
same PostgreSQL advisory transaction lock as control changes. Missing state or
anything other than explicit unpaused refuses new entries. Duplicate source
requests still return their existing position rather than creating another.

Pause is not liquidation: ongoing observations, normal stop/target/time exits
and operator closes remain independent. This is not yet capital accounting,
drawdown/exposure limits or a complete emergency close workflow. No migration or
deployment performed; existing runtime is unchanged. No new control authority
has been configured. Remote API/session security review remains a separate gate.

Tests added for missing-state refusal, truthful paused readback and blank-reason
rejection; full API regression result recorded in task output. Next: isolated
SQL/API persistence and serialized admission acceptance, UI confirmation and
status, then apply migration/deploy with explicit initial paused readback. Update
paper API QA to create its own isolated control state; never unpause public
controls as a fixture setup shortcut.

No real entry/close, wallet, secret, message, commit or push. Full integration
goal remains active; this foundation does not claim unattended readiness.

[Documentation index](../README.md) · [Roadmap](../../roadmap.md) ·
[Consolidated handover](../HANDOVER_2026-09-14_INTEGRATION_STATE.md).
