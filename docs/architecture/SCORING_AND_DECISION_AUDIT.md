# TradeSync — Scoring & Decision Logic Audit

**Last Updated:** 2026-03-27
**Purpose:** Brutally honest audit of what the scoring and decision logic actually does today vs what it is described as doing.

---

## 1. The Two-Layer Scoring System

There are **two separate scoring computations** running in sequence:

### Layer 1: `core_score.calculate_score()` — in `libs/tradesync_core/tradesync_core/core_score.py`

This is the **only signal alpha source**. Everything else modifies or gates it.

```python
def calculate_score(events: List[Event]) -> float:
    score = 0.0

    # TradingView signals
    for event in tradingview_events:
        if bias == "LONG": score += 1.0
        elif bias == "SHORT": score -= 1.0

    # Latest market_snapshot: funding + OI delta
    if metrics_events:
        funding = latest.payload["funding"]
        oi_delta_pct = (oi_current - oi_start) / oi_start

        # Squeeze detection
        if funding < -0.0001 and oi_delta_pct > 0.005: score += 2.0
        elif funding > 0.0001 and oi_delta_pct > 0.005: score -= 2.0

        # Base funding bias
        if funding < 0: score += 0.5
        elif funding > 0: score -= 0.5

    return clamp(score, -10, 10)
```

**This is it.** No other market logic exists in Layer 1.

### Layer 2: `EnhancedScorer.compute_enhanced_score()` — in `libs/tradesync_core/tradesync_core/scoring.py`

Runs in fusion-engine worker. Modifies the raw score:

```
final_score = raw_score
            + microstructure_penalty   (spread, depth, slippage — reduces score)
            + exposure_penalty         (concentration, margin stress — reduces score)  ← ALWAYS 0 TODAY
            + regime_bonus             (squeeze alignment, market condition — increases score)
```

**The exposure_penalty is always 0** because `exposure_data=None` is hardcoded in the worker.

---

## 2. Feature Usage Matrix

| Feature | Used In Core Scoring | Used In Enhanced Scoring | Used In Risk Veto | Displayed In UI | Ingested | Notes |
|---------|---------------------|-------------------------|-------------------|----------------|---------|-------|
| **Funding rate** | YES — squeeze + base bias | YES — regime_bonus input | NO | YES | YES | Core signal |
| **OI (current value)** | PARTIAL — only for delta calc | YES — regime_bonus input | NO | YES | YES | Value itself not scored, only delta |
| **OI delta %** | YES — squeeze trigger (0.5% threshold) | YES — regime classification | NO | YES (derived) | YES | 30-min window in core scorer |
| **Volume 24h** | NO | YES — regime classification only | NO | YES | YES | No directional signal from volume |
| **Volume delta / CVD** | NO | NO | NO | NO | NO | Not ingested, not scored |
| **Orderbook spread** | NO | YES — microstructure penalty | YES — SPREAD_TOO_WIDE veto | YES | YES | Reduces final score |
| **Orderbook depth** | NO | YES — depth penalty | YES — DEPTH_TOO_THIN veto | YES | YES | Reduces final score |
| **Mid-price** | NO | NO | NO | YES | YES | Displayed only |
| **Slippage / impact estimate** | NO | YES — impact penalty | YES — SLIPPAGE_TOO_HIGH veto | YES (microstructure) | YES (derived) | Derived from orderbook |
| **Liquidity score** | NO | YES — flag | YES — LIQUIDITY_TOO_LOW veto | YES (microstructure) | YES (derived) | Derived from orderbook |
| **Liquidations** | NO | NO | NO | YES (PROXY label) | YES (proxy) | OI-delta proxy only, not scored |
| **Volatility** | NO | NO | NO | NO | NO | Not implemented anywhere |
| **TradingView bias** | YES — +1/-1 per signal | NO | NO | YES (events) | YES | Simple count only |
| **HTF thesis** | NO | NO | NO | NO | NO | Not implemented |
| **LTF thesis** | NO | NO | NO | NO | NO | Not implemented |
| **Funding regime label** | NO (computed from) | YES — regime_bonus | NO | YES | YES (derived) | Label is computed, not a raw input |
| **OI regime label** | NO (computed from) | YES — regime_bonus | NO | YES | YES (derived) | |
| **Market condition label** | NO | YES — regime_bonus +0.3/-0.3 | NO | YES | YES (derived) | |
| **Position / margin** | NO | PARTIAL (exposure_data=None) | YES — MARGIN_STRESS veto | NO | YES (exec services) | exposure_penalty always 0 |
| **Symbol exposure USD** | NO | PARTIAL (exposure_data=None) | YES — EXPOSURE_TOO_HIGH veto | NO | YES (exec services) | always 0 in scoring |
| **Open position count** | NO | NO | YES — LIMIT_POSITIONS veto | NO | YES | Risk veto only |
| **Recent decisions** | NO | NO | YES — COOLDOWN veto | NO | YES | Risk veto only |
| **Signal age** | NO | NO | YES — STALE_DATA veto | NO | YES | Risk veto only |
| **Opportunity quality** | NO | NO | YES — MIN_QUALITY veto | YES | YES (derived) | quality = confidence × 100 |
| **Source library context** | NO | NO | NO | NO (placeholder) | NO | Phase 4 |
| **Macro headlines** | NO | NO | NO | NO (stub endpoint) | NO | Phase 4 |
| **SMC / ICT concepts** | NO | NO | NO | NO | NO | Not implemented — see Section 4 |

---

## 3. Where Weights, Thresholds, Confluence, and Veto Rules Live

### Scoring thresholds (core_score.py — hardcoded):
```python
SQUEEZE_FUNDING_THRESHOLD = 0.0001     # 0.01% per 8h
SQUEEZE_OI_DELTA_THRESHOLD = 0.005     # 0.5% OI change
TV_SIGNAL_WEIGHT = 1.0                 # per TradingView signal
SQUEEZE_SCORE_BONUS = 2.0             # squeeze detection bonus
BASE_FUNDING_BIAS = 0.5               # funding direction base weight
```

### Opportunity creation threshold (env var, default 2.0):
```
OPPORTUNITY_THRESHOLD=2.0
```
A score of abs(2.0) or higher creates an opportunity. This is **the only confluence gate**.

### Microstructure penalty weights (EnhancedScorer, env-configurable):
```python
spread_penalty_weight = 0.5   # max -1.0 from spread
depth_penalty_weight = 0.3    # max -0.45 from depth
impact_penalty_weight = 0.2   # max -0.30 from slippage
# Total max microstructure penalty: -1.75
```

### Regime bonuses (EnhancedScorer, hardcoded):
```python
squeeze_bonus = +0.5           # funding+OI aligned for squeeze
trending_bonus = +0.3          # market_condition == "trending_healthy"
choppy_penalty = -0.3          # market_condition == "choppy"
```

### RiskGuardian veto thresholds (env-configurable):
```python
MAX_LEVERAGE = 5.0
MAX_SPREAD_BPS = 50.0
MIN_DEPTH_25BP_USD = 100000
MAX_IMPACT_BPS_5K = 25.0
MIN_LIQUIDITY_SCORE = 0.3
MARGIN_STRESS_THRESHOLD = 0.8
MAX_EXPOSURE_PER_SYMBOL_USD = 25000
MAX_OPEN_POSITIONS = 10
MIN_QUALITY = 50.0
MAX_EVENT_AGE_SECONDS = 300
MAX_SIGNAL_AGE_SECONDS = 300
```

### What is deterministic vs heuristic vs placeholder:

| Component | Nature |
|-----------|--------|
| TradingView signal counting | **Deterministic** — exactly +1/-1 per signal |
| Funding squeeze logic | **Deterministic rule-based** — explicit thresholds |
| OI delta calculation | **Deterministic** — 30-min window math |
| Microstructure penalty | **Deterministic rule-based** — linear interpolation within bands |
| Regime classification | **Deterministic rule-based** — explicit thresholds in snapshotter |
| Regime bonus | **Deterministic rule-based** — hardcoded bonus values |
| Exposure penalty | **Placeholder** — always 0 due to bug |
| Quality score | **Derived** — confidence × 100 = abs(score) / 10 × 100 |
| Stop loss / take profit | **Not computed** — no stop/TP calculation logic anywhere in code |
| Leverage sizing | **Implicit** — checked against limit but not auto-sized |

---

## 4. SMC/ICT Support — Honest Assessment

**Is the current system implementing Smart Money Concepts / ICT-style logic?**

**No.**

The following SMC/ICT concepts are **not implemented anywhere** in the codebase:

| Concept | Status |
|---------|--------|
| Break of Structure (BOS) | NOT IMPLEMENTED |
| Change of Character (CHOCH) | NOT IMPLEMENTED |
| Fair Value Gap (FVG) | NOT IMPLEMENTED |
| Liquidity sweep detection | NOT IMPLEMENTED |
| Displacement candle detection | NOT IMPLEMENTED |
| Order block identification | NOT IMPLEMENTED |
| Premium/discount zones | NOT IMPLEMENTED |
| Inducement detection | NOT IMPLEMENTED |
| Internal liquidity vs external liquidity | NOT IMPLEMENTED |
| Equal highs/lows sweep | NOT IMPLEMENTED |
| Market structure shift (MSS) | NOT IMPLEMENTED |
| HTF/LTF alignment | NOT IMPLEMENTED |

The system does NOT interpret price action or market structure. It has no candlestick data, no OHLCV feed, and no time-series price analysis.

---

## 5. Brutal Gap Analysis vs Intended Trading Model

### What the system actually is today:

A **funding/OI-driven bias model** with:
- Directional count from TradingView webhooks (+1/-1)
- Squeeze detection from funding + OI delta (the main signal)
- Microstructure gates (spread, depth, slippage — as penalty and veto)
- Regime labeling for context display
- Risk veto layer (exposure, leverage, age, quality)

### What it is NOT:

1. **It is not SMC/ICT.** There is no price structure analysis, no liquidity mapping, no displacement or FVG detection.

2. **It is not using CVD.** Cumulative Volume Delta is not ingested, not computed, not displayed.

3. **It is not using volume delta.** Volume is only used for regime classification (HIGH/NORMAL/LOW vs 7d avg).

4. **It is not interpreting market structure.** There is no concept of highs/lows, swings, trend direction from price.

5. **It is not using OI meaningfully for directional bias** — OI is only used in the squeeze rule (>0.5% delta triggers the squeeze score). OI level itself is displayed but not scored.

6. **The "confluence" field in opportunities is misleading branding.** It contains the EnhancedScore breakdown (a scoring modifier), not multi-timeframe or multi-factor confluence in the trading sense.

7. **The scoring is a simple weighted sum, not a confluence system.** There is no requirement that multiple independent signals agree before an opportunity is created.

8. **Stop loss / take profit values are not computed anywhere.** The `decisions.risk` field stores SL/TP but they are passed through from the preview request, not calculated by any strategy logic.

### What the system IS good at today:

1. **Honest instrumentation.** The pipeline is real, the DB schema is solid, events → signals → opportunities → decisions → orders is fully traced and auditable.

2. **Microstructure risk gates.** The spread/depth/slippage veto layer is real and will prevent bad executions in thin markets.

3. **Expiry and staleness enforcement.** Opportunities expire on schedule, signals are age-gated.

4. **Regime context.** The market regime labels are explicitly defined and consistent. They correctly describe what funding/OI/volume are doing without overclaiming.

5. **Observability.** Prometheus metrics, trace IDs, service health maps, partial-failure resilience.

---

## 6. What Should Be Built Next for Scoring Quality

In priority order, based on what would actually improve signal quality with minimal architecture change:

1. **Fix exposure_data=None** (fusion-engine worker line 82) — wire to `/state/positions` so the exposure penalty actually works. Low risk, high value.

2. **Add volume delta tracking** — track volume over 5m/15m windows and add directional bias check. Requires small change to ingest-gateway to accumulate volume per period.

3. **Add multi-signal confluence requirement** — currently one funding+OI event creates an opportunity. Could add a minimum signal count or require TradingView + metrics agreement before threshold.

4. **Add OI level check** — absolute OI relative to 7d average is already computed (regime classification) but not used in scoring. Could add OI_BUILD bonus only when OI is also high vs historical.

5. **Price structure from OHLCV** — this is a larger lift (requires OHLCV data feed) but is the prerequisite for any SMC/ICT-style logic. Until this exists, SMC/ICT is not achievable.
