# Phase 3A.1 - Cockpit Trust Patch

**Date:** 2026-01-21
**Phase:** 3A.1 (Cockpit Trust Patch)

## Summary

Completed the Phase 3A productization fixes for the TradeSync Cockpit UI. The main goals were:
1. Fix bias/quality semantics to display meaningful metrics
2. Add proper status derivation from timestamps
3. Implement execution modes and kill switches
4. Create proper Settings page
5. Add skeleton pages for future features

---

## Changes Made

### 1. API Contract Documentation
**Files:**
- `docs/contracts/OPPORTUNITY_CONTRACT.md` - Comprehensive API contract documentation
- `docs/samples/snapshot.json` - Captured snapshot response
- `docs/samples/opportunities.json` - Captured opportunities list
- `docs/samples/evidence_*.json` - Captured evidence responses
- `docs/samples/preview_*.json` - Captured preview responses

**Key Findings:**
- `bias` is a raw model score (e.g., -2.5 to +2.5), NOT a percentage
- `quality` is 0-100 (confidence * 100), already normalized
- No `expires_at` field - must compute from `snapshot_ts` + TTL
- Only `1m` timeframe currently emitted (pipeline limitation)

### 2. Bias/Quality Semantics Fix
**File:** `services/cockpit-ui/src/components/OpportunityCard.tsx`

- Added visual progress bars for Strength and Quality
- Added tooltips explaining raw model scores
- Changed display to `biasStrength.toFixed(0)%` (removes decimal noise)
- Color-coded quality bar (green for >= 50%, yellow otherwise)

### 3. Status Derivation from Timestamps
**File:** `services/cockpit-ui/src/components/OpportunityCard.tsx`

- Implemented 5-minute TTL constant: `OPPORTUNITY_TTL_SECONDS = 300`
- Auto-compute `expired` status when `ageSec > TTL`
- Added freshness indicators:
  - Green: < 60 seconds (fresh)
  - Yellow + warning icon: > 180 seconds (stale)
- Faded opacity for expired opportunities

### 4. Execution Page - Modes + Kill Switch + Logs
**File:** `services/cockpit-ui/src/pages/Execution.tsx`

**New Features:**
- **Execution Mode Selector:**
  - Observe (read-only)
  - Manual (requires confirmation)
  - Autonomous (locked - requires wallet config)

- **Global Kill Switch:**
  - Emergency stop for all venues
  - Visual indicator when active

- **Per-Venue Kill Switches:**
  - Independent stop/resume per venue
  - Disabled when global kill is active

- **Decisions & Orders Log Preview:**
  - Placeholder for recent activity
  - Link to full logs page

### 5. Settings Page
**File:** `services/cockpit-ui/src/pages/Settings.tsx` (new)

**Features:**
- TradeSync API Key configuration (stored in localStorage)
- API Base URL configuration
- Venue connection status display
- Clear cache functionality
- Environment info display (mode, DRY_RUN status, version)

### 6. Skeleton Pages (Product Surfaces)
**New Files:**
- `services/cockpit-ui/src/pages/Market.tsx` - Market Intel (Phase 3B)
- `services/cockpit-ui/src/pages/Sources.tsx` - RAG Sources Library (Phase 4)
- `services/cockpit-ui/src/pages/Copilot.tsx` - AI Copilot (Phase 4)
- `services/cockpit-ui/src/pages/Autonomy.tsx` - Autonomy Control
- `services/cockpit-ui/src/pages/Logs.tsx` - Decisions & Orders audit trail

Each page includes:
- Contextual placeholder panels
- Phase indicator badge
- Feature explanations
- Visual structure matching final design intent

### 7. App Routes Updated
**File:** `services/cockpit-ui/src/App.tsx`

All placeholder routes replaced with actual page components.

### 8. Bug Fixes
- Fixed TypeScript errors in `EvidenceTrail.tsx` (type casting for payload fields)
- Fixed unused import warnings in `Overview.tsx`
- Fixed JSX entity issue in Overview telemetry display (`->` to `&rarr;`)

---

## Verification

```bash
# Build the UI
cd services/cockpit-ui && npm run build

# Result: SUCCESS
# Output:
# - dist/index.html        0.45 kB
# - dist/assets/index-*.css  21.89 kB
# - dist/assets/index-*.js  296.58 kB
```

---

## What's Next

### Phase 3A.2 - Remaining Items
- [ ] Wire kill switches to backend API (currently UI-only)
- [ ] Implement mode persistence (localStorage or backend)
- [ ] Add dry-run banner to Opportunity Detail preview

### Phase 3B - Market Data Expansion
- Funding regime detection
- OI delta tracking
- Liquidation heatmaps
- Volume/CVD analysis
- Orderbook depth

### Phase 3C - Scoring Upgrades
- Liquidity/slippage guards
- Regime shift detection
- Exposure-aware scoring

---

## Files Changed

| File | Change Type |
|------|-------------|
| `docs/contracts/OPPORTUNITY_CONTRACT.md` | Updated |
| `docs/samples/*.json` | Created |
| `services/cockpit-ui/src/components/OpportunityCard.tsx` | Modified |
| `services/cockpit-ui/src/components/EvidenceTrail.tsx` | Fixed |
| `services/cockpit-ui/src/pages/Execution.tsx` | Rewritten |
| `services/cockpit-ui/src/pages/Settings.tsx` | Created |
| `services/cockpit-ui/src/pages/Market.tsx` | Created |
| `services/cockpit-ui/src/pages/Sources.tsx` | Created |
| `services/cockpit-ui/src/pages/Copilot.tsx` | Created |
| `services/cockpit-ui/src/pages/Autonomy.tsx` | Created |
| `services/cockpit-ui/src/pages/Logs.tsx` | Created |
| `services/cockpit-ui/src/pages/Overview.tsx` | Fixed |
| `services/cockpit-ui/src/pages/index.ts` | Updated |
| `services/cockpit-ui/src/App.tsx` | Updated |
