# Phase 3C Verification Runbook

## Overview

This runbook provides step-by-step verification commands for all Phase 3C features:

1. **Market Microstructure Deriver** - Liquidity analysis from orderbook
2. **Enhanced Scoring** - Policy + structure aware scoring with breakdown
3. **Risk Guardian Extensions** - Microstructure-based blocking
4. **Liquidity Heatmap UI** - Frontend visualizations
5. **Macro Feed MVP** - RSS headline aggregation

## Prerequisites

```bash
# Start full stack
docker compose -f ops/compose.full.yml up -d

# Wait for services to be ready (10-15 seconds)
sleep 15

# Verify services are running
docker compose -f ops/compose.full.yml ps
```

## 1. Market Microstructure Deriver

### Verify Microstructure in Market Snapshots

```bash
# Get market snapshots (should include microstructure field)
curl -s http://localhost:8005/snapshots | jq '.snapshots[0].microstructure'
```

Expected output (when orderbook data available):
```json
{
  "spread_bps": 2.5,
  "mid_price": 42150.50,
  "depth_usd": {
    "10bp": 250000,
    "25bp": 580000,
    "50bp": 1200000
  },
  "impact_est_bps": {
    "1000": 1.2,
    "5000": 4.5,
    "10000": 8.3
  },
  "liquidity_score": 0.85,
  "book_heatmap": [...]
}
```

### Verify Specific Symbol

```bash
# Get microstructure for BTC
curl -s http://localhost:8005/snapshot/hyperliquid/BTC-PERP | jq '.microstructure'
```

## 2. Enhanced Scoring

### Verify Confluence in Opportunities

```bash
# Get opportunities with confluence data
curl -s http://localhost:8000/state/opportunities | jq '.[0].confluence'
```

Expected output:
```json
{
  "score_breakdown": {
    "alpha": 3.5,
    "microstructure_penalty": -0.2,
    "exposure_penalty": 0,
    "regime_bonus": 0.5,
    "final_score": 3.8,
    "notes": [...]
  },
  "execution_risk": {
    "spread_bps": 2.5,
    "impact_est_bps_5k": 4.5,
    "depth_25bp": 580000,
    "liquidity_score": 0.85,
    "flags": []
  },
  "warnings": []
}
```

### Verify Score Breakdown

```bash
# Check if scoring includes penalties/bonuses
curl -s http://localhost:8000/state/opportunities | \
  jq '.[0] | {symbol, quality, confluence: .confluence.score_breakdown}'
```

## 3. Risk Guardian Extensions

### Verify New Block Codes Available

```bash
# Get risk limits
curl -s http://localhost:8000/state/risk/limits | jq
```

### Test Preview with Microstructure Checks

```bash
# First, get an opportunity ID
OPP_ID=$(curl -s http://localhost:8000/state/opportunities?status=new | jq -r '.[0].id')

# Preview (will perform microstructure checks)
curl -s http://localhost:8000/actions/preview \
  -H "Content-Type: application/json" \
  -d "{\"opportunity_id\": \"$OPP_ID\", \"size_usd\": 1000, \"venue\": \"hyperliquid\"}" | jq
```

Expected response includes reason_code (one of):
- `OK` - All checks passed
- `SPREAD_TOO_WIDE` - Spread exceeds threshold
- `SLIPPAGE_TOO_HIGH` - Impact estimate too high
- `DEPTH_TOO_THIN` - Insufficient depth
- `LIQUIDITY_TOO_LOW` - Liquidity score below minimum
- `MARGIN_STRESS` - Margin utilization too high
- `EXPOSURE_TOO_HIGH` - Per-symbol exposure limit exceeded

### Verify Suggested Adjustments

When blocked, check for suggested_adjustments:

```bash
curl -s http://localhost:8000/actions/preview \
  -H "Content-Type: application/json" \
  -d "{\"opportunity_id\": \"$OPP_ID\", \"size_usd\": 50000, \"venue\": \"hyperliquid\"}" | \
  jq '.suggested_adjustments'
```

## 4. Liquidity Heatmap UI

### Verify Frontend Components

1. **Market Page** (`/market`):
   - [ ] Liquidity & Slippage panel visible
   - [ ] Liquidity score displayed (0-100%)
   - [ ] Spread shown in bps
   - [ ] Depth badges (10bp, 25bp, 50bp)
   - [ ] Slippage estimates ($1k, $5k, $10k)
   - [ ] Book heatmap visualization
   - [ ] REAL/PROXY/UNAVAILABLE labels

2. **Overview Page** (`/`):
   - [ ] Execution Conditions strip visible
   - [ ] BTC/ETH spread indicators
   - [ ] BTC/ETH liquidity indicators
   - [ ] ALL CLEAR / CAUTION badge

3. **Opportunity Detail Page** (`/opportunities/:id`):
   - [ ] Execution Risk box visible
   - [ ] Risk level indicator (LOW/MEDIUM/HIGH)
   - [ ] Spread, liquidity, depth, slippage metrics
   - [ ] Warning flags if any
   - [ ] Data source label

### UI Verification Commands

```bash
# Start frontend dev server
cd services/cockpit-ui && npm run dev

# Or access via production build
# Open http://localhost:3000 in browser
```

## 5. Macro Feed MVP

### Verify Headlines Endpoint

```bash
# Get macro headlines
curl -s http://localhost:8000/state/macro/headlines | jq
```

Expected output:
```json
{
  "headlines": [
    {
      "title": "Bitcoin Surges Past $45K...",
      "source": "CoinDesk",
      "category": "crypto",
      "url": "https://...",
      "sentiment": "bullish"
    }
  ],
  "status": {
    "sources_configured": 3,
    "headlines_cached": 15,
    "cache_age_seconds": 120,
    "cache_ttl_seconds": 300,
    "sources": ["Cointelegraph", "CoinDesk", "Bloomberg Crypto"]
  },
  "cached": true,
  "ts": "2025-01-23T..."
}
```

### Filter by Category

```bash
# Get only crypto headlines
curl -s "http://localhost:8000/state/macro/headlines?category=crypto" | jq '.headlines[:3]'

# Get only macro headlines
curl -s "http://localhost:8000/state/macro/headlines?category=macro" | jq '.headlines[:3]'
```

### Force Refresh

```bash
# Force refresh from sources
curl -s "http://localhost:8000/state/macro/headlines?refresh=true" | jq '.cached'
# Should return: false
```

### Check Service Status

```bash
curl -s http://localhost:8000/state/macro/status | jq
```

## Automated Tests

### Run Phase 3C Tests

```bash
# From project root
pytest tests/test_phase3c.py -v

# Run specific test
pytest tests/test_phase3c.py::test_market_snapshot_includes_microstructure -v

# Run with output
pytest tests/test_phase3c.py -v -s
```

### Expected Test Results

```
test_market_snapshot_includes_microstructure PASSED
test_microstructure_fields_structure PASSED
test_opportunity_includes_confluence PASSED
test_risk_limits_endpoint PASSED
test_preview_includes_microstructure_checks PASSED
test_macro_headlines_endpoint PASSED
test_macro_headlines_structure PASSED
test_macro_headlines_filtering PASSED
test_macro_status_endpoint PASSED
test_full_flow_with_microstructure PASSED
```

## Environment Variables

Phase 3C introduces these new environment variables:

### Market Microstructure

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_SPREAD_BPS` | 50.0 | Block if spread exceeds this |
| `MIN_DEPTH_25BP_USD` | 100000 | Minimum depth at 25bp |
| `MAX_IMPACT_BPS_5K` | 25.0 | Max slippage for $5k order |
| `MIN_LIQUIDITY_SCORE` | 0.3 | Minimum liquidity score |

### Risk Guardian

| Variable | Default | Description |
|----------|---------|-------------|
| `MARGIN_STRESS_THRESHOLD` | 0.8 | Block if margin util > this |
| `MAX_EXPOSURE_PER_SYMBOL_USD` | 25000 | Per-symbol exposure limit |

### Macro Feed

| Variable | Default | Description |
|----------|---------|-------------|
| `MACRO_FEED_CACHE_TTL` | 300 | Cache TTL in seconds |
| `MACRO_FEED_MAX_PER_SOURCE` | 10 | Headlines per source |
| `MACRO_FEED_MAX_TOTAL` | 30 | Total headlines to keep |
| `MACRO_RSS_SOURCES` | (defaults) | JSON array of sources |

## Troubleshooting

### Microstructure Shows N/A

1. Check if orderbook data is available:
   ```bash
   curl -s http://localhost:8005/snapshot/hyperliquid/BTC-PERP | jq '.orderbook'
   ```

2. Check normalizer is including sufficient depth:
   ```bash
   docker logs tradesync-market-data-1 2>&1 | grep -i orderbook
   ```

### Macro Feed Empty

1. Check RSS sources are reachable:
   ```bash
   curl -I https://cointelegraph.com/rss
   ```

2. Check for errors in logs:
   ```bash
   docker logs tradesync-state-api-1 2>&1 | grep -i macro
   ```

3. Force refresh:
   ```bash
   curl -s "http://localhost:8000/state/macro/headlines?refresh=true"
   ```

### Preview Always Blocked

1. Check execution is enabled:
   ```bash
   curl -s http://localhost:8000/state/execution/status | jq
   ```

2. Check specific reason code in preview response

3. Adjust thresholds if testing:
   ```bash
   # In compose.full.yml, add to state-api environment:
   MAX_SPREAD_BPS: "100.0"
   MIN_LIQUIDITY_SCORE: "0.1"
   ```

## Sign-off Checklist

- [ ] All pytest tests pass
- [ ] Market page shows Liquidity panel with real data
- [ ] Overview shows Execution Conditions strip
- [ ] Opportunity detail shows Execution Risk box
- [ ] Macro feed shows headlines in Overview
- [ ] Preview returns microstructure-based verdicts
- [ ] No regressions in existing /state/* endpoints
