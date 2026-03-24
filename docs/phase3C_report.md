# Phase 3C: Market Microstructure & Risk Intelligence - Final Report

This document provides a comprehensive overview of the accomplishments, architectural changes, and exposed interfaces established during Phase 3C of the TradeSync project.

## 1. Objective

The primary goal of Phase 3C was to build a **Market Microstructure Intelligence Layer**: a system that derives execution-quality metrics from orderbook data, enhances scoring with structural awareness, and provides guardrails against poor execution conditions.

Key principles followed:
- **Execution Awareness**: Score opportunities not just on alpha signal but on ability to execute efficiently.
- **Transparent Risk**: Clear breakdown of why opportunities are blocked (spread, depth, slippage, exposure).
- **Suggested Adjustments**: When blocked, provide actionable recommendations (wait, resize, etc.).
- **Macro Context**: MVP macro feed for broader market awareness.

---

## 2. Infrastructure & Services

### 2.1 Market Microstructure Deriver (`services/market-data/app/processors/microstructure.py`)

A new processing module that derives execution-quality metrics from raw orderbook data:

- **Spread Calculation**: Computes spread in basis points from best bid/ask
- **Depth Analysis**: Cumulative depth at 10bp, 25bp, 50bp from mid-price
- **Impact Estimation**: Price impact for $1k, $5k, $10k orders using linear interpolation
- **Liquidity Scoring**: Composite 0-1 score based on spread and depth quality
- **Book Heatmap**: Top N price levels with size_usd for visualization

### 2.2 Enhanced Scoring Engine (`services/fusion-engine/app/scoring.py`)

A new scoring module that produces policy + structure aware scores:

**Score Components**:
| Component | Range | Description |
|-----------|-------|-------------|
| Alpha | Raw signal | Base score from core-scorer |
| Microstructure Penalty | 0 to -1.75 | Penalty for poor spread/depth/impact |
| Exposure Penalty | 0 to -1.5 | Penalty for concentration/margin stress |
| Regime Bonus | -0.3 to +0.8 | Bonus/penalty for market conditions |

**Output Structure**:
```json
{
  "score_breakdown": {
    "alpha": 3.5,
    "microstructure_penalty": -0.2,
    "exposure_penalty": 0,
    "regime_bonus": 0.5,
    "final_score": 3.8,
    "notes": ["Base alpha from signal: 3.50", "Spread penalty: -0.20 (spread 8.5 bps)"]
  },
  "execution_risk": {
    "spread_bps": 8.5,
    "impact_est_bps_5k": 12.3,
    "depth_25bp": 450000,
    "liquidity_score": 0.72,
    "flags": []
  },
  "warnings": []
}
```

### 2.3 Risk Guardian Extensions (`services/state-api/app/risk.py`)

Extended with microstructure-based blocking:

**New Block Codes**:
| Code | Threshold | Description |
|------|-----------|-------------|
| `SPREAD_TOO_WIDE` | >50 bps | Bid-ask spread too wide |
| `SLIPPAGE_TOO_HIGH` | >25 bps for $5k | Expected slippage excessive |
| `DEPTH_TOO_THIN` | <$100k at 25bp | Insufficient orderbook depth |
| `LIQUIDITY_TOO_LOW` | <0.3 | Composite liquidity score too low |
| `MARGIN_STRESS` | >80% util | Account margin under stress |
| `EXPOSURE_TOO_HIGH` | >$25k/symbol | Per-symbol exposure limit |

**Suggested Adjustments**:
When blocked, the system provides actionable recommendations:
```json
{
  "action": "WAIT",
  "condition": "spread < 50 bps"
}
```
or
```json
{
  "action": "RESIZE",
  "value": 2500,
  "note": "Reduce size to limit slippage"
}
```

### 2.4 Macro Feed MVP (`services/state-api/app/macro_feed.py`)

A simple RSS-based headline aggregator:

- **Multi-Source**: Configurable RSS sources (Cointelegraph, CoinDesk, etc.)
- **Caching**: 5-minute cache TTL to avoid excessive requests
- **Sentiment Detection**: Basic keyword-based bullish/bearish/neutral classification
- **Category Filtering**: Filter by crypto, macro, etc.

---

## 3. API Changes

### 3.1 Enhanced Opportunity Response

`GET /state/opportunities` now includes `confluence` field:

```json
{
  "id": "...",
  "symbol": "BTC-PERP",
  "quality": 75.0,
  "confluence": {
    "score_breakdown": {...},
    "execution_risk": {...},
    "warnings": []
  }
}
```

### 3.2 Enhanced Market Snapshot Response

`GET /state/market/snapshot` now includes `microstructure` field:

```json
{
  "venue": "hyperliquid",
  "symbol": "BTC-PERP",
  "microstructure": {
    "spread_bps": 2.5,
    "mid_price": 42150.50,
    "depth_usd": {"10bp": 250000, "25bp": 580000, "50bp": 1200000},
    "impact_est_bps": {"1000": 1.2, "5000": 4.5, "10000": 8.3},
    "liquidity_score": 0.85,
    "book_heatmap": [...]
  }
}
```

### 3.3 Enhanced Preview Response

`POST /actions/preview` now returns detailed reason codes and adjustments:

```json
{
  "risk_verdict": {
    "allowed": false,
    "reason_code": "SPREAD_TOO_WIDE",
    "reason": "Spread 62.5 bps exceeds maximum 50.0 bps"
  },
  "suggested_adjustments": {
    "action": "WAIT",
    "condition": "spread < 50 bps"
  }
}
```

### 3.4 New Macro Feed Endpoints

**`GET /state/macro/headlines`**
- Query params: `refresh`, `limit`, `category`
- Returns headlines with sentiment, source, category

**`GET /state/macro/status`**
- Returns service status: sources configured, cache state

---

## 4. UI Integration

### 4.1 Market Page (`/market`)

**New Liquidity & Slippage Panel**:
- Liquidity score gauge (0-100%)
- Spread badge with color coding
- Depth badges (10bp, 25bp, 50bp)
- Slippage estimates ($1k, $5k, $10k)
- Book heatmap visualization
- REAL/PROXY/UNAVAILABLE labels

### 4.2 Overview Page (`/`)

**Execution Conditions Strip**:
- BTC/ETH spread indicators
- BTC/ETH liquidity indicators
- Overall "ALL CLEAR" / "CAUTION" badge

**Macro Feed Card**:
- Live headlines with sentiment icons
- Source and category labels
- External link to full article
- Refresh button

### 4.3 Opportunity Detail Page (`/opportunities/:id`)

**Execution Risk Box**:
- Risk level indicator (LOW/MEDIUM/HIGH)
- Spread, liquidity, depth, slippage metrics
- Warning flags display
- Data source label (confluence vs live microstructure)

---

## 5. Configuration

### 5.1 New Environment Variables

| Variable | Default | Service | Description |
|----------|---------|---------|-------------|
| `MAX_SPREAD_BPS` | 50.0 | state-api, fusion-engine | Max spread before block |
| `MIN_DEPTH_25BP_USD` | 100000 | state-api, fusion-engine | Min depth at 25bp |
| `MAX_IMPACT_BPS_5K` | 25.0 | state-api, fusion-engine | Max impact for $5k |
| `MIN_LIQUIDITY_SCORE` | 0.3 | state-api, fusion-engine | Min liquidity score |
| `MARGIN_STRESS_THRESHOLD` | 0.8 | state-api | Margin util block threshold |
| `MAX_EXPOSURE_PER_SYMBOL_USD` | 25000 | state-api | Per-symbol exposure cap |
| `MACRO_FEED_CACHE_TTL` | 300 | state-api | Macro feed cache TTL |
| `MACRO_RSS_SOURCES` | (defaults) | state-api | JSON array of RSS sources |

---

## 6. Files Created/Modified

### 6.1 New Files

| Path | Purpose |
|------|---------|
| `services/market-data/app/processors/microstructure.py` | Microstructure derivation |
| `services/fusion-engine/app/scoring.py` | Enhanced scoring engine |
| `services/state-api/app/macro_feed.py` | Macro headline aggregator |
| `services/cockpit-ui/src/api/hooks/useMacroFeed.ts` | Macro feed React hook |
| `tests/test_phase3c.py` | Phase 3C test suite |
| `docs/runbooks/Phase3C_Verification.md` | Verification runbook |
| `docs/architecture/PHASE_3C_CONTEXT.md` | Architecture context |
| `docs/samples/phase3C/*` | Sample payloads |

### 6.2 Modified Files

| Path | Changes |
|------|---------|
| `services/market-data/app/models.py` | Added MicrostructureData, BookHeatmapLevel |
| `services/market-data/app/processors/snapshotter.py` | Integrated microstructure |
| `services/market-data/app/processors/normalizer.py` | Extended to 50 orderbook levels |
| `services/fusion-engine/app/worker.py` | Integrated enhanced scoring |
| `services/fusion-engine/app/db.py` | Added confluence field |
| `services/state-api/app/main.py` | Added macro endpoints, updated preview |
| `services/state-api/app/risk.py` | Added microstructure checks |
| `services/cockpit-ui/src/api/types.ts` | Added Phase 3C types |
| `services/cockpit-ui/src/pages/Market.tsx` | Added LiquidityPanel |
| `services/cockpit-ui/src/pages/Overview.tsx` | Added ExecutionConditions, MacroFeed |
| `services/cockpit-ui/src/pages/OpportunityDetail.tsx` | Added ExecutionRiskBox |

---

## 7. Testing & Verification

### 7.1 Automated Tests

```bash
pytest tests/test_phase3c.py -v
```

Tests cover:
- Microstructure in market snapshots
- Microstructure field structure
- Confluence in opportunities
- Risk limits endpoint
- Preview with microstructure checks
- Macro headlines endpoint
- Macro headlines structure and filtering
- Full flow integration

### 7.2 Manual Verification

See `docs/runbooks/Phase3C_Verification.md` for comprehensive verification steps.

---

## 8. Future Considerations

### 8.1 Not Implemented (Deferred)

- **Wallet Connect**: Phase 3E scope
- **ML-based Sentiment**: MVP uses keyword matching
- **Historical Microstructure**: Only live data, no persistence

### 8.2 Potential Enhancements

- **Order Splitting**: Automatically split large orders based on depth
- **Time-of-Day Analysis**: Liquidity patterns by time
- **Cross-Venue Arbitrage**: Compare microstructure across venues
- **Advanced Sentiment**: LLM-based headline analysis

---

## 9. Conclusion

Phase 3C establishes the foundation for execution-aware trading decisions. The system now:

1. **Derives** execution quality metrics from raw orderbook data
2. **Scores** opportunities with full transparency into alpha vs penalties
3. **Guards** against poor execution conditions with specific block codes
4. **Suggests** actionable adjustments when trades are blocked
5. **Provides** macro context through live news headlines

This creates a more robust and transparent trading system where users understand not just *what* to trade but *when* and *how* to trade it efficiently.
