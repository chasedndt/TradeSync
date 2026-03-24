# Phase 3A Complete - Cockpit UI Productization

**Date:** 2026-01-21
**Phase:** 3A (All Sub-phases: 3A.1 through 3A.7)

## Summary

Phase 3A delivers a fully productionized Cockpit UI with trust indicators, execution controls, and comprehensive risk visibility. All 7 sub-phases are complete.

| Sub-Phase | Description | Status |
|-----------|-------------|--------|
| 3A.1 | Cockpit Trust Patch | ✅ Complete |
| 3A.2 | Product Surfaces Shells | ✅ Complete |
| 3A.3 | Opportunity Detail Upgrades | ✅ Complete |
| 3A.4 | Overview Dashboard Fixes | ✅ Complete |
| 3A.5 | Execution Control Plane | ✅ Complete |
| 3A.6 | Settings Evolution | ✅ Complete |
| 3A.7 | Position & Risk Clarity | ✅ Complete |

---

## Phase 3A.1: Cockpit Trust Patch

### Bias & Quality Semantics (0-100%)
**Files:** `components/OpportunityCard.tsx`, `utils/metrics.ts`

- Implemented `calculateBiasStrength()` using tanh normalization: `Math.abs(Math.tanh(score / scale)) * 100`
- Quality displayed as percentage (0-100%) with color-coded progress bars
- Tooltips explaining raw model scores vs normalized display values

### Status Derived from Timestamps
**Files:** `components/OpportunityCard.tsx`, `components/StatusBadge.tsx`, `pages/Opportunities.tsx`

- 5-minute TTL constant: `OPPORTUNITY_TTL_SECONDS = 300`
- Auto-compute status from `snapshot_ts`:
  - **New**: Fresh opportunity (< 60s)
  - **Previewed**: User has viewed details
  - **Executed**: Order placed
  - **Expired**: Age > TTL
- Freshness indicators with color coding (green/yellow/red)
- Faded opacity for expired opportunities

### UI Deduplication & Multi-Timeframe Filtering
**File:** `pages/Opportunities.tsx`

- Deduplication by symbol-timeframe-direction (toggleable)
- Timeframe filter dropdown: all, 1m, 5m, 15m, 1h, 4h, 1d
- Search filter by symbol
- Status filter tabs: new, previewed, executed, expired

### Preview Verdict Panel
**File:** `components/PreviewPanel.tsx`

- EXECUTION ALLOWED / BLOCKED status with icons
- Reason code display with user-friendly explanations via `reasonCodeExplanations` mapping
- Fix suggestions for blocked trades
- Trace ID displayed as truncated decision_id
- Policy checks enumeration with PASS/FAIL status

### Dry-Run/Demo Banners & API Key Settings
**Files:** `components/DryRunBanner.tsx`, `pages/Settings.tsx`

- Three banner variants: full, compact, inline
- Separate display for: Observe Mode, DRY_RUN, DEMO flags
- API Key input with masking and save/clear functionality
- API Base URL configuration

---

## Phase 3A.2: Product Surfaces Shells

### Placeholder Pages
**Files:** `pages/Market.tsx`, `pages/Sources.tsx`, `pages/Copilot.tsx`, `pages/Autonomy.tsx`, `pages/Logs.tsx`

| Page | Purpose | Phase Target |
|------|---------|--------------|
| Market | Funding, OI, Liquidations, Volume, Spread, Macro panels | Phase 3B |
| Sources | Document upload, semantic search, RAG library | Phase 4 |
| Copilot | AI chat interface, citations, voice mode | Phase 4 |
| Autonomy | Mode state machine visualization (Observe→Manual→Autonomous) | Phase 3A |
| Logs | Decisions & Orders audit trail with filters | Phase 3A |

Each page includes contextual placeholder panels, phase badges, and feature explanations.

### Kill Switch (Global/Venue) + Mode Selector
**Files:** `pages/Execution.tsx`, `context/ExecutionContext.tsx`

- **Global Kill Switch**: Emergency stop all venues, visual "KILL ALL" / "RESUME" toggle
- **Per-Venue Kill Switches**: Independent stop/resume per venue (Drift, Hyperliquid)
- **Execution Mode Selector**: Observe / Manual / Autonomous (Autonomous locked with badge)
- State persisted to localStorage
- Backend sync via `useBackendSync` hook

---

## Phase 3A.3: Opportunity Detail Upgrades

### Trade Summary (Human-Readable)
**File:** `pages/OpportunityDetail.tsx` (lines 134-158)

```
"Model detected {direction} momentum on {symbol} using the {timeframe} candle set.
Signal strength indicates {conviction_level} conviction based on {feature_count} features.
Quality score of {quality}% reflects venue confluence..."
```

- Dynamic narrative generation based on opportunity data
- Raw model bias display
- Data freshness indicator

### EvidenceTrail with Readable Fields
**File:** `components/EvidenceTrail.tsx`

Four sections:
1. **Logic Signals**: Agent name, direction, kind, confidence %, features grid
2. **Raw Market Events**: Timestamp, source, kind, mark price, funding rate
3. **Decisions**: Decision cards with venue, risk parameters
4. **Orders**: Order cards with status, dry_run flag, response details

### Trade Plan Fields (Entry/SL/TP)
**Files:** `pages/OpportunityDetail.tsx`, `components/PreviewPanel.tsx`

- Skeleton trade plan in OpportunityDetail (placeholders until preview)
- Populated values in PreviewPanel when available:
  - Entry price
  - Stop loss (red styling)
  - Take profit (green styling)
  - Size, venue, action fields

---

## Phase 3A.4: Overview Dashboard Fixes

### Actionable Telemetry
**File:** `pages/Overview.tsx` (lines 31-71)

Replaced raw counts with meaningful metrics:
- **Flow Rate**: "142 ev/min" (events per minute)
- **Execution State**: ARMED/DISARMED indicator
- **Venues**: Per-venue status indicators
- **Data Lag**: "0.2s" freshness metric
- Stale data warning after 5 minutes (animated alert)

### Top Opportunities Queue
**File:** `pages/Overview.tsx` (lines 76-92)

- Curated LTF opportunities (one per symbol per direction)
- Limited to 6 displayed
- OpportunityCard shows: symbol, timeframe, direction, strength %, quality %, age
- Freshness indicator (Fresh/Stale/Just Now)

### Market Thesis & Macro Risk Panels
**File:** `pages/Overview.tsx` (lines 111-169)

- **HTF Thesis Card**: BTC (1D) BULLISH / ETH (1D) NEUTRAL with reasoning text
- **Macro Risk Panel**: Bloomberg/News connection placeholder

---

## Phase 3A.5: Execution Control Plane

### Decisions & Orders Log Tables
**File:** `pages/Logs.tsx`

- Tab-based structure for Decisions and Orders
- **Decisions Table**: Time, Opportunity, Venue, Verdict, Reason, Trace ID
- **Orders Table**: Time, Symbol, Side, Size, Venue, Status, Latency, Order ID
- Filters: venue, status, date range
- Empty state with helpful messaging

### Venue Connection Status
**Files:** `pages/Settings.tsx`, `pages/Execution.tsx`

- Per-venue status cards: CONNECTED / CIRCUIT OPEN / NOT CONNECTED
- Circuit breaker state display with fail count tracking
- Context-specific help text:
  - Drift: "Connect Solana wallet..."
  - Hyperliquid: "Configure API keys..."

---

## Phase 3A.6: Settings Evolution

### Dedicated /settings Page
**File:** `pages/Settings.tsx`

Four main sections:
1. **API Configuration**: API Key + Base URL input with save button
2. **Venue Connection Status**: Live status, circuit breakers, demo mode warning
3. **Danger Zone**: Clear Local Cache button
4. **Environment Info**: Mode, Backend URL, DRY_RUN flag, Execution Gate status

Settings persisted to localStorage with load/save handlers.

---

## Phase 3A.7: Position & Risk Clarity

### Data Truth Labels (Demo vs Live)
**Files:** `components/DryRunBanner.tsx`, `pages/Settings.tsx`, `pages/Positions.tsx`, `context/ExecutionContext.tsx`

- Three distinct labels:
  - **DEMO** (gray): Simulated positions/balances
  - **PAPER** (yellow): DRY_RUN mode, no real capital
  - **LIVE** (green): Real trading enabled
- ExecutionContext tracks `isDryRun` and `isDemo` separately
- Prominent badge in Positions page header: `{dataMode} DATA`
- Demo Mode warning banner with explanation

### Exposure Summary
**File:** `pages/Positions.tsx` (new Exposure Summary card)

- **Total Notional**: Sum of all position `size_usd`
- **Position Count**: Current vs max allowed from risk limits
- **Daily Usage Bar**: Visual progress bar showing `daily_notional_usage / daily_notional_limit`
  - Green: < 70%
  - Yellow: 70-90%
  - Red: > 90%
- Usage percentage label

### Margin Context
**File:** `pages/Positions.tsx` (new Margin Context card)

- **Average Leverage**: Weighted by position size (`Σ(leverage × size) / total_exposure`)
  - Warning color when > 80% of max leverage
  - Max leverage allowed shown below
- **Total PnL**: With ROI percentage (`pnl / exposure × 100`)
- **Risk Status Indicator**:
  - "Position limit reached" (red)
  - "Near daily limit" (red)
  - "High leverage exposure" (yellow)
  - "Within risk parameters" (green)

---

## Verification

```bash
# Build the UI
cd services/cockpit-ui && npm run build

# Expected: SUCCESS with no TypeScript errors
```

---

## Files Changed (Phase 3A Complete)

### Created
| File | Description |
|------|-------------|
| `docs/contracts/OPPORTUNITY_CONTRACT.md` | API contract documentation |
| `docs/samples/*.json` | Captured API responses |
| `src/components/DryRunBanner.tsx` | Simulation mode indicators |
| `src/context/ExecutionContext.tsx` | Centralized execution state |
| `src/context/index.ts` | Context exports |
| `src/api/hooks/useBackendSync.ts` | Backend state synchronization |
| `src/pages/Market.tsx` | Market Intel placeholder |
| `src/pages/Sources.tsx` | RAG Sources placeholder |
| `src/pages/Copilot.tsx` | AI Copilot placeholder |
| `src/pages/Autonomy.tsx` | Autonomy Control |
| `src/pages/Logs.tsx` | Decisions & Orders audit |
| `src/pages/Settings.tsx` | Configuration page |

### Modified
| File | Changes |
|------|---------|
| `src/components/OpportunityCard.tsx` | Bias/quality semantics, status derivation, freshness |
| `src/components/EvidenceTrail.tsx` | Readable fields, feature summaries, type fixes |
| `src/components/PreviewPanel.tsx` | Verdict display, reason codes, trace ID |
| `src/components/StatusBadge.tsx` | All status types support |
| `src/components/index.ts` | New component exports |
| `src/pages/Execution.tsx` | Kill switches, mode selector, context integration |
| `src/pages/Overview.tsx` | Telemetry metrics, HTF thesis, macro panels |
| `src/pages/Opportunities.tsx` | Deduplication, filtering, DryRunBanner |
| `src/pages/OpportunityDetail.tsx` | Trade summary, trade plan fields, DryRunBanner |
| `src/pages/Positions.tsx` | **Exposure Summary, Margin Context, Data Truth labels** |
| `src/pages/index.ts` | New page exports |
| `src/api/hooks/index.ts` | New hook exports |
| `src/App.tsx` | Routes, useBackendSync hook |
| `src/main.tsx` | ExecutionProvider wrapper |
| `src/utils/metrics.ts` | calculateBiasStrength with tanh |

---

## API Dependencies

### Existing Endpoints Used
- `GET /state/snapshot` - System state, venue status, circuit breakers
- `GET /state/opportunities` - Opportunities list with filtering
- `GET /state/evidence?opportunity_id={id}` - Full evidence chain
- `GET /state/positions?venue={venue}` - Open positions
- `GET /state/risk/limits` - Risk parameters and daily counters
- `GET /state/execution/status` - Execution gate and venue states
- `POST /actions/preview` - Trade plan preview
- `POST /actions/execute` - Execute decision

### Response Structures
See `docs/contracts/OPPORTUNITY_CONTRACT.md` for full schema documentation.

---

## What's Next

### Phase 3B: Market Data Expansion
- [ ] Funding regime detection
- [ ] OI delta tracking
- [ ] Liquidation heatmaps
- [ ] Volume/CVD analysis
- [ ] Orderbook depth

### Phase 3C: Scoring Upgrades
- [ ] Liquidity/slippage guards
- [ ] Regime shift detection
- [ ] Exposure-aware scoring

### Phase 4: AI & RAG
- [ ] AI Copilot integration
- [ ] Sources/RAG knowledge base
- [ ] Natural language trade explanations

---

## Known Issues Addressed

| Issue | Status | Resolution |
|-------|--------|------------|
| "Opportunity not found" detail view | ✅ Fixed | Evidence hook with proper error handling |
| Stale opportunity labels (2hr old as "New") | ✅ Fixed | TTL-based expiration in OpportunityCard |
| Real-time data latency | ✅ Fixed | Optimized polling intervals in hooks |

---

*Phase 3A is 100% complete. Ready to proceed to Phase 3B.*
