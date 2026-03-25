# Cockpit UI Bug Audit & Reconciliation
**Date:** 2026-03-25
**Scope:** Read-only audit + targeted bug fixes only. No feature development.

---

## A. EXECUTIVE SUMMARY

The TradeSync cockpit is structurally sound — real API calls throughout, graceful degradation, proper context management. However six confirmed bugs were causing misleading or broken behavior:

1. **Runtime crash** on any Macro Feed request (`apiClient` undefined)
2. **Static "DRY RUN MODE" header** that never updated regardless of actual backend state
3. **Wrong service port** in state-api causing `/state/snapshot` to 500 on `ingest/sources` calls
4. **Hardcoded fake metrics** on Overview ("142 ev/min", "0.2s") and four hardcoded fake telemetry log lines
5. **"All Venues" showing only first venue** silently — no aggregation, no indication
6. **Expired opportunities leaking** into the "new" tab when fusion-engine hasn't marked them expired yet
7. **"Volume Profile" label** — the card shows volume summary + CVD, not a real volume profile

---

## B. BUG TRIAGE — CONFIRMED FIXES

### BUG-01 · `useMacroFeed.ts` — Runtime crash (CRITICAL)
**File:** `services/cockpit-ui/src/api/hooks/useMacroFeed.ts`
**Root cause:** Imported `{ apiClient }` from `'../client'` but `client.ts` only exports `apiGet` / `apiPost`. `apiClient` does not exist — calling `.get()` on undefined throws at runtime.
**Fix:** Replaced `apiClient.get<T>(url)` → `apiGet<T>(url)` and removed the bad import. `apiGet` returns data directly (no `.data` wrapper), so `return response.data` was also dropped.
**Impact:** MacroFeedCard on Overview was silently broken. Any component using `useMacroHeadlines` or `useMacroStatus` would crash.

---

### BUG-02 · `Header.tsx` — Static mode badge (HIGH)
**File:** `services/cockpit-ui/src/components/layout/Header.tsx`
**Root cause:** Hard-coded `<div>DRY RUN MODE (Mock Execution)</div>` — completely static, never read from `ExecutionContext`. If backend reported live mode the header still showed "DRY RUN".
**Fix:** Replaced with `<SystemModeBadge />` component that reads `{ isDryRun, isDemo, mode }` from `useExecution()` and renders one of four states:
- `DEMO MODE — no venue connectivity` (gray)
- `DRY RUN — orders simulated, no real capital` (yellow)
- `OBSERVE — read-only, execution disarmed` (blue)
- `MANUAL — live execution armed` (orange)
**Impact:** Header now consistently reflects actual backend/context state.

---

### BUG-03 · `state-api/app/main.py` — Wrong ingest-gateway port (HIGH)
**File:** `services/state-api/app/main.py` line ~467
**Root cause:** `GET http://ingest-gateway:8001/ingest/sources` — port 8001 is `core-scorer`. `ingest-gateway` binds to **8080** per `ops/compose.full.yml`.
**Fix:** `8001` → `8080`.
**Impact:** Every `/state/snapshot` call attempted a connection to the wrong service. The exception was caught silently, but `ingest_sources` was always empty in snapshot responses.

---

### BUG-04 · `Overview.tsx` — Hardcoded fake metrics (MEDIUM)
**File:** `services/cockpit-ui/src/pages/Overview.tsx`
**Root cause:**
- "Flow Rate" card showed hardcoded `142 ev/min` — a placeholder never wired to any real source
- "Data Lag" card showed hardcoded `0.2s` — a placeholder, never computed from timestamps
- "Recent System Events" section contained four hardcoded fake log lines (timestamps `[03:01:xx]`, fabricated events)

**Fix:**
- "Flow Rate" card → "Events in Stream" showing `snapshot.stream_lengths['x:events.norm']` (real Redis stream depth) or `—` if unavailable
- "Data Lag" card → "Last Event" showing computed age from `snapshot.latest_event_ts` with green/yellow/red color coding
- Fake telemetry events → replaced with a real "System State" panel showing execution gate, circuit breaker states, and last signal timestamp from actual snapshot data

---

### BUG-05 · `Market.tsx` — "All Venues" shows only first snapshot (MEDIUM)
**File:** `services/cockpit-ui/src/pages/Market.tsx`
**Root cause:** When "All Venues" is selected, `filteredSnapshots` contains all venues but `activeSnapshot = filteredSnapshots[0]` — only the first is shown with no indication. No aggregation exists anywhere.
**Fix:**
- Added `isMultiVenue` flag (true when `selectedVenue === 'all'` and multiple snapshots exist)
- When `isMultiVenue`: renders a per-venue comparison grid showing funding rate, OI, and trend regime per venue, with a "View detailed panels →" shortcut to drill into a specific venue
- Added blue info banner explaining: "Values are per-venue — no cross-venue aggregation. Select a specific venue for detailed panels."
- Single-venue detailed panel grid only renders when `!isMultiVenue`

---

### BUG-06 · `Opportunities.tsx` — Expired items leak into 'new' tab (MEDIUM)
**File:** `services/cockpit-ui/src/pages/Opportunities.tsx`
**Root cause:** Backend `state-api` fetches `WHERE status = 'new'` — no TTL check. The fusion-engine sets `OPPORTUNITY_TTL_SECONDS=900` but only marks items expired when it actively processes them. If fusion-engine is quiet, stale 'new' items accumulate.
**Fix:**
- Added client-side TTL filter: when tab is `status === 'new'`, items older than 900 seconds are hidden from the list
- Added `expiredCount` memo that tracks how many items were hidden
- Renders a dismissible notice: "N items hidden — older than 15 min TTL. Switch to the Expired tab to review them."
- `Clock` icon imported from lucide-react for the notice

---

### BUG-07 · `Market.tsx` — "Volume Profile" mislabeled (LOW)
**File:** `services/cockpit-ui/src/pages/Market.tsx`
**Root cause:** Card title says "Volume Profile" but the `VolumePanel` component shows 24h volume and Cumulative Volume Delta (CVD) — which is a volume *summary*, not a price-by-volume profile.
**Fix:** Renamed card title to "Volume Summary" and subtitle to "24h volume and cumulative delta".

---

## C. PAGE-BY-PAGE RESPONSIBILITY DEFINITIONS (POST-FIX)

| Page | Responsibility | Data Source | Status |
|------|---------------|-------------|--------|
| **Overview** | System health, active LTF opps, HTF thesis, macro context | `/state/snapshot`, `/state/opportunities`, `/state/market/snapshots`, `/state/macro/headlines` | ✅ Live data, fake metrics removed |
| **Market Intel** | Per-venue market microstructure, regimes, liquidity | `/state/market/snapshots`, `/state/market/status` | ✅ Fixed multi-venue display |
| **Opportunities** | Browse/filter signals by status/symbol/timeframe | `/state/opportunities?status=X` | ✅ TTL expiry filter added |
| **Opportunity Detail** | Evidence trail, execution risk context, preview/execute | `/state/evidence`, `/state/market/snapshot`, `POST /actions/preview`, `POST /actions/execute` | ✅ No changes needed |
| **Execution** | Mode control, kill switches, circuit breakers | `/state/execution/status` | ✅ No changes needed |
| **Positions** | Exposure snapshot, margin/PnL context | `/state/positions`, `/state/risk/limits` | ✅ No changes needed — DEMO/PAPER/LIVE badge already correct |
| **Risk Policies** | Current policy display, daily notional usage | `/state/risk/limits` | ⚠️ Deferred: needs editable policy surface (Phase 4) |
| **Autonomy** | Governance mode state machine | ExecutionContext | ✅ Correctly phase-gated. No changes needed. |
| **Decisions & Orders** | Audit trail for decisions and exec_orders | (future: `/state/decisions`) | 🔜 Currently empty because execution pipeline not active |
| **Settings** | Technical config (API URL, API key) | localStorage | ⚠️ Deferred: too thin, needs env display |
| **Sources / Copilot** | Future RAG/ingestion features | Not implemented | 🔒 Correctly phase-gated |

---

## D. WHAT WAS DEFERRED (INTENTIONALLY OUT OF SCOPE)

| Item | Reason deferred |
|------|----------------|
| Risk Policies editing (form-based) | Requires backend policy write endpoint. Phase 4 feature. |
| Decisions & Orders page content | Awaiting active execution pipeline. Empty = correct. |
| Settings page depth | Needs design decision on what belongs here vs Risk Policies. |
| Wallet/signing authority | Phase 3E/4 — autonomous mode intentionally locked. |
| Source Library / Copilot | Phase 4/5 — correctly labeled as future. |
| Backend-side TTL expiry job | Server-side fix in fusion-engine or state-api to actively mark opportunities expired. Client-side filter is a stopgap. |
| Cross-venue OI aggregation | True aggregation requires unit normalization. Multi-venue comparison grid is the honest interim solution. |
| `/state/events/latest` live feed on Overview | Requires a symbol param — not usable as a generic feed without backend change. Real system state shown instead. |

---

## E. BACKEND / API DEPENDENCIES

| Endpoint | Used by | Status |
|----------|---------|--------|
| `GET /state/snapshot` | Overview, header sync | ✅ Fixed (port bug resolved) |
| `GET /state/market/snapshots` | Market, Overview | ✅ Working |
| `GET /state/macro/headlines` | Overview MacroFeedCard | ✅ Fixed (apiClient crash resolved) |
| `GET /state/opportunities` | Opportunities, Overview | ✅ Working (TTL guard added client-side) |
| `GET /state/execution/status` | Execution, Header | ✅ Working |
| `POST /actions/preview` | OpportunityDetail | ✅ Working |
| `POST /actions/execute` | OpportunityDetail | ✅ Working (dry-run safe) |
| `GET /state/positions` | Positions | ⚠️ Returns empty until venue position fetch is wired |
| `GET /state/risk/limits` | RiskPolicies, Positions | ✅ Working |

---

## F. VERIFICATION STEPS

1. **Macro Feed** — Open Overview. MacroFeedCard should load (or show "Feed error" if RSS fetch fails). It should no longer throw a JS runtime error. Check browser console — no `TypeError: Cannot read properties of undefined (reading 'get')`.

2. **Header badge** — Start the stack. While both exec services are down, header should show `DEMO MODE`. With stack up and `DRY_RUN=true`, header should show `DRY RUN`. Toggle kill switches and confirm mode label tracks context.

3. **Snapshot port fix** — `docker compose logs state-api` should no longer show `Connection refused: exec-hl-svc` cascading from `ingest-gateway:8001` errors. Snapshot response should now include `ingest_sources`.

4. **Overview metrics** — "Events in Stream" should show a number (Redis stream depth) or `—`. "Last Event" should show a live age like `3s ago` or `2m ago`. No static values visible.

5. **Overview system state** — The telemetry panel now shows execution gate, circuit breaker state, and last signal time from real snapshot data.

6. **Market — All Venues** — Select "All Venues" + "BTC-PERP". Should see the multi-venue comparison grid with funding, OI, and regime per venue. Click "View detailed panels →" should switch selector to that venue.

7. **Opportunities TTL** — If any 'new' items exist older than 15 min, they should be hidden and a yellow notice should appear counting them. Switching to "Expired" tab should still show them (fetched from backend with `?status=expired`).

8. **Market labels** — "Volume Profile" card is now titled "Volume Summary".

---

## G. RECOMMENDED NEXT DEVELOPMENT ORDER

### 1. Must-fix (not done here — backend changes required)
- [ ] State-api: add server-side TTL expiry job (mark `new` opportunities as `expired` after 900s)
- [ ] State-api: ensure snapshot doesn't 500 when optional services are down — return partial data with clear status flags

### 2. Next implementation wave
- [ ] Risk Policies: make limits editable via form (needs `PATCH /state/risk/limits` endpoint)
- [ ] Settings page: show current env/config values read-only, API key management
- [ ] Decisions & Orders: wire up to real `exec_orders` table query

### 3. Later (Phase 4+)
- [ ] Wallet/signing authority → unlocks Manual and Autonomous execution modes
- [ ] True cross-venue OI aggregation with unit normalization
- [ ] Source Library + Copilot RAG pipeline
- [ ] `/state/events/latest` live feed (make symbol optional for system-wide feed)
