# Cockpit Build Unblock — Contract Alignment

**Date:** 2026-03-29
**Scope:** TypeScript compile errors blocking `docker compose -f ops/compose.full.yml up -d --build`

---

## Summary

The build failed at `services/cockpit-ui → RUN npm run build` with 6 TypeScript errors across 4 files. All errors were frontend-side mismatches against the real backend contract — wrong field names, an illegal interface extension, a missing undefined guard, and an unused import. No backend changes were required.

---

## Errors Fixed

### 1. `TS2339` — `circuit_drift` / `circuit_hl` do not exist on `SnapshotResponse`
**File:** `src/pages/Overview.tsx` (lines 378–386)

**Root cause:** Two compounding bugs in the same block:
- Wrong field names: `snapshot.circuit_drift` / `snapshot.circuit_hl` — these do not exist.
- The real backend fields (and the matching `types.ts` interface) use `drift_circuit` / `hl_circuit`.
- Wrong comparison logic: code compared the entire `CircuitStatus` object with `=== false`/`=== true`, treating it as a boolean. The real type is `CircuitStatus | null`; the boolean lives at `circuit_open` inside it.

**Fix:** Renamed both field references and descended into `.circuit_open`:
```diff
- snapshot.circuit_drift === false
+ snapshot.drift_circuit?.circuit_open === false
- snapshot.circuit_hl === false
+ snapshot.hl_circuit?.circuit_open === false
```

### 2. `TS2430` — `OpportunityWithConfluence` incorrectly extends `Opportunity`
**File:** `src/api/types.ts` (line 353)

**Root cause:** `Opportunity.confluence` is typed `Record<string, unknown>` (a generic JSONB passthrough). `OpportunityWithConfluence` tried to narrow it to `Confluence` via `extends`. TypeScript rejects this: `Confluence` has no index signature, so it is not a subtype of `Record<string, unknown>` in a structural sense, making the extension illegal (TS2430).

**Fix:** Changed from `interface … extends` to a `type` alias using `Omit` + intersection:
```diff
- export interface OpportunityWithConfluence extends Opportunity {
-   confluence?: Confluence
- }
+ export type OpportunityWithConfluence = Omit<Opportunity, 'confluence'> & { confluence?: Confluence }
```
`Omit` removes the conflicting property from the base, the intersection adds it back with the correct type. `OpportunityWithConfluence` is only defined here and is not used elsewhere in the codebase (confirmed by grep), so changing `interface` → `type` is safe.

### 3. `TS18048` — `status.venues.length` / `status` possibly undefined (×2)
**File:** `src/pages/Autonomy.tsx` (lines 16–17)

**Root cause:** `status` is `ExecutionStatus | undefined` (React Query `data` field). The existing code used `status?.venues?.length` with `?.` but then compared the result directly with `> 0` — TypeScript sees `number | undefined > 0` as an error. Line 17 then accessed `status.venues.every(...)` without any guard at all.

**Fix:** Null-coalesced both sides:
```diff
- const allVenuesConnected = status?.venues?.length > 0 &&
-     status.venues.every(v => v.circuit_open !== 'unknown')
+ const allVenuesConnected = (status?.venues?.length ?? 0) > 0 &&
+     (status?.venues?.every(v => v.circuit_open !== 'unknown') ?? false)
```

### 4. `TS6133` — `Droplets` declared but never read
**File:** `src/pages/OpportunityDetail.tsx` (line 7)

**Root cause:** `Droplets` was imported from `lucide-react` but not referenced anywhere in the file. The icon was used in `Overview.tsx`'s `ExecutionConditionsStrip` for liquidity display, not here.

**Fix:** Removed from the import statement:
```diff
- import { AlertTriangle, ShieldCheck, TrendingUp, Info, Activity, Shield, AlertCircle, Droplets } from 'lucide-react'
+ import { AlertTriangle, ShieldCheck, TrendingUp, Info, Activity, Shield, AlertCircle } from 'lucide-react'
```

---

## Contract Alignment

### Backend `SnapshotResponse` field names (confirmed from `services/state-api/app/main.py`)
```python
class SnapshotResponse(BaseModel):
    drift_circuit: Optional[Dict[str, Any]] = None   # ← correct name
    hl_circuit: Optional[Dict[str, Any]] = None       # ← correct name
```
Frontend `types.ts` interface already had the correct names (`drift_circuit`, `hl_circuit`). `Overview.tsx` had them reversed.

### `CircuitStatus` shape
The `drift_circuit`/`hl_circuit` payload comes from the exec service circuit-status endpoint. `types.ts` types it as:
```typescript
export interface CircuitStatus {
  venue: string
  circuit_open: boolean
  fail_count: number
  last_fail_reason?: string
  last_fail_ts?: string
}
```
`circuit_open` is the boolean; comparing the parent object to `true`/`false` was always wrong.

### `Opportunity.confluence` typing
`Opportunity.confluence` remains `Record<string, unknown>` — truthful for generic JSONB from the DB. `OpportunityWithConfluence` adds a structured `Confluence` type for Phase 3C components that work with score-breakdown data, without changing the base type.

### No backend changes required
All 6 errors were frontend-only. Backend contracts are correct and unchanged.

---

## Files Changed

| File | Change |
|------|--------|
| `services/cockpit-ui/src/api/types.ts` | `OpportunityWithConfluence`: `interface extends` → `type Omit + intersection` |
| `services/cockpit-ui/src/pages/Overview.tsx` | `circuit_drift`/`circuit_hl` → `drift_circuit?.circuit_open`/`hl_circuit?.circuit_open` |
| `services/cockpit-ui/src/pages/Autonomy.tsx` | `venues.length > 0` and `status.venues.every` → null-coalesced optional chaining |
| `services/cockpit-ui/src/pages/OpportunityDetail.tsx` | Removed unused `Droplets` import |

---

## Verification Steps

**TypeScript type-check (tsc --noEmit):**
```
EXIT: 0  — zero errors
```
Run using Playwright's bundled Node v22.13.1 (only node available on this machine):
```bash
node node_modules/typescript/bin/tsc --noEmit
# EXIT: 0
```

**Vite production build:**
```
vite v5.4.21 building for production...
✓ 1793 modules transformed.
dist/index.html                  0.45 kB │ gzip:  0.31 kB
dist/assets/index-a7ItfeuM.css  26.04 kB │ gzip:  5.34 kB
dist/assets/index-DNxZbl5X.js  355.15 kB │ gzip: 96.22 kB
✓ built in 25.15s
```
Zero errors. This is the same build step Docker executes inside the container.

**To confirm via Docker compose, run from the project root:**
```bash
docker compose -f ops/compose.full.yml up -d --build
```

---

## Known Limitations

1. **Docker compose not run** — The Vite build was verified locally using Node v22.13.1. The Docker layer (COPY, nginx config, etc.) was not exercised. The `npm run build` step itself is confirmed clean; any remaining Docker build failure would be in infrastructure layers, not TypeScript.

2. **`SnapshotResponse` type in `types.ts` is incomplete** — The backend returns additional fields (`service_health`, `degraded`, `errors`, `snapshot_ts`) that are not in the frontend interface. These do not cause build errors because no page component accesses them via TypeScript types, but they represent a silent gap. Not fixed in this pass per the narrow scope.

3. **No integration/runtime validation** — The circuit status display in `Overview.tsx` now reads `drift_circuit?.circuit_open`. At runtime, if the exec service is down, `drift_circuit` will be `null` and the display will show `UNKNOWN`, which is correct. However, this has not been exercised against a live stack.

4. **`OpportunityWithConfluence` is defined but unused** — No page or component currently imports it. It was exported as a Phase 3C type and may be wired up in a future pass. Not removed in this pass.

---

## Next Recommended Step

Run the live stack smoke test after the Docker build succeeds:

```bash
docker compose -f ops/compose.full.yml up -d --build

BASE=http://localhost:8000
curl -s $BASE/healthz | jq .
curl -s $BASE/state/snapshot | jq '{execution_gate, degraded, errors}'
curl -s $BASE/state/risk/limits | jq '{daily_notional_limit, account_equity_usd}'
curl -s http://localhost:3000 | head -1
```

If the build passes and the stack starts, do a cockpit audit: verify that blocked opportunities display rejection banners, the circuit status row in Overview shows correct state, and the Risk Policies page shows `account_equity_usd`.

Do NOT proceed to wallet/signing/autonomous execution work until the stack is confirmed healthy under live conditions.
