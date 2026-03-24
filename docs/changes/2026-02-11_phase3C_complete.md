# Phase 3C Complete - Scoring Upgrade (Policy + Structure Aware) + Liquidity Heatmap + Macro Feed MVP

**Date:** 2026-02-11
**Phase:** 3C (All Sub-phases: 3C.0 through 3C.8)

## Summary

Phase 3C transforms TradeSync from a signal-only system into an **execution-aware trading engine**. Opportunities are now scored not just on alpha signal but on ability to execute efficiently. The system derives microstructure metrics from orderbook data, penalizes poor liquidity conditions, blocks trades on slippage/spread thresholds with human-readable reason codes, and provides a macro feed MVP for broader market awareness.

**Hard constraints honored:**
- No wallet signing/custody/connect flows (deferred to Phase 3E)
- No breaking changes to existing `/state/*` and `/actions/*` contracts — all extensions are backward compatible
- All new UI panels are truthful: labeled REAL / PROXY / UNAVAILABLE / DEMO
- Docs, contracts, and runbooks updated as part of the work

| Sub-Phase | Description | Status |
|-----------|-------------|--------|
| 3C.0 | Context Capture & Contract Truth | ✅ Complete |
| 3C.1 | Market Microstructure Deriver (backend) | ✅ Complete |
| 3C.2 | Scoring Upgrade — Policy + Structure Aware (backend) | ✅ Complete |
| 3C.3 | Risk Guardian Extensions — Slippage/Spread Guardrails (backend) | ✅ Complete |
| 3C.4 | Macro Feed MVP — RSS/Articles (backend + API) | ✅ Complete |
| 3C.5 | UI: Market Page + Overview Missing Panels (frontend) | ✅ Complete |
| 3C.6 | UI: Opportunity Detail Execution Risk Box (frontend) | ✅ Complete |
| 3C.7 | Verification + Tests | ✅ Complete |
| 3C.8 | Docs Updates | ✅ Complete |

---

## Phase 3C.0: Context Capture & Contract Truth

### 3C.0.1 — Architecture Context Document
**File:** `docs/architecture/PHASE_3C_CONTEXT.md`

Comprehensive architecture context including:
- File paths and module names for every Phase 3C touchpoint:
  - Scoring pipeline (`fusion-engine/app/scoring.py`, `fusion-engine/app/worker.py`)
  - Market snapshot shaping (`market-data/app/processors/snapshotter.py`, `normalizer.py`)
  - Orderbook parsing (`market-data/app/providers/hyperliquid.py`)
  - Risk guardian enforcement (`state-api/app/risk.py`)
  - UI Market page components (`cockpit-ui/src/pages/Market.tsx`)
- ASCII data flow diagram: `ingest → normalize → snapshot → scorer → opportunities → preview → UI`
- Current data shapes vs Phase 3C target data shapes
- Configuration reference table for all new environment variables

### 3C.0.2 — Sample Payload Dumps
**Directory:** `docs/samples/phase3C/`

Captured payloads for offline development and contract verification:

| File | Source |
|------|--------|
| `market_snapshot.json` | `GET /state/market/snapshot?venue=hyperliquid&symbol=BTC-PERP` |
| `opportunities.json` | `GET /state/opportunities` |
| `evidence_sample.json` | `GET /state/evidence?opportunity_id=<id>` |
| `preview_sample.json` | `POST /actions/preview` |
| `orderbook_raw_hyperliquid.json` | Raw Hyperliquid L2 book response |

### 3C.0.3 — Contract Updates
**Directory:** `docs/contracts/`

Updated or created:

| File | Changes |
|------|---------|
| `MARKET_CONTRACT.md` | Added `microstructure` field definition with all sub-fields |
| `PREVIEW_CONTRACT.md` | Added new block reason codes and `suggested_adjustments` field |
| `RISK_LIMITS.md` | Documented all 6 new threshold parameters with defaults |
| `OPPORTUNITY_CONTRACT.md` | Added `confluence` field with score_breakdown and execution_risk |
| `SYMBOL_NORMALIZATION.md` | No changes (stable from 3B) |

---

## Phase 3C.1: Market Microstructure Deriver (Backend)

### Goal
Convert raw orderbook data into derived microstructure fields so scoring and UI can trust a consistent shape.

### 3C.1.1 — New Derived Fields on MarketSnapshot
**File:** `services/market-data/app/models.py`

Added backward-compatible `microstructure` field to `MarketSnapshot`:

```json
{
  "microstructure": {
    "spread_bps": 2.5,
    "mid_price": 42150.50,
    "depth_usd": { "10bp": 250000, "25bp": 580000, "50bp": 1200000 },
    "impact_est_bps": { "1000": 1.2, "5000": 4.5, "10000": 8.3 },
    "liquidity_score": 0.85,
    "book_heatmap": [
      { "price": 42140.0, "side": "bid", "size_usd": 125000 },
      { "price": 42160.0, "side": "ask", "size_usd": 98000 }
    ]
  }
}
```

New Pydantic models:
- `BookHeatmapLevel`: `price`, `side` (bid/ask), `size_usd`
- `MicrostructureData`: All fields above
- `MarketSnapshot.microstructure: Optional[MicrostructureData]` (backward compatible)

### 3C.1.2 — Microstructure Derivation Logic
**File:** `services/market-data/app/processors/microstructure.py`

New `MicrostructureDeriver` class with:

| Method | Purpose |
|--------|---------|
| `derive(bids, asks)` | Main entry point — returns `MicrostructureResult` |
| `_compute_depth_slices(levels, mid, thresholds)` | Cumulative depth at ±10bp, ±25bp, ±50bp from mid |
| `_compute_impact_estimates(levels, size_buckets)` | Price impact for $1k, $5k, $10k via orderbook walk |
| `_compute_liquidity_score(spread_bps, depth_25bp)` | Composite 0-1 score (40% spread weight, 60% depth weight) |
| `_build_heatmap(bids, asks, max_levels)` | Top N price levels per side (default: 50 bid + 50 ask) |

**Scoring formula:**
```
spread_score = max(0, 1.0 - spread_bps / 5.0)
depth_score = min(1.0, depth_25bp / 3_000_000)
liquidity_score = 0.4 * spread_score + 0.6 * depth_score
```

**Truthfulness:**
- `available_metrics[]` extended with `orderbook:real|proxy|unavailable` and `microstructure:derived|unavailable`
- If venue can't provide full depth, computes what it can and marks rest as unavailable

### 3C.1.3 — Integration with Snapshotter
**File:** `services/market-data/app/processors/snapshotter.py`

- Snapshotter now calls `MicrostructureDeriver` when orderbook data is present
- Extended normalizer to pass 50 orderbook levels (up from 20) for better depth analysis
- Microstructure data attached to snapshot before publishing to Redis

---

## Phase 3C.2: Scoring Upgrade — Policy + Structure Aware (Backend)

### Goal
Opportunities stop being "funding squeeze only." Scoring becomes structure-aware and execution-aware.

### 3C.2.1 — Enhanced Scoring Module
**File:** `services/fusion-engine/app/scoring.py`

New `EnhancedScorer` class producing policy + structure aware scores.

**Dataclasses:**

```python
@dataclass
class ScoreBreakdown:
    alpha: float                    # Raw signal from core-scorer
    microstructure_penalty: float   # 0 to -1.75 penalty for poor execution conditions
    exposure_penalty: float         # 0 to -1.5 penalty for concentration/margin stress
    regime_bonus: float             # -0.3 to +0.8 for market regime alignment
    final_score: float              # alpha + all adjustments
    notes: List[str]                # Human-readable explanation of each component

@dataclass
class ExecutionRisk:
    spread_bps: float
    impact_est_bps_5k: float
    depth_25bp: float
    liquidity_score: float
    flags: List[str]                # e.g., ["SPREAD_ELEVATED", "THIN_DEPTH"]

@dataclass
class EnhancedScore:
    score_breakdown: ScoreBreakdown
    execution_risk: ExecutionRisk
    warnings: List[str]             # Human-readable warnings
```

### 3C.2.2 — Scoring Algorithm

**Score Components:**

| Component | Range | Logic |
|-----------|-------|-------|
| Alpha | Raw signal | Base score from core-scorer (funding extremes, OI deltas, volume regime, trend regime) |
| Microstructure Penalty | 0 to -1.75 | Penalizes wide spread (-2.0 max), thin depth (-1.5 max), high impact (-1.5 max) |
| Exposure Penalty | 0 to -1.5 | Penalizes symbol concentration (-0.5) and margin stress (-1.0) |
| Regime Bonus | -0.3 to +0.8 | Squeeze potential (+0.5), trend alignment (+0.3), misalignment (-0.3) |

**Final score:** `alpha + microstructure_penalty + exposure_penalty + regime_bonus`

**Microstructure penalty breakdown:**
- Spread > 50 bps: -2.0 (hard block territory)
- Spread > OPTIMAL_SPREAD_BPS (2.0): scaled penalty up to -0.5
- Depth at 25bp < MIN_DEPTH_25BP_USD (100k): -1.5
- Impact for $5k > MAX_IMPACT_BPS_5K (25.0): -1.5

**Exposure penalty breakdown:**
- Existing position in same symbol with >50% of max exposure: -0.5 concentration penalty
- Margin utilization > 80%: -1.0 margin stress penalty

**Regime bonus logic:**
- Squeeze potential (extreme funding + OI build): +0.5
- Trend alignment (same direction as trend regime): +0.3
- Trend misalignment: -0.3

**Thresholds configurable via environment variables:**
- `MAX_SPREAD_BPS` = 50.0
- `OPTIMAL_SPREAD_BPS` = 2.0
- `MIN_DEPTH_25BP_USD` = 100000
- `MAX_IMPACT_BPS_5K` = 25.0
- `MIN_LIQUIDITY_SCORE` = 0.3

### 3C.2.3 — Regime Shift Invalidation / De-prioritization

When regimes change (funding flips, OI unwind, volatility spike):
- Regime bonus goes negative (-0.3) for misaligned opportunities
- Open opportunities with stale regime context get downgraded
- Alert events emitted into market alerts stream

### 3C.2.4 — Fusion Engine Worker Integration
**File:** `services/fusion-engine/app/worker.py`

- Creates `EnhancedScorer` instance at startup
- `fetch_market_snapshot()` function retrieves microstructure data from market-data service
- Enhanced score computation in opportunity processing loop:
  1. Fetches market snapshot with microstructure for the symbol
  2. Fetches regime data
  3. Calls `enhanced_scorer.compute_enhanced_score()` with alpha, microstructure, exposure, regime
  4. Uses `final_score` from enhanced breakdown as opportunity quality
  5. Stores `confluence: enhanced_score.to_dict()` in opportunity record

**Key acceptance proof:** Same symbol + same funding/OI setup produces a lower score if spread widens or depth collapses, because the microstructure penalty increases.

---

## Phase 3C.3: Risk Guardian Extensions — Slippage/Spread Guardrails (Backend)

### Goal
Preview/Execute must block trades that are unexecutable due to poor microstructure.

### 3C.3.1 — New Block Reason Codes
**File:** `services/state-api/app/risk.py`

| Code | Threshold | Check Logic |
|------|-----------|-------------|
| `SPREAD_TOO_WIDE` | spread_bps > 50 bps (configurable via `MAX_SPREAD_BPS`) | Bid-ask spread exceeds maximum |
| `SLIPPAGE_TOO_HIGH` | impact_est_bps_5k > 25 bps (configurable via `MAX_IMPACT_BPS_5K`) | Expected price impact for $5k order is excessive |
| `DEPTH_TOO_THIN` | depth_25bp < $100k (configurable via `MIN_DEPTH_25BP_USD`) | Insufficient orderbook depth within 25bp of mid |
| `LIQUIDITY_TOO_LOW` | liquidity_score < 0.3 (configurable via `MIN_LIQUIDITY_SCORE`) | Composite liquidity score below minimum |
| `MARGIN_STRESS` | margin_utilization > 80% (configurable via `MARGIN_STRESS_THRESHOLD`) | Account margin under stress |
| `EXPOSURE_TOO_HIGH` | symbol_exposure_usd > $25k (configurable via `MAX_EXPOSURE_PER_SYMBOL_USD`) | Per-symbol exposure limit exceeded |

### 3C.3.2 — Suggested Adjustments
When a trade is blocked, the Risk Guardian returns actionable recommendations:

**WAIT action** (for transient conditions):
```json
{
  "action": "WAIT",
  "condition": "spread < 50 bps"
}
```

**RESIZE action** (for size-dependent blocks):
```json
{
  "action": "RESIZE",
  "value": 2500,
  "note": "Reduce size to limit slippage"
}
```

### 3C.3.3 — Preview Integration
**File:** `services/state-api/app/main.py`

`POST /actions/preview` enhanced (lines 817-859):
1. Fetches current market snapshot for the opportunity's symbol
2. Extracts microstructure data (spread, depth, impact, liquidity)
3. Fetches current position exposure for the symbol
4. Calculates margin utilization (simplified as notional/50k)
5. Passes all to `RiskGuardian.check()` with new parameters:
   - `microstructure`: spread_bps, depth_25bp, impact_5k, liquidity_score
   - `margin_utilization`: current margin usage ratio
   - `symbol_exposure_usd`: existing exposure in the symbol

Preview response now includes:
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

### 3C.3.4 — Risk Limits Endpoint
**File:** `services/state-api/app/main.py`

`GET /state/risk/limits` updated to include all Phase 3C threshold parameters:
- `max_spread_bps`, `min_depth_25bp_usd`, `max_impact_bps_5k`, `min_liquidity_score`
- `margin_stress_threshold`, `max_exposure_per_symbol_usd`
- Plus existing limits: `max_leverage`, `daily_notional_limit`, `max_open_positions`

---

## Phase 3C.4: Macro Feed MVP — RSS/Articles (Backend + API)

### Goal
Stop placeholder Macro panels; provide real macro/news feed that can later become Phase 4 RAG.

**Important:** This is "Macro Feed MVP", not "RAG". Full RAG is Phase 4.

### 3C.4.1 — Macro Feed Service
**File:** `services/state-api/app/macro_feed.py`

`MacroFeedService` class with:

| Feature | Implementation |
|---------|---------------|
| Multi-source RSS fetch | Async concurrent fetching from configurable RSS source list |
| Caching | 5-minute cache TTL (configurable via `MACRO_FEED_CACHE_TTL`) |
| Sentiment detection | Keyword-based bullish/bearish/neutral classification |
| Category support | Crypto, macro categories with filtering |
| Error handling | Per-source error isolation, stale cache fallback |

**Sentiment keywords:**
- Bullish: surge, rally, breakout, institutional, ETF approved, accumulation, bullish
- Bearish: crash, plunge, hack, exploit, ban, regulation, sell-off, bearish

**Default RSS sources:**
1. Cointelegraph (category: crypto)
2. CoinDesk (category: crypto)
3. Bloomberg Crypto (category: macro)

Sources configurable via `MACRO_RSS_SOURCES` environment variable (JSON array).

**Headline model:**
```python
@dataclass
class MacroHeadline:
    title: str
    source: str
    category: str       # "crypto" | "macro"
    url: str
    published_at: Optional[str]
    summary: Optional[str]
    sentiment: str       # "bullish" | "bearish" | "neutral"
```

### 3C.4.2 — API Endpoints
**File:** `services/state-api/app/main.py`

**`GET /state/macro/headlines`**
- Query params: `refresh` (bool), `limit` (int), `category` (str)
- Returns: `MacroFeedResponse` with `headlines[]`, `status`, `cached` flag, `ts`
- Category filtering: `?category=crypto` returns only crypto headlines

**`GET /state/macro/status`**
- Returns: Service status including sources configured, cache state, headline count, cache age

### 3C.4.3 — Storage Note
Headlines are cached in-memory (Python dict with TTL). Postgres persistence is deferred — the MVP serves from cache with RSS re-fetch on expiry. This is intentional for Phase 3C scope.

---

## Phase 3C.5: UI — Market Page + Overview Missing Panels (Frontend)

### Goal
Market page and Overview must show liquidity/microstructure and tie it to scoring. Macro panel must display real feed items.

### 3C.5.1 — Market Page: Liquidity & Slippage Panel
**File:** `services/cockpit-ui/src/pages/Market.tsx`

New `LiquidityPanel` component (rendered within the Market page):

| Element | Description |
|---------|-------------|
| Liquidity Score Gauge | 0-100% with color-coded progress bar (green/yellow/red) |
| Spread Badge | Color-coded: green (≤5 bps), yellow (≤20 bps), red (>20 bps) |
| Depth Badges | Three badges for 10bp, 25bp, 50bp depth in USD (K/M notation) |
| Slippage Estimates | Impact in bps for $1k, $5k, $10k order sizes |
| Book Heatmap | Table visualization of top 10 price levels (bid=green, ask=red) with size_usd |
| Source Labels | REAL / PROXY / UNAVAILABLE badges via `MetricStatusBadge` component |

### 3C.5.2 — Overview Page: Execution Conditions Strip
**File:** `services/cockpit-ui/src/pages/Overview.tsx`

New `ExecutionConditionsStrip` component:

| Element | Description |
|---------|-------------|
| BTC Spread | Current spread with health label: OK (green) / WIDE (red) |
| BTC Liquidity | Liquidity score with label: HEALTHY (green) / THIN (yellow/red) |
| ETH Spread | Same as BTC |
| ETH Liquidity | Same as BTC |
| BTC Slippage | Impact estimate with label: LOW (green) / HIGH (red) |
| ETH Slippage | Same as BTC |
| Overall Badge | "ALL CLEAR" (green) when all conditions pass, "CAUTION" (amber) otherwise |

Data sourced from `MarketSnapshotWithMicrostructure` for BTC-PERP and ETH-PERP.

### 3C.5.3 — Overview Page: Macro Feed Card
**File:** `services/cockpit-ui/src/pages/Overview.tsx`

New `MacroFeedCard` component:

| Element | Description |
|---------|-------------|
| Headlines List | Latest 5 headlines with title, source, category |
| Sentiment Icons | Colored indicators: bullish (green), bearish (red), neutral (gray) |
| External Links | Clickable URLs opening in new tab |
| Refresh Button | Manual refresh with active polling state animation |
| Cache Info | Shows cache age and source count |
| Error Handling | Error state with retry button |
| Loading State | Spinner animation during fetch |
| Empty State | "No headlines available" with explanation |

Hook: `useMacroHeadlines({ limit: 5 })` with 60-second refetch interval.

---

## Phase 3C.6: UI — Opportunity Detail Execution Risk Box (Frontend)

### Goal
Opportunity detail page shows execution risk tied to microstructure and scoring.

### 3C.6.1 — ExecutionRiskBox Component
**File:** `services/cockpit-ui/src/pages/OpportunityDetail.tsx`

Inline `ExecutionRiskBox` component (line 25) rendered after Evidence Trail (line 369):

| Element | Description |
|---------|-------------|
| Risk Level Indicator | LOW (green border) / MEDIUM (yellow border) / HIGH (red border) |
| Spread Metric | Current spread in bps, color-coded (green ≤10, yellow ≤25, red >25) |
| Depth at 25bp | USD value with K/M notation |
| Slippage Estimate | Impact for $5k in bps |
| Liquidity Score | 0-100% with color indicator |
| Warning Flags | AlertTriangle icons for execution risk flags from scoring |
| Warnings | AlertCircle icons for human-readable warnings |
| Data Source Label | "Source: confluence analysis" (from opportunity) or "Source: live microstructure" (from snapshot) |

**Risk level thresholds:**
- HIGH: flags present OR spread > 25 bps OR liquidity < 0.4 OR impact > 15 bps
- MEDIUM: spread > 10 bps OR liquidity < 0.6 OR impact > 8 bps
- LOW: otherwise

**Data priority:**
1. Confluence data from opportunity (preferred — reflects scoring-time conditions)
2. Live microstructure from market snapshot (fallback — reflects current conditions)

### 3C.6.2 — TypeScript Types
**File:** `services/cockpit-ui/src/api/types.ts`

New Phase 3C interfaces (lines 305-381):

| Type | Fields |
|------|--------|
| `BookHeatmapLevel` | price, side, size_usd |
| `MicrostructureData` | spread_bps, mid_price, depth_usd, impact_est_bps, liquidity_score, book_heatmap |
| `ExecutionRisk` | spread_bps, impact_est_bps_5k, depth_25bp, liquidity_score, flags[] |
| `ScoreBreakdown` | alpha, microstructure_penalty, exposure_penalty, regime_bonus, final_score, notes[] |
| `Confluence` | score_breakdown, execution_risk, warnings[] |
| `MacroHeadline` | title, source, category, url, published_at, summary, sentiment |
| `MacroFeedStatus` | sources_configured, headlines_cached, cache_age_seconds, cache_ttl_seconds, sources[], error |
| `MacroFeedResponse` | headlines[], status, cached, ts |
| `OpportunityWithConfluence` | Opportunity + optional confluence |
| `MarketSnapshotWithMicrostructure` | MarketSnapshot + optional microstructure |
| `MetricStatus` | 'REAL' \| 'PROXY' \| 'UNAVAILABLE' \| 'STALE' |

### 3C.6.3 — Macro Feed Hook
**File:** `services/cockpit-ui/src/api/hooks/useMacroFeed.ts`

| Hook | Endpoint | Refetch | Stale Time |
|------|----------|---------|------------|
| `useMacroHeadlines(options)` | `/state/macro/headlines` | 60s | 30s |
| `useMacroStatus()` | `/state/macro/status` | 300s | 60s |

Options: `refresh`, `limit`, `category`

Exported via `services/cockpit-ui/src/api/hooks/index.ts`.

---

## Phase 3C.7: Verification + Tests

### 3C.7.1 — Automated Test Suite
**File:** `tests/test_phase3c.py`

10 comprehensive tests:

| Test | Category | Validates |
|------|----------|-----------|
| `test_market_snapshot_includes_microstructure` | Microstructure | Snapshot has microstructure field |
| `test_microstructure_fields_structure` | Microstructure | All required sub-fields present and typed |
| `test_opportunity_includes_confluence` | Scoring | Opportunities contain confluence with score_breakdown |
| `test_risk_limits_endpoint` | Risk Guardian | Risk limits endpoint returns Phase 3C thresholds |
| `test_preview_includes_microstructure_checks` | Risk Guardian | Preview returns Phase 3C block codes |
| `test_macro_headlines_endpoint` | Macro Feed | Headlines endpoint returns valid response |
| `test_macro_headlines_structure` | Macro Feed | Headline objects have required fields |
| `test_macro_headlines_filtering` | Macro Feed | Category filtering works correctly |
| `test_macro_status_endpoint` | Macro Feed | Status endpoint returns service info |
| `test_full_flow_with_microstructure` | Integration | End-to-end: snapshot → score → preview → block |

**Valid Phase 3C reason codes tested:**
- SPREAD_TOO_WIDE, SLIPPAGE_TOO_HIGH, DEPTH_TOO_THIN
- LIQUIDITY_TOO_LOW, MARGIN_STRESS, EXPOSURE_TOO_HIGH

Usage:
```bash
pytest tests/test_phase3c.py -v
```

### 3C.7.2 — Verification Runbook
**File:** `docs/runbooks/Phase3C_Verification.md`

350-line operational runbook with:
- Step-by-step curl verification commands for every new endpoint
- Expected output formats with sample responses
- Environment variable documentation with defaults
- UI screenshot checklist:
  - Market Liquidity panel
  - Overview execution conditions strip + macro panel
  - Opportunity Detail execution risk box
  - Preview block with reason codes
- Troubleshooting section for common issues
- Sign-off checklist for Phase 3C completion

---

## Phase 3C.8: Docs Updates

### Updated Documents

| File | Changes |
|------|---------|
| `docs/architecture/PHASE_3C_CONTEXT.md` | **NEW** — Full architecture context with file paths, data flow, configuration |
| `docs/contracts/MARKET_CONTRACT.md` | **UPDATED** — Added microstructure field definition |
| `docs/contracts/PREVIEW_CONTRACT.md` | **UPDATED** — Added new block reason codes and suggested_adjustments |
| `docs/contracts/RISK_LIMITS.md` | **UPDATED** — Documented 6 new threshold parameters with defaults |
| `docs/contracts/OPPORTUNITY_CONTRACT.md` | **UPDATED** — Added confluence field with score_breakdown |
| `docs/runbooks/Phase3C_Verification.md` | **NEW** — Operational verification runbook |
| `docs/phase3C_report.md` | **NEW** — Phase 3C final report |
| `docs/changes/2026-02-11_phase3C_complete.md` | **NEW** — This changelog |

---

## Configuration Reference

### New Environment Variables (Phase 3C)

| Variable | Default | Service(s) | Description |
|----------|---------|------------|-------------|
| `MAX_SPREAD_BPS` | 50.0 | state-api, fusion-engine | Max spread before hard block |
| `OPTIMAL_SPREAD_BPS` | 2.0 | fusion-engine | Spread below which no penalty applied |
| `MIN_DEPTH_25BP_USD` | 100000 | state-api, fusion-engine | Min orderbook depth at 25bp from mid |
| `MAX_IMPACT_BPS_5K` | 25.0 | state-api, fusion-engine | Max acceptable impact for $5k order |
| `MIN_LIQUIDITY_SCORE` | 0.3 | state-api, fusion-engine | Min composite liquidity score |
| `MARGIN_STRESS_THRESHOLD` | 0.8 | state-api | Margin utilization block threshold |
| `MAX_EXPOSURE_PER_SYMBOL_USD` | 25000 | state-api | Per-symbol exposure cap in USD |
| `MACRO_FEED_CACHE_TTL` | 300 | state-api | Macro feed cache TTL in seconds |
| `MACRO_RSS_SOURCES` | (3 defaults) | state-api | JSON array of RSS source configs |

---

## Files Changed (Phase 3C Complete)

### Created

| File | Description |
|------|-------------|
| `services/market-data/app/processors/microstructure.py` | Microstructure derivation from orderbook |
| `services/fusion-engine/app/scoring.py` | Enhanced scoring engine (policy + structure aware) |
| `services/state-api/app/macro_feed.py` | Macro headline RSS aggregator with sentiment |
| `services/cockpit-ui/src/api/hooks/useMacroFeed.ts` | React hooks for macro feed endpoints |
| `tests/test_phase3c.py` | Phase 3C automated test suite (10 tests) |
| `docs/architecture/PHASE_3C_CONTEXT.md` | Architecture context document |
| `docs/runbooks/Phase3C_Verification.md` | Operational verification runbook |
| `docs/phase3C_report.md` | Phase 3C final report |
| `docs/samples/phase3C/market_snapshot.json` | Sample market snapshot with microstructure |
| `docs/samples/phase3C/opportunities.json` | Sample opportunities with confluence |
| `docs/samples/phase3C/evidence_sample.json` | Sample evidence response |
| `docs/samples/phase3C/preview_sample.json` | Sample preview with block codes |
| `docs/samples/phase3C/orderbook_raw_hyperliquid.json` | Raw orderbook response |
| `docs/changes/2026-02-11_phase3C_complete.md` | This changelog |

### Modified

| File | Changes |
|------|---------|
| `services/market-data/app/models.py` | Added `MicrostructureData`, `BookHeatmapLevel` models |
| `services/market-data/app/processors/snapshotter.py` | Integrated microstructure derivation |
| `services/market-data/app/processors/normalizer.py` | Extended to 50 orderbook levels |
| `services/fusion-engine/app/worker.py` | Integrated `EnhancedScorer`, stores `confluence` |
| `services/state-api/app/main.py` | Added macro endpoints, updated preview with microstructure checks |
| `services/state-api/app/risk.py` | Added 6 new block codes + suggested adjustments |
| `services/cockpit-ui/src/api/types.ts` | Added all Phase 3C TypeScript interfaces |
| `services/cockpit-ui/src/api/hooks/index.ts` | Exported macro feed hooks |
| `services/cockpit-ui/src/pages/Market.tsx` | Added `LiquidityPanel` component |
| `services/cockpit-ui/src/pages/Overview.tsx` | Added `ExecutionConditionsStrip` + `MacroFeedCard` |
| `services/cockpit-ui/src/pages/OpportunityDetail.tsx` | Added `ExecutionRiskBox` component |
| `docs/contracts/MARKET_CONTRACT.md` | Added microstructure field spec |
| `docs/contracts/PREVIEW_CONTRACT.md` | Added new block codes and adjustments |
| `docs/contracts/RISK_LIMITS.md` | Added Phase 3C threshold docs |
| `docs/contracts/OPPORTUNITY_CONTRACT.md` | Added confluence field spec |

---

## Acceptance Criteria (Definition of Done)

| Criteria | Status | Proof |
|----------|--------|-------|
| MarketSnapshot includes microstructure derived fields and `available_metrics[]` truth labels | ✅ | `models.py`: MicrostructureData model, `snapshotter.py`: integration |
| `/market` shows liquidity heatmap + spread/depth/slippage badges | ✅ | `Market.tsx`: LiquidityPanel with all elements |
| Opportunity Detail shows execution risk box and renders preview guardrails clearly | ✅ | `OpportunityDetail.tsx`: ExecutionRiskBox at line 369 |
| Scoring includes microstructure + exposure penalties and emits breakdown | ✅ | `scoring.py`: EnhancedScorer with score_breakdown |
| Opportunity scoring visibly changes when liquidity is bad (same symbol + same alpha produces lower score if spread widens / depth collapses) | ✅ | `scoring.py`: `_compute_microstructure_penalty()` — up to -5.0 combined |
| Preview blocks trades on slippage/spread with human-readable reason codes | ✅ | `risk.py`: 6 block codes with plain-language reasons |
| Risk guardian blocks on spread/slippage/depth with reason codes | ✅ | `risk.py`: All 6 codes + suggested adjustments |
| Market page shows liquidity heatmap and numbers match the snapshot | ✅ | `Market.tsx`: LiquidityPanel renders microstructure data |
| Exposure actually influences ranking (open position exists -> new opp gets down-weighted) | ✅ | `scoring.py`: `_compute_exposure_penalty()` — -0.5 concentration, -1.0 margin stress |
| Overview macro panel shows real RSS/news feed items (MVP) | ✅ | `Overview.tsx`: MacroFeedCard with useMacroHeadlines hook |
| Docs updated (architecture/contracts/runbooks/changes) | ✅ | 8 docs created or updated |
| Verification runbook + tests added | ✅ | `Phase3C_Verification.md` + `test_phase3c.py` (10 tests) |

---

## What's Next

### Phase 3D/3E: Wallet Connect & Live Execution
- [ ] Wallet signing/custody flows (Drift + Hyperliquid)
- [ ] Transition from DRY_RUN=true to live execution
- [ ] Real position tracking and PnL

### Phase 4: AI & RAG
- [ ] AI Copilot with cited evidence
- [ ] Full RAG knowledge base (replacing Macro Feed MVP keyword matching with LLM analysis)
- [ ] Natural language trade explanations
- [ ] Historical microstructure persistence

### Deferred from Phase 3C
- ML-based sentiment (MVP uses keyword matching)
- Historical microstructure storage (live data only)
- Order splitting based on depth analysis
- Cross-venue arbitrage microstructure comparison

---

## Known Issues Addressed

| Issue | Status | Resolution |
|-------|--------|------------|
| Scoring not execution-aware | ✅ Fixed | Enhanced scoring with microstructure + exposure penalties |
| No slippage/spread guardrails | ✅ Fixed | 6 new Risk Guardian block codes |
| Static/fake macro panel | ✅ Fixed | Live RSS macro feed with sentiment |
| No liquidity visibility on Market page | ✅ Fixed | LiquidityPanel with heatmap + badges |
| No execution risk on Opportunity Detail | ✅ Fixed | ExecutionRiskBox with risk levels |
| Overview missing execution conditions | ✅ Fixed | ExecutionConditionsStrip with ALL CLEAR/CAUTION |
| No Phase 3C changelog | ✅ Fixed | This document |

---

*Phase 3C is 100% complete. The system now scores, guards, and displays execution-aware trading intelligence. Ready to proceed to Phase 3D/3E (Wallet Connect & Live Execution).*
