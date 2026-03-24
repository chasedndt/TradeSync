# Phase 3A.2 - Product Surfaces & Execution Context

**Date:** 2026-01-21
**Phase:** 3A.2 (Product Surfaces)

## Summary

Completed Phase 3A.2 productization for the TradeSync Cockpit UI. The main goals were:
1. Add dry-run/demo-mode banners across all relevant pages
2. Implement execution mode persistence via localStorage
3. Create backend sync for execution state (isDryRun, isDemo)
4. Add truthful venue connection status displays
5. Improve PreviewPanel with reason codes and fix suggestions

---

## Changes Made

### 1. ExecutionContext - Centralized State Management
**File:** `services/cockpit-ui/src/context/ExecutionContext.tsx` (new)

**Purpose:** Centralized state management for execution-related settings with localStorage persistence.

**State Shape:**
```typescript
interface ExecutionState {
  mode: 'observe' | 'manual' | 'autonomous'
  globalKillSwitch: boolean
  venueKillSwitches: Record<string, boolean>  // { drift: false, hyperliquid: false }
  isDryRun: boolean      // From backend EXECUTION_ENABLED env
  isDemo: boolean        // True when venues are not connected
}
```

**Features:**
- Persists `mode`, `globalKillSwitch`, `venueKillSwitches` to localStorage
- Key: `tradesync_execution_state`
- Autonomous mode is locked (returns early if attempted)
- Provides `canExecute` computed property: `mode !== 'observe' && !globalKillSwitch`
- Exposes `setBackendState(isDryRun, isDemo)` for backend sync

**Usage:**
```tsx
const { mode, setMode, globalKillSwitch, toggleGlobalKill, isDryRun, isDemo, canExecute } = useExecution()
```

### 2. DryRunBanner Component
**File:** `services/cockpit-ui/src/components/DryRunBanner.tsx` (new)

**Purpose:** Visual indicator for simulation/demo modes. Displays contextual warnings based on system state.

**Variants:**
| Variant | Use Case | Style |
|---------|----------|-------|
| `full` | Main pages (Execution) | Full panel with descriptions |
| `compact` | Detail pages (OpportunityDetail, PreviewPanel) | Single-line centered |
| `inline` | List pages (Opportunities) | Inline chip badges |

**Shows:**
- **Observe Mode** (blue): When `mode === 'observe'`
- **DRY_RUN** (yellow): When `isDryRun === true`
- **Demo Mode** (gray): When `isDemo === true` (no real credentials)

**Added to Pages:**
- `Execution.tsx` - full variant
- `OpportunityDetail.tsx` - compact variant
- `Opportunities.tsx` - inline variant
- `PreviewPanel.tsx` - compact variant

### 3. Backend Sync Hook
**File:** `services/cockpit-ui/src/api/hooks/useBackendSync.ts` (new)

**Purpose:** Syncs ExecutionContext with backend state from `/state/execution/status`.

**Logic:**
```typescript
// execution_enabled === "true" means DRY_RUN=false (live mode)
const isDryRun = status.execution_enabled !== 'true'

// Demo mode: venues returning "unknown" status
const hasUnknownVenues = status.venues?.some(v => v.circuit_open === 'unknown')
const isDemo = hasUnknownVenues || isDryRun
```

**Integration:**
- Called in `App.tsx` to sync on every page load
- Uses `useExecutionStatus` hook for data fetching
- Updates context via `setBackendState(isDryRun, isDemo)`

### 4. PreviewPanel Improvements
**File:** `services/cockpit-ui/src/components/PreviewPanel.tsx` (modified)

**New Features:**

**Reason Code Explanations:**
```typescript
const reasonCodeExplanations: Record<string, { title: string; fix?: string }> = {
  EXPIRED: {
    title: 'Opportunity Expired',
    fix: 'The opportunity window has closed. Wait for a new signal.'
  },
  SIZE_TOO_SMALL: { ... },
  SIZE_TOO_LARGE: { ... },
  QUALITY_TOO_LOW: { ... },
  BLACKLISTED: { ... },
  COOLDOWN_ACTIVE: { ... },
  DAILY_LIMIT_REACHED: { ... },
  SIGNAL_STALE: { ... }
}
```

**Enhanced Verdict Display:**
- Shows reason code badge when available
- User-friendly title instead of raw reason
- "How to fix" suggestion for blocked executions
- Integrated DryRunBanner
- Dynamic confirmation text based on isDryRun state

**TypeScript Fixes:**
- Removed unused `RiskBadge` import
- Fixed `plan.*` field accesses with proper null checks:
  ```typescript
  // Before (error: unknown not assignable to ReactNode)
  {plan.entry && (<div>...</div>)}

  // After (correct)
  {plan.entry != null && (<div>...</div>)}
  ```

### 5. Settings Page - Live Venue Status
**File:** `services/cockpit-ui/src/pages/Settings.tsx` (modified)

**New Features:**

**Dynamic Venue Status:**
- Fetches actual status from `/state/execution/status`
- Shows real-time connection state per venue:
  - **CONNECTED** (green): Circuit responding normally
  - **CIRCUIT OPEN** (red): Circuit breaker triggered
  - **NOT CONNECTED** (yellow): Venue unreachable
- Displays fail counts and error messages
- Shows loading spinner during fetch

**Environment Section Updated:**
| Field | Source | Display |
|-------|--------|---------|
| Mode | `isDemo` | Demo / Live |
| Backend | localStorage | URL |
| DRY_RUN | `isDryRun` | Enabled / Disabled |
| Execution Gate | `execution_enabled` | Open / Closed |

### 6. Context Integration
**File:** `services/cockpit-ui/src/main.tsx` (modified)

Wrapped app with `ExecutionProvider`:
```tsx
<ExecutionProvider>
  <App />
</ExecutionProvider>
```

### 7. App-Level Backend Sync
**File:** `services/cockpit-ui/src/App.tsx` (modified)

Added `useBackendSync()` hook call to sync state on app load:
```tsx
export default function App() {
  useBackendSync()  // Sync ExecutionContext with backend
  return (...)
}
```

---

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         Backend                                  │
│  /state/execution/status                                        │
│  ├─ execution_enabled: "true" | "false"                         │
│  └─ venues: [{ venue, circuit_open, fail_count, error }]        │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    useBackendSync Hook                          │
│  - Fetches execution status                                     │
│  - Computes isDryRun, isDemo                                    │
│  - Calls setBackendState()                                      │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   ExecutionContext                              │
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │  localStorage    │  │   Backend State   │                    │
│  │  - mode          │  │   - isDryRun      │                    │
│  │  - killSwitches  │  │   - isDemo        │                    │
│  └──────────────────┘  └──────────────────┘                    │
│                          │                                      │
│                          ▼                                      │
│              canExecute = mode !== 'observe'                    │
│                       && !globalKillSwitch                      │
└─────────────────────────┬───────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │DryRunBnr │   │Execution │   │PreviewPnl│
    │ Component│   │  Page    │   │Component │
    └──────────┘   └──────────┘   └──────────┘
```

### localStorage Schema

**Key:** `tradesync_execution_state`
```json
{
  "mode": "observe",
  "globalKillSwitch": false,
  "venueKillSwitches": {
    "drift": false,
    "hyperliquid": false
  }
}
```

Note: `isDryRun` and `isDemo` are NOT persisted - they are derived from backend state on each load.

---

## Verification

```bash
# Build the UI
cd services/cockpit-ui && npm run build

# Result: SUCCESS
# Output:
# - dist/index.html            0.45 kB
# - dist/assets/index-*.css   21.93 kB
# - dist/assets/index-*.js   305.33 kB
# ✓ built in 15.45s
```

---

## What's Next

### Phase 3A - Complete
All Phase 3A items have been implemented:
- [x] Bias/quality semantics fix (3A.1)
- [x] Status derivation from timestamps (3A.1)
- [x] Execution modes + kill switches (3A.1)
- [x] Settings page with API config (3A.1)
- [x] Skeleton pages for future features (3A.1)
- [x] Dry-run/demo banners (3A.2)
- [x] Mode persistence via localStorage (3A.2)
- [x] Backend sync for execution state (3A.2)
- [x] Venue connection status checks (3A.2)
- [x] PreviewPanel verdict improvements (3A.2)

### Phase 3B - Market Data Expansion
- [ ] Funding regime detection
- [ ] OI delta tracking
- [ ] Liquidation heatmaps
- [ ] Volume/CVD analysis
- [ ] Orderbook depth

### Phase 3C - Scoring Upgrades
- [ ] Liquidity/slippage guards
- [ ] Regime shift detection
- [ ] Exposure-aware scoring

---

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `services/cockpit-ui/src/context/ExecutionContext.tsx` | Created | Centralized execution state management |
| `services/cockpit-ui/src/context/index.ts` | Created | Context exports |
| `services/cockpit-ui/src/components/DryRunBanner.tsx` | Created | Simulation mode indicators |
| `services/cockpit-ui/src/components/index.ts` | Modified | Added DryRunBanner export |
| `services/cockpit-ui/src/api/hooks/useBackendSync.ts` | Created | Backend state synchronization |
| `services/cockpit-ui/src/api/hooks/index.ts` | Modified | Added useBackendSync export |
| `services/cockpit-ui/src/components/PreviewPanel.tsx` | Modified | Reason codes, verdict display, TS fixes |
| `services/cockpit-ui/src/pages/Execution.tsx` | Modified | Uses ExecutionContext, added DryRunBanner |
| `services/cockpit-ui/src/pages/Settings.tsx` | Modified | Live venue status, environment info |
| `services/cockpit-ui/src/pages/Opportunities.tsx` | Modified | Added DryRunBanner inline |
| `services/cockpit-ui/src/pages/OpportunityDetail.tsx` | Modified | Added DryRunBanner compact |
| `services/cockpit-ui/src/main.tsx` | Modified | Wrapped with ExecutionProvider |
| `services/cockpit-ui/src/App.tsx` | Modified | Added useBackendSync hook |

---

## API Dependencies

### GET /state/execution/status
**Used by:** `useExecutionStatus`, `useBackendSync`

**Response:**
```json
{
  "execution_enabled": "false",
  "venues": [
    {
      "venue": "drift",
      "circuit_open": false,
      "fail_count": 0
    },
    {
      "venue": "hyperliquid",
      "circuit_open": "unknown",
      "error": "Connection refused"
    }
  ]
}
```

**Interpretation:**
- `execution_enabled === "true"` → DRY_RUN=false (live trading)
- `circuit_open === "unknown"` → Venue not connected (demo mode)
- `circuit_open === true` → Circuit breaker open (error recovery)
- `circuit_open === false` → Normal operation
