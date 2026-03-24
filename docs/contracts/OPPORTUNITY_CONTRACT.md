# TradeSync API Contract Documentation

## Overview
This document defines the actual data structures returned by the TradeSync state-api endpoints, captured from live system responses on 2026-01-21.

---

## Endpoints

### GET /state/snapshot
System health and stream status.

```json
{
  "latest_event_ts": "2026-01-21T04:13:22.568433Z",
  "latest_signal_ts": "2026-01-21T04:13:29.541102Z",
  "latest_opportunity_ts": "2026-01-21T03:01:17.813737Z",
  "execution_gate": "true",
  "drift_status": "ok",
  "hl_status": "ok",
  "drift_circuit": {
    "venue": "drift",
    "circuit_open": false,
    "consecutive_failures": 0,
    "threshold": 5
  },
  "hl_circuit": {
    "venue": "hyperliquid",
    "circuit_open": false,
    "consecutive_failures": 5,
    "threshold": 5
  },
  "stream_lengths": {
    "x:events.norm": 94352,
    "x:signals.funding": 82071
  },
  "ingest_sources": []
}
```

**Key Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `execution_gate` | string ("true"/"false") | Global execution enablement |
| `drift_status` / `hl_status` | string | Venue health: "ok" or error state |
| `*_circuit.circuit_open` | boolean | True = circuit breaker tripped |
| `stream_lengths` | object | Redis stream event counts |

---

### GET /state/opportunities
List of active trading opportunities.

```json
[
  {
    "id": "8c68acb8-b00e-4d8d-a737-9eca5d1479b1",
    "symbol": "ETH-PERP",
    "timeframe": "1m",
    "bias": -2.5,
    "quality": 25.0,
    "dir": "SHORT",
    "status": "new",
    "snapshot_ts": "2026-01-21T03:01:07.188302Z",
    "links": {
      "event_ids": ["uuid1", "uuid2", "..."]
    }
  }
]
```

**Key Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique opportunity identifier |
| `symbol` | string | Trading pair (e.g., "ETH-PERP", "BTC-PERP") |
| `timeframe` | string | Candle timeframe. **Currently only "1m"** (pipeline limitation) |
| `bias` | number | **RAW model score** (unbounded, e.g., -2.5 to +2.5). NOT a percentage. |
| `quality` | number | **RAW quality score** (0-100, derived from signal confidence * 100) |
| `dir` | string | Direction: "LONG" or "SHORT" |
| `status` | string | Status: "new", "previewed", "executed", "expired" |
| `snapshot_ts` | ISO8601 | When the opportunity was created |
| `links.event_ids` | UUID[] | Related market events |

**IMPORTANT - Semantic Clarifications:**
1. `bias` is a RAW MODEL OUTPUT, not a percentage. Use `tanh(bias/scale)` to normalize to 0-100%.
2. `quality` is already 0-100 but represents raw model confidence, not computed quality.
3. There is NO `expires_at` field - expiry must be computed from `snapshot_ts` + TTL.

---

### GET /state/evidence?opportunity_id={id}
Evidence trail for a specific opportunity.

```json
{
  "opportunity": { /* same as above */ },
  "signals": [
    {
      "id": "45ec5f70-dd94-4d4e-8f90-dae50f3c6412",
      "created_at": "2026-01-21T03:01:07.139111Z",
      "agent": "core_scorer",
      "symbol": "ETH",
      "timeframe": "1m",
      "kind": "bias_score",
      "confidence": 0.25,
      "dir": "SHORT",
      "features": {
        "score": -2.5
      }
    }
  ],
  "events": [
    {
      "id": "a9e50aa8-bdcc-4f11-b3e0-18a3651b5be9",
      "ts": "2026-01-21T02:31:44.269677Z",
      "source": "metrics",
      "kind": "market_snapshot",
      "symbol": "ETH-PERP",
      "timeframe": "1m",
      "payload": {
        "oi": "1021670.0659999996",
        "mark": "2960.6",
        "venue": "hyperliquid",
        "oracle": "2961.5",
        "volume": "2266511465.7432169914",
        "funding": "0.0000125"
      }
    }
  ],
  "decisions": [],
  "exec_orders": []
}
```

**Signal Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `agent` | string | Scoring agent name (e.g., "core_scorer") |
| `confidence` | number | 0.0-1.0, model confidence in the signal |
| `features.score` | number | Raw bias score (same as opportunity.bias) |

**Event Payload Fields (market_snapshot):**
| Field | Type | Description |
|-------|------|-------------|
| `oi` | string (number) | Open interest |
| `mark` | string (number) | Mark price |
| `oracle` | string (number) | Oracle price |
| `volume` | string (number) | 24h volume |
| `funding` | string (number) | Funding rate |
| `venue` | string | Source venue |

---

### POST /actions/preview
Simulate a trade execution to check risk gates.

**Request:**
```json
{
  "opportunity_id": "8c68acb8-...",
  "size_usd": 1000,
  "venue": "drift"
}
```

**Response:**
```json
{
  "decision_id": null,
  "plan": {
    "action": "Market Order",
    "symbol": "ETH-PERP",
    "size_usd": 1000.0,
    "venue": "drift",
    "slippage_tolerance": 0.01
  },
  "risk_verdict": {
    "allowed": false,
    "reason_code": "EXPIRED",
    "reason": "Opportunity has expired",
    "suggested_adjustment": null
  },
  "suggested_adjustments": null
}
```

**Risk Verdict Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `allowed` | boolean | Whether execution is permitted |
| `reason_code` | string | Machine-readable code: EXPIRED, SIZE_TOO_SMALL, QUALITY_TOO_LOW, etc. |
| `reason` | string | Human-readable explanation |
| `suggested_adjustment` | object? | Optional hint to fix the block |

---

## UI Display Recommendations

### Bias Strength (0-100%)
```typescript
// Already implemented in utils/metrics.ts
biasStrength = Math.abs(Math.tanh(bias / 2.0)) * 100

// Examples:
// bias = -2.5 -> 84.8%
// bias = 1.0  -> 46.2%
// bias = 3.0  -> 90.5%
```

### Quality Score (0-100%)
The raw `quality` field is already 0-100, but it only reflects model confidence.
For a more holistic quality, compute:
```typescript
quality_display = calculateQuality({
  rawQuality: opportunity.quality,
  ageSeconds: (now - snapshot_ts) / 1000,
  ttlSeconds: 300, // 5 min default TTL
  hasRiskVerdict: !!previewResult,
  isAllowed: previewResult?.risk_verdict.allowed ?? true,
  evidenceCount: signals.length + events.length,
  confluenceThreshold: 5
})
```

### Status Derivation
Status should be computed client-side from timestamps:
- `expired`: now > snapshot_ts + TTL (300s default)
- `executed`: has exec_orders with status=completed
- `previewed`: has been previewed (cached in client state)
- `new`: fresh opportunity, not yet acted upon

### Timeframe Issue
Currently the pipeline only emits `1m` opportunities. This is a backend configuration issue, not a UI bug. Multi-timeframe support requires:
1. Ingest sources polling at different intervals
2. Core-scorer processing multiple timeframe windows
3. Fusion-engine aggregating across timeframes

---

## Sample Files
- `docs/samples/snapshot.json` - Full snapshot response
- `docs/samples/opportunities.json` - Opportunities list
- `docs/samples/evidence_*.json` - Evidence for specific opportunities
- `docs/samples/preview_*.json` - Preview responses
