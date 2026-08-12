# Explainability Data Path

**Date:** 2026-03-29
**Scope:** Score breakdown, confluence, and execution risk — from DB storage to API response to UI rendering

---

## Summary

The score/confluence system is **more complete than it appears**. All structured data (score breakdown, execution risk, warnings) is stored in the DB and returned by the API. The UI renders execution_risk and warnings but completely skips `score_breakdown`, which contains the most actionable explainability information.

---

## Full Data Flow

```
fusion-engine (worker.py)
  └─ EnhancedScorer.score()
       ├─ alpha (from signal confidence)
       ├─ microstructure_penalty (spread, depth, impact, liquidity)
       ├─ exposure_penalty (concentration, margin stress) ← ALWAYS 0 (exposure_data=None)
       ├─ regime_bonus (funding regime, OI regime, market condition)
       └─ notes[] (human-readable explanation per component)
       → stored as opportunity.confluence JSONB

state-api (/state/opportunities, /state/evidence)
  └─ returns full confluence field as dict ← DATA IS THERE

cockpit-ui (OpportunityDetail.tsx)
  ├─ execution_risk → ExecutionRiskBox ← RENDERED ✓
  ├─ warnings[] → shown in ExecutionRiskBox ← RENDERED ✓
  └─ score_breakdown → NOT RENDERED ✗
```

---

## confluence JSONB Structure

Stored in `opportunities.confluence` column. Written by `fusion-engine/app/worker.py` via `EnhancedScore.to_dict()`.

```json
{
  "score_breakdown": {
    "alpha": 3.24,
    "microstructure_penalty": -0.45,
    "exposure_penalty": 0.0,
    "regime_bonus": 0.50,
    "final_score": 3.29,
    "notes": [
      "Base alpha from signal: 3.24",
      "Spread penalty: -0.20 (spread 18.5 bps > 10 bps threshold)",
      "Depth penalty: -0.25 (depth $150K < $500K optimal)",
      "Regime bonus: +0.50 (funding negative — supports short bias)"
    ]
  },
  "execution_risk": {
    "spread_bps": 18.5,
    "impact_est_bps_5k": 2.3,
    "depth_25bp": 150000.0,
    "liquidity_score": 0.62,
    "flags": ["THIN_DEPTH"]
  },
  "warnings": [
    "Thin liquidity: depth $150K at 25bp"
  ]
}
```

**Note:** `exposure_penalty` is always `0.0` because `fusion-engine/app/worker.py` passes `exposure_data=None` to `EnhancedScorer`. This is a known gap (roadmap item 3G-7).

---

## State-API Endpoints Returning confluence

Both endpoints return the full `confluence` dict:

| Endpoint | Returns confluence? |
|----------|---------------------|
| `GET /state/opportunities` | Yes — `List[OpportunityResponse]` each with `confluence` |
| `GET /state/evidence?opportunity_id={id}` | Yes — nested under `opportunity.confluence` |

---

## Frontend Types (`types.ts`)

```typescript
export interface ScoreBreakdown {
  alpha: number
  microstructure_penalty: number
  exposure_penalty: number
  regime_bonus: number
  final_score: number
  notes: string[]
}

export interface ExecutionRisk {
  spread_bps: number
  impact_est_bps_5k: number
  depth_25bp: number
  liquidity_score: number
  flags: string[]
}

export interface Confluence {
  score_breakdown?: ScoreBreakdown
  execution_risk?: ExecutionRisk
  warnings?: string[]
}
```

The types are already correct. The data flows to the frontend. The rendering gap is purely a UI component issue.

---

## What is Currently Rendered (OpportunityDetail.tsx)

| Data | Rendered | Component |
|------|----------|-----------|
| `confluence.execution_risk.spread_bps` | YES | ExecutionRiskBox (lines 24-151) |
| `confluence.execution_risk.liquidity_score` | YES | ExecutionRiskBox |
| `confluence.execution_risk.depth_25bp` | YES | ExecutionRiskBox |
| `confluence.execution_risk.impact_est_bps_5k` | YES | ExecutionRiskBox |
| `confluence.execution_risk.flags` | YES | ExecutionRiskBox (badge per flag) |
| `confluence.warnings[]` | YES | ExecutionRiskBox (warning list) |
| `confluence.score_breakdown` | **NO** | Not rendered anywhere |
| `confluence.score_breakdown.notes[]` | **NO** | Not rendered anywhere |

---

## Minimum Viable Rendering Plan

### Component 1: ScoreBreakdownCard (highest value)

**Where to add:** `OpportunityDetail.tsx`, alongside or above `ExecutionRiskBox`

**What to show:**
```
Score Analysis
──────────────────────────────
Base Signal Alpha          +3.24
  Microstructure Penalty   -0.45   (spread/depth cost)
  Exposure Penalty          0.00   (no position data)
  Regime Alignment         +0.50   (funding supports direction)
──────────────────────────────
Enhanced Final Score       +3.29

[Show details ▼]  → expands notes[] array
```

Color coding: green for positive components, red for penalties, gray for zero.

**Data path:** `opportunity.confluence?.score_breakdown`

**TypeScript type:** Already defined as `ScoreBreakdown` in `types.ts`

---

### Component 2: Explainability Notes (foldable)

**Where to add:** Expand the existing ExecutionRiskBox OR add a collapsible section

**What to show:** The `notes[]` array from `score_breakdown`, one line each. These are already human-readable strings like "Spread penalty: -0.20 (spread 18.5 bps > 10 bps threshold)".

**Data path:** `opportunity.confluence?.score_breakdown?.notes`

---

### Component 3: Regime Contribution Context

**Where to add:** Enhance existing "Market Context" section in OpportunityDetail

**What to show:** Cross-reference the regime badges with the `regime_bonus` value. Currently the regime badges (Funding, OI, Market Condition) are displayed but their contribution to the score is not linked. Adding a small annotation like "+0.50 applied to score" makes the regime section explainable.

**Data path:** `opportunity.confluence?.score_breakdown?.regime_bonus`

---

## Known Gaps

1. **`exposure_penalty` is always 0** — fusion-engine `worker.py` passes `exposure_data=None` to `EnhancedScorer`. Fix: wire to `GET /state/positions` (roadmap item 3G-7). Until then, the penalty component in the ScoreBreakdown display will always show 0.0 with a note explaining why.

2. **`regime_bonus` notes** — The breakdown notes explain microstructure penalties in detail but may be sparse for regime bonuses depending on the scoring implementation. Verify with real data before building the regime contribution component.

3. **OpportunityCard does not show confluence** — The list view (`OpportunityCard.tsx`) shows quality score and bias but not the enhanced final score. This is a separate rendering gap and lower priority than the detail view.
