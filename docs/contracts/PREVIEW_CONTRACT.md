# Preview Contract

## 1. Overview
The `/actions/preview` endpoint provides a dry-run of an execution decision, including an execution plan and a risk verdict.

## 2. Response Schema

```typescript
interface PreviewResponse {
  decision_id?: string;     // UUID if risk check passed and decision persisted
  plan: ExecutionPlan;
  risk_verdict: RiskVerdict;
  suggested_adjustments?: RiskAdjustment;
}

interface ExecutionPlan {
  action: string;           // "Market Order"
  symbol: string;           // "BTC-PERP"
  size_usd: number;
  venue: string;
  slippage_tolerance: number;
}

interface RiskVerdict {
  allowed: boolean;
  reason?: string;          // Human readable reason if blocked
  block_code?: string;      // machine readable (SPREAD_TOO_WIDE, etc.)
  execution_risk: {
    spread_bps: number;
    impact_est_bps_5k: number;
    depth_25bp: number;
    flags: string[];        // list of warnings
  };
}

interface RiskAdjustment {
  max_size_allowed?: number;
  suggested_venue?: string;
}
```
