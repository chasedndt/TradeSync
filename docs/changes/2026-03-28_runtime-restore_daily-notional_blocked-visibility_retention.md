# Phase 1–5: Runtime Restore, Daily Notional, Blocked Visibility, Retention

**Date:** 2026-03-28
**Phase:** 1 (daily notional enforcement) · 2 (blocked cockpit visibility) · 3 (retention cleanup) · 4 (account equity in cockpit) · 5 (pre-existing test fixes)
**Scope:** End-to-end hardening pass following Phase 3F-3

---

## Summary

### Phase 0 — Stack Restoration Assessment (documentation only)

No code changes required. Fresh bring-up procedure:
1. Copy repo to new machine.
2. `cp .env.example .env` — fill in `POSTGRES_PASSWORD`.
3. `docker compose -f ops/compose.full.yml up -d --build`
4. Schema is applied automatically via `postgres/docker-entrypoint-initdb.d` mount on first container start.
5. The `ops/scripts/bootstrap-db.ps1` script is only needed for the `compose.infra.yml` stack (infra-only, no services). When using `compose.full.yml`, skip it.

**Env vars added to `ops/compose.full.yml` `state-api` block:**
- `ACCOUNT_EQUITY_USD` — capital base for account risk load (default $50k)
- `DAILY_NOTIONAL_LIMIT` — daily order cap (default $50k)
- `OPPORTUNITY_TTL_SECONDS` — TTL for stale opportunities (default 300s)

**Env vars added to `.env.example`:**
- Same three vars above, under `# --- Account Capital & Daily Risk ---`

---

## Phase 1 — Daily Notional Enforcement

### What was wrong before

`LIMIT_DAILY` existed as a `ReasonCode` enum value but was never checked in `RiskGuardian.check()`. The `get_risk_limits()` endpoint calculated daily notional usage (`current_notional`) but:
1. The value was never passed to `risk_engine.check()` at preview time.
2. The SQL filtered `status = 'placed'`, silently excluding completed orders from the count.
3. `RiskGuardian.check()` had no `daily_notional_usd` / `daily_notional_limit` parameters.

**Result:** The daily notional limit was display-only. It appeared in the cockpit Risk Policies page and was returned by `/state/risk/limits`, but zero enforcement happened. An account could execute unlimited notional in a day.

### What was fixed

1. **`libs/tradesync_core/tradesync_core/risk.py`**:
   - Added `daily_notional_usd: float = 0.0` and `daily_notional_limit: float = 0.0` parameters to `check()`.
   - Added `LIMIT_DAILY` check after `LIMIT_POSITIONS` (check #6.5): fires when `daily_notional_limit > 0 and daily_notional_usd + size_usd > daily_notional_limit`.
   - `daily_notional_limit=0` disables the check (unconfigured default).

2. **`services/state-api/app/main.py`**:
   - Added `DAILY_NOTIONAL_LIMIT = float(os.getenv("DAILY_NOTIONAL_LIMIT", "50000.0"))` module-level constant.
   - In `preview_action()`: after `recent_decisions`, queries today's exec_orders sum:
     ```python
     daily_notional_usd = await conn.fetchval("""
         SELECT COALESCE(SUM((request->>'size_usd')::float), 0.0)
         FROM exec_orders
         WHERE created_at >= CURRENT_DATE
     """) or 0.0
     ```
   - Passes `daily_notional_usd=daily_notional_usd, daily_notional_limit=DAILY_NOTIONAL_LIMIT` to `risk_engine.check()`.
   - Fixed `get_risk_limits()` query: removed `status = 'placed'` filter — all today's orders count regardless of fill status. Also changed to `COALESCE(..., 0.0)` to avoid null math.

### DB call order in `preview_action()` (updated)

| # | Call | Returns |
|---|------|---------|
| fetchrow[0] | opportunity row | opp dict |
| fetchrow[1] | existing decision check | None or decision row |
| fetchrow[2] | latest signal | None or signal row |
| fetchval[0] | recent_decisions count | int |
| **fetchval[1]** | **daily_notional_usd** | **float (NEW)** |
| HTTP try/except | market-data + exec services | exposure data |
| fetchval[2] | INSERT decision (allowed path only) | UUID |

---

## Phase 2 — Blocked Status + Reason in Cockpit

### What was wrong before

- `blocked` was not in the status filter chips in `Opportunities.tsx` — operators had no UI path to view permanently blocked opportunities.
- When writing `blocked` status at preview time, no rejection reason was stored — the cockpit had no data to explain *why* an opportunity was blocked.
- `o.created_at` was used in `Opportunities.tsx` for TTL age calculation, but the API returns `snapshot_ts` (not `created_at`). The TTL filter silently evaluated `NaN > TTL` = false, hiding no rows and producing no visible error.
- `StatusBadge` had no `blocked` color — it would fall back to gray `bg-gray-700` (same as expired, visually ambiguous).

### What was fixed

1. **`services/state-api/app/main.py`** — blocked write-back now stores rejection in `links`:
   ```sql
   UPDATE opportunities
   SET status = 'blocked',
       links = jsonb_set(COALESCE(links, '{}'), '{rejection}', $2::jsonb, true)
   WHERE id = $1 AND status = 'new'
   ```
   Where `$2` = `{"reason_code": "DNT", "reason": "Symbol LUNA-PERP is on the Do Not Trade (DNT) list"}`.
   The rejection data travels through the existing `links` JSONB column — no schema migration needed.

2. **`Opportunities.tsx`**:
   - Added `'blocked'` to `statusOptions` — operators can now filter to view blocked opportunities.
   - Fixed `new Date(o.created_at)` → `new Date(o.snapshot_ts)` (correct field name). This fixes the silent TTL age calculation bug.

3. **`StatusBadge.tsx`**: Added `blocked: 'bg-red-950 text-red-300 border border-red-800'` — visually distinct from expired (gray) and executed (green).

4. **`OpportunityCard.tsx`**: When `status === 'blocked'` and `links.rejection` is present, renders a rejection banner below the metric grid:
   ```
   🚫 DNT  Symbol LUNA-PERP is on the Do Not Trade (DNT) list
   ```

5. **`api/types.ts`**:
   - Added `OpportunityRejection` interface: `{ reason_code: string; reason: string }`.
   - Updated `Opportunity.links` to include `rejection?: OpportunityRejection`.
   - Added `confluence?: Record<string, unknown>` to `Opportunity`.
   - Added `account_equity_usd: number` to `RiskLimitResponse`.

---

## Phase 3 — Retention / Cleanup

### New endpoint: `POST /admin/cleanup`

Deletes old terminal opportunities (`blocked` + `expired`) older than N days. Cascades to `decisions` rows via `ON DELETE CASCADE`. Never touches `executed` or `new` rows.

**Query params:**
- `days` (int, 1–365, default 30) — retention window
- `dry_run` (bool, default true) — if true, returns count without deleting

**Example:**
```bash
# Preview: how many rows would be cleaned up?
curl -X POST "http://localhost:8000/admin/cleanup?dry_run=true&days=30"
# {"dry_run": true, "would_delete": 42, "older_than_days": 30}

# Execute cleanup
curl -X POST "http://localhost:8000/admin/cleanup?dry_run=false&days=30"
# {"dry_run": false, "deleted": 42, "older_than_days": 30}
```

**Safety:** Default `dry_run=true` prevents accidental mass deletion. Always count first.

---

## Phase 4 — Account Equity Visible in Cockpit

`RiskPolicies.tsx` now shows `account_equity_usd` in the Current Limits grid and in the env vars config block at the bottom of the page. Previously this value was returned by `/state/risk/limits` but never surfaced in the UI — operators had to read source code or call the API directly to see what capital base assumption the risk engine was using.

---

## Phase 5 — Pre-existing Test Bugs Fixed

Three tests in `test_main.py` were broken against a clean environment (no Docker env vars):

| Test | Root cause | Fix |
|------|-----------|-----|
| `test_preview_action` | No `EXECUTION_ENABLED=true` patch → EXEC_DISABLED fires before risk logic | Added `@patch.dict({"EXECUTION_ENABLED": "true", "MIN_QUALITY": "1.0"})` |
| `test_preview_action_positions_unavailable_does_not_block` | Used `MOCK_OPP_ROW` (quality=25.0 < MIN_QUALITY=50.0) → MIN_QUALITY fires before exposure check | Switched to `high_quality_row` (quality=90.0) |
| `test_preview_transient_cooldown_does_not_write_blocked` | Same quality issue — MIN_QUALITY fires before COOLDOWN | Switched to `high_quality_row` |

All tests using `fetchval.side_effect` in preview tests updated to include the new daily_notional `fetchval[1]` call.

---

## fetchval.side_effect pattern guide (for future tests)

All `preview_action` tests must account for 3 fetchval calls on the happy path, 2 on the rejection path:

| Path | side_effect |
|------|-------------|
| Allowed (decision inserted) | `[recent_decisions, daily_notional_usd, decision_uuid]` |
| Rejected (no insert) | `[recent_decisions, daily_notional_usd]` |

Standard values for most tests (not testing daily notional):
```python
conn.fetchval.side_effect = [0, 0.0, str(uuid.uuid4())]  # allowed
conn.fetchval.side_effect = [0, 0.0]                      # rejected
```

---

## Tests Added

### Phase 1
| Test | Proves |
|------|--------|
| `test_preview_daily_notional_blocks_when_limit_exceeded` | $48k used + $3k order > $50k limit → LIMIT_DAILY fires |
| `test_preview_daily_notional_passes_when_below_limit` | $45k + $4k = $49k < $50k → allowed=True |
| `test_preview_daily_notional_zero_limit_disables_check` | DAILY_NOTIONAL_LIMIT=0 → LIMIT_DAILY never fires |

### Phase 2
| Test | Proves |
|------|--------|
| `test_blocked_rejection_stores_reason_in_links` | DNT blocked write stores reason_code + reason in links.rejection |

### Phase 3
| Test | Proves |
|------|--------|
| `test_cleanup_endpoint_dry_run_returns_count` | dry_run=true counts without deleting |
| `test_cleanup_endpoint_deletes_when_dry_run_false` | dry_run=false executes DELETE on blocked+expired+old rows |

---

## Files Changed

| File | Change |
|------|--------|
| `libs/tradesync_core/tradesync_core/risk.py` | Add `daily_notional_usd`/`daily_notional_limit` params; add LIMIT_DAILY check |
| `services/state-api/app/main.py` | Add `DAILY_NOTIONAL_LIMIT` constant; add daily_notional DB query in preview; pass to risk_engine.check(); store rejection in links on blocked write; fix get_risk_limits query; add `/admin/cleanup` endpoint |
| `services/state-api/tests/test_main.py` | Update all `fetchval.side_effect` patterns (add daily_notional at [1]); fix 3 broken tests; add 6 new tests |
| `ops/compose.full.yml` | Add `ACCOUNT_EQUITY_USD`, `DAILY_NOTIONAL_LIMIT`, `OPPORTUNITY_TTL_SECONDS` to state-api env |
| `.env.example` | Add same 3 vars under `# --- Account Capital & Daily Risk ---` |
| `services/cockpit-ui/src/api/types.ts` | Add `OpportunityRejection`; add `rejection?` to Opportunity.links; add `confluence?` to Opportunity; add `account_equity_usd` to RiskLimitResponse |
| `services/cockpit-ui/src/pages/Opportunities.tsx` | Add `'blocked'` to statusOptions; fix `o.created_at` → `o.snapshot_ts` |
| `services/cockpit-ui/src/components/StatusBadge.tsx` | Add `blocked` color |
| `services/cockpit-ui/src/components/OpportunityCard.tsx` | Show rejection banner when status=blocked and links.rejection present |
| `services/cockpit-ui/src/pages/RiskPolicies.tsx` | Show `account_equity_usd` in Current Limits grid and env vars block |
| `docs/changes/2026-03-28_runtime-restore_...` | This file |
| `docs/architecture/RUNTIME_RESTORE_AND_STACK_VALIDATION.md` | New: stack bring-up runbook |
| `docs/architecture/DAILY_NOTIONAL_AND_RETENTION_FLOW.md` | New: daily notional + cleanup reference |
| `docs/architecture/COCKPIT_LIFECYCLE_REASON_DATA_PATH.md` | New: blocked reason data path |

---

## Known Limitations After This Phase

1. **`DAILY_NOTIONAL_LIMIT` is computed from `exec_orders.request->>'size_usd'`** — this is the size sent at execution time, not the confirmed fill size. If the exec service uses a different size in the actual order, the count may diverge.

2. **`/admin/cleanup` is unauthenticated** — the service has no auth layer. The endpoint is protected only by `dry_run=true` default. For production use, add a shared secret or restrict network access.

3. **Blocked reason stored in `links.rejection`** — this reuses the existing JSONB column to avoid a schema migration. It is semantically a stretch (links was for related record IDs). A future migration should add a `rejection_reason jsonb` column to `opportunities`.

4. **`o.created_at` bug was in both TTL filter lines in `Opportunities.tsx`** — both replaced with `snapshot_ts`. The effect was that TTL filtering was silently disabled (no rows hidden). Fixed.
