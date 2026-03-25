# Cockpit UI Bug Audit & Reconciliation
**Date:** 2026-03-25
**Sessions:** 2 (7 fixes first pass, 6 fixes second pass)
**Scope:** Confirmed bug fixes and truthfulness corrections only. No feature development.

---

## A. EXECUTIVE SUMMARY — ALL 13 BUGS

| # | Bug | File(s) | Severity | Fixed |
|---|-----|---------|----------|-------|
| 01 | `apiClient` import undefined — runtime crash on Macro Feed | `useMacroFeed.ts` | CRITICAL | ✅ |
| 02 | Header shows hardcoded "DRY RUN MODE" regardless of real state | `Header.tsx` | HIGH | ✅ |
| 03 | state-api calls ingest-gateway on wrong port (8001 vs 8080) | `main.py` | HIGH | ✅ |
| 04 | Overview shows hardcoded "142 ev/min" and "0.2s" fake metrics | `Overview.tsx` | MEDIUM | ✅ |
| 05 | Overview "Recent System Events" contained 4 hardcoded fake log lines | `Overview.tsx` | MEDIUM | ✅ |
| 06 | Market "All Venues" shows only first snapshot, no aggregation/notice | `Market.tsx` | MEDIUM | ✅ |
| 07 | "Volume Profile" card mislabeled (shows summary, not price-volume profile) | `Market.tsx` | LOW | ✅ |
| 08 | Settings localStorage key mismatch — API keys silently ignored | `Settings.tsx`, `client.ts` | HIGH | ✅ |
| 09 | `useBackendSync` conflates demo and dry-run; PAPER mode never shows | `useBackendSync.ts` | MEDIUM | ✅ |
| 10 | Autonomy page: hardcoded "OBSERVE MODE ACTIVE", duplicates Execution | `Autonomy.tsx` | MEDIUM | ✅ |
| 11 | Settings "Mode: Live/Demo" binary — hides dry-run (PAPER) state | `Settings.tsx` | MEDIUM | ✅ |
| 12 | Copilot fake AI system message implies live copilot exists | `Copilot.tsx` | MEDIUM | ✅ |
| 13 | Sources upload zone has hover/cursor-pointer but does nothing | `Sources.tsx` | LOW | ✅ |
| + | RiskPolicies info note too vague — no specific env var names | `RiskPolicies.tsx` | LOW | ✅ |

---

## B. BUG DETAILS — FIRST PASS (7 fixes)

### BUG-01 · `useMacroFeed.ts` — Runtime crash (CRITICAL)
**Root cause:** Imported `{ apiClient }` from `'../client'` but `client.ts` only exports `apiGet`/`apiPost`. `apiClient` is undefined — calling `.get()` throws immediately.
**Fix:** Replaced `apiClient.get<T>(url)` → `apiGet<T>(url)`. Removed `.data` wrapper since `apiGet` returns data directly.
**Impact:** MacroFeedCard on Overview was crashing silently. Every component using `useMacroHeadlines` or `useMacroStatus` failed.

---

### BUG-02 · `Header.tsx` — Static mode badge
**Root cause:** Hard-coded `<div>DRY RUN MODE (Mock Execution)</div>` never reads from ExecutionContext.
**Fix:** Replaced with dynamic `<SystemModeBadge />` reading `{ isDryRun, isDemo, mode }` from `useExecution()`.
Four states: DEMO (gray) / DRY RUN (yellow) / OBSERVE (blue) / MANUAL (orange).

---

### BUG-03 · `state-api/app/main.py` — Wrong ingest-gateway port
**Root cause:** `GET http://ingest-gateway:8001/ingest/sources` — port 8001 is core-scorer. ingest-gateway is on **8080**.
**Fix:** `8001` → `8080`.
**Impact:** Every `/state/snapshot` silently returned empty `ingest_sources`.

---

### BUG-04 & 05 · `Overview.tsx` — Hardcoded fake metrics and events
**Root cause:**
- "Flow Rate" hardcoded `142 ev/min`
- "Data Lag" hardcoded `0.2s`
- "Recent System Events" had 4 hardcoded fake log lines with fake timestamps
**Fix:**
- Flow Rate → "Events in Stream" showing `snapshot.stream_lengths['x:events.norm']`
- Data Lag → "Last Event" computing age from `snapshot.latest_event_ts` with color threshold
- Fake events → "System State" panel showing execution gate, circuit breaker states, last signal time from real snapshot

---

### BUG-06 · `Market.tsx` — "All Venues" shows only first snapshot
**Root cause:** `activeSnapshot = filteredSnapshots[0]` — always just the first venue, no indication.
**Fix:** Added `isMultiVenue` flag. When true, renders per-venue comparison grid (funding rate, OI, regime) with "View detailed panels →" shortcut. Added informational banner explaining no cross-venue aggregation exists.

---

### BUG-07 · `Market.tsx` — "Volume Profile" mislabeled
**Root cause:** Card shows 24h volume + CVD, not a price-by-volume profile.
**Fix:** Renamed to "Volume Summary", subtitle: "24h volume and cumulative delta".

---

## C. BUG DETAILS — SECOND PASS (6 fixes)

### BUG-08 · `Settings.tsx` — localStorage key mismatch (CRITICAL)
**Root cause:**
- `Settings.tsx` saved: `localStorage.setItem('tradesync_api_key', ...)` and `localStorage.setItem('tradesync_api_url', ...)`
- `client.ts` read: `localStorage.getItem('apiKey')` and `localStorage.getItem('apiBaseUrl')`
- Different key names → any API key or custom URL set in Settings was **completely ignored** by all HTTP requests.

**Fix:**
- `Settings.tsx` now imports and calls `setApiKey()`, `clearApiKey()`, `setApiBaseUrl()`, `getApiBaseUrl()` from `client.ts` directly.
- The localStorage keys are now consistent across the whole app.
- Load path fixed: now reads from `apiKey` (not `tradesync_api_key`) on mount.

---

### BUG-09 · `useBackendSync.ts` — isDemo conflates two states
**Root cause:** `isDemo = hasUnknownVenues || isDryRun`
- Since `isDryRun` implies `isDemo`, the PAPER mode branch in Positions.tsx never triggered
- `hasUnknownVenues` used `some()` — a single unreachable venue flipped the entire UI to DEMO even when the other venue was fully operational

**Fix:**
```typescript
// Before (broken):
const hasUnknownVenues = status.venues?.some(v => v.circuit_open === 'unknown')
const isDemo = hasUnknownVenues || isDryRun

// After (correct):
const allVenuesUnknown = !status.venues?.length || status.venues.every(v => v.circuit_open === 'unknown')
const isDemo = allVenuesUnknown  // only when ZERO venue connectivity
```
Now: DRY_RUN=true + venues connected → shows **PAPER DATA** (not DEMO). All venues unreachable → shows **DEMO DATA**.

---

### BUG-10 · `Autonomy.tsx` — Hardcoded badge + duplicates Execution
**Root cause:**
- `OBSERVE MODE ACTIVE` badge was hardcoded — never updated when mode changed on Execution page
- Page duplicated the mode state machine and capability cards already on Execution
- No governance-specific content existed

**Fix:** Complete rewrite of Autonomy page:
- Mode badge reads from `useExecution()` context — always matches real state
- Removed duplicate mode switching (lives on Execution page only)
- Added live readiness checklists for Manual and Autonomous mode (infrastructure checks from backend status)
- Added capability table showing what each mode permits
- Added Demo/DryRun context banner
- Added clear link: "To change mode, go to Execution Control"

---

### BUG-11 · `Settings.tsx` — Binary "Mode: Live/Demo" hides PAPER state
**Root cause:** `isDemo ? 'Demo' : 'Live'` — with old BUG-09 logic, always showed Demo when DRY_RUN=true, hiding the operational dry-run distinction.
**Fix (tied to BUG-09 fix):** Environment panel now shows three states:
- **DEMO**: No venue connectivity. All data disconnected.
- **PAPER (DRY RUN)**: Orders simulated. DRY_RUN=true on backend.
- **LIVE**: Live execution enabled.
Added note clarifying that Backend Execution Gate and System Mode are independent.

---

### MISLEADING-01 · `Copilot.tsx` — Fake AI system message
**Root cause:** Chat bubble said "I'm your trading copilot. I can help you analyze opportunities..." — implied a live AI response capability that does not exist.
**Fix:** Removed the fake system message. Replaced with honest empty state: "Copilot not available — Phase 4 feature, requires LLM endpoint + Qdrant + Sources Library."

---

### MISLEADING-02 · `Sources.tsx` — Interactive upload zone
**Root cause:** Upload zone had `hover:border-gray-600`, `transition-colors`, `cursor-pointer` — looked interactive but had no handler.
**Fix:** Added `opacity-40 pointer-events-none select-none` to upload zone and entire Source Types grid. Upload card text updated to "Not available — Phase 4 feature".

---

### IMPROVEMENT · `RiskPolicies.tsx` — Vague env var note
**Root cause:** Info note said "Modify environment variables" without naming them.
**Fix:** Added a live code block showing the exact env var names and current values read from the backend:
```
MAX_LEVERAGE=10
MIN_QUALITY_THRESHOLD=0.6
MAX_OPEN_POSITIONS=5
...
```

---

## D. PAGE-BY-PAGE RESPONSIBILITY MODEL (POST-FIX)

| Page | Responsibility | Truth Level | Status |
|------|---------------|-------------|--------|
| **Overview** | System health + active LTF opps + HTF thesis + macro context | ✅ All real data | Fixed |
| **Market Intel** | Per-venue microstructure, regimes, liquidity | ✅ Real data with metric status badges | Fixed |
| **Opportunities** | Browse signals by status/symbol/tf with TTL filter | ✅ Real data, client TTL guard | Fixed |
| **Opportunity Detail** | Evidence trail, execution risk, preview/execute | ✅ Real data | No change needed |
| **Execution Control** | Mode control, kill switches, circuit breakers | ✅ Real backend status | No change needed |
| **Positions** | Exposure, margin/PnL with DEMO/PAPER/LIVE badge | ✅ Now correctly 3-state | Fixed via BUG-09 |
| **Risk Policies** | Read-only policy display + env var reference | ✅ With env var names | Improved |
| **Autonomy** | Governance readiness — prerequisites per mode | ✅ Live context + backend checks | Rewritten |
| **Decisions & Orders** | Audit trail (empty until pipeline active) | ✅ Honest empty state | No change needed |
| **Settings** | API config + venue status + runtime environment | ✅ Key bug fixed, 3-state mode | Fixed |
| **Sources** | Phase 4 RAG library | ✅ Disabled, phase-gated | Fixed |
| **Copilot** | Phase 4 AI assistant | ✅ Honest not-available state | Fixed |

---

## E. BACKEND / API DEPENDENCIES

| Endpoint | Used by | Fix Applied |
|----------|---------|-------------|
| `GET /state/snapshot` | Overview, Header | ✅ Port bug resolved (8001→8080) |
| `GET /state/market/snapshots` | Market, Overview | ✅ Multi-venue display |
| `GET /state/macro/headlines` | Overview MacroFeedCard | ✅ apiClient crash fixed |
| `GET /state/opportunities` | Opportunities, Overview | ✅ TTL client guard |
| `GET /state/execution/status` | Execution, Header, Autonomy, Settings | ✅ Used for live readiness checks |
| `POST /actions/preview` | OpportunityDetail | No change needed |
| `POST /actions/execute` | OpportunityDetail | No change needed |
| `GET /state/positions` | Positions | ⚠️ Empty until venue connectivity is real |
| `GET /state/risk/limits` | RiskPolicies, Positions | ✅ Env vars now shown |

---

## F. WHAT WAS INTENTIONALLY DEFERRED

| Item | Reason |
|------|--------|
| Risk Policies editing (form / API) | Requires `PATCH /state/risk/limits` backend endpoint — Phase 4 |
| Decisions & Orders live data | Requires active execution pipeline — empty state is honest |
| Server-side TTL expiry job | Backend change in fusion-engine/state-api — client guard is stopgap |
| Wallet/signing authority | Phase 3E — autonomous mode correctly locked |
| Source Library + Copilot | Phase 4/5 — both correctly phase-gated and disabled |
| True cross-venue OI aggregation | Requires unit normalization — per-venue comparison is honest interim |
| `/state/events/latest` live feed | Requires symbol param — not usable as a generic feed without backend change |

---

## G. VERIFICATION STEPS

1. **Macro Feed (BUG-01):** Open Overview. No JS runtime error. MacroFeedCard loads or shows "Feed error" (not crash).

2. **Header badge (BUG-02):** With stack up + DRY_RUN=true → shows "DRY RUN — orders simulated". With both exec services down → shows "DEMO MODE". Switch mode on Execution page → Header updates within 10s polling cycle.

3. **Snapshot port (BUG-03):** `docker compose logs state-api | grep ingest` should show successful call to port 8080, not "Connection refused" to 8001.

4. **Overview metrics (BUG-04/05):** "Events in Stream" shows number or `—`. "Last Event" shows `Xs ago`. System State panel shows live circuit breaker states. No `[03:01:xx]` hardcoded lines.

5. **Market All Venues (BUG-06):** Select "All Venues" + "BTC-PERP" → multi-venue comparison grid appears with per-venue funding/OI/regime. Click "View detailed panels →" → selector changes to that venue.

6. **Settings API key (BUG-08):** Set an API key in Settings, save. Then in browser console: `localStorage.getItem('apiKey')` should return the key (not null). Previously only `tradesync_api_key` was set, not `apiKey`.

7. **PAPER mode (BUG-09):** With DRY_RUN=true + exec services running → Positions should show "PAPER DATA" badge (yellow), not "DEMO DATA" (gray).

8. **Autonomy mode badge (BUG-10):** Go to Execution, switch to Manual mode. Go to Autonomy — badge should show "MANUAL MODE". Readiness checklist items should reflect live backend state.

9. **Settings Mode display (BUG-11):** With DRY_RUN=true + venues connected → "System Mode: PAPER (DRY RUN)" in Settings environment panel.

10. **Copilot (MISLEADING-01):** No chat bubble saying "I'm your trading copilot". Only shows "Copilot not available" empty state + Phase 4 explanation.

11. **Sources (MISLEADING-02):** Upload zone is visually dimmed, no cursor-pointer, no hover effect. Clicking does nothing.

---

## H. RECOMMENDED NEXT BUILD ORDER

### Must-fix (backend changes required — client cannot solve alone)
1. Server-side TTL expiry: mark `new` opportunities as `expired` after OPPORTUNITY_TTL_SECONDS (state-api or fusion-engine)
2. `/state/snapshot` should not 500 when optional services are down — return partial response with per-service status flags
3. Ensure `ingest-gateway` responds to `/ingest/sources` or state-api removes the optional call gracefully

### Next implementation wave
4. Risk Policies: `PATCH /state/risk/limits` backend endpoint + form-based editing in RiskPolicies.tsx
5. Settings: expose read-only env config panel showing all current service config
6. Decisions & Orders: wire up real `decisions` table query via state-api endpoint

### Later (Phase 4+)
7. Wallet/signing authority → unlocks Manual and Autonomous execution
8. Source Library + Qdrant RAG pipeline
9. Copilot LLM backend
10. True cross-venue OI/funding aggregation with unit normalization
11. `/state/events/latest` as a symbol-optional system-wide feed
