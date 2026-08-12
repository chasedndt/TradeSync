# Opportunity Generation Runtime Audit

**Date:** 2026-03-29 (updated 2026-03-30 after pipeline validation)
**Trigger:** Operator observed zero visible trade opportunities after hours of runtime

---

## UPDATE — Pipeline Now Validated (2026-03-30)

The first real opportunity was generated through the live pipeline on 2026-03-30. The findings below are still correct and remain the definitive explanation of why scores were ±0.5 and why the threshold was never crossed. They are also the explanation of how to generate opportunities going forward.

**Confirmed working path:**
```bash
# Send 3 TradingView LONG alerts (each adds +1.0):
curl -X POST http://localhost:8080/ingest/tv \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC","timeframe":"1h","bias":"LONG","confidence":80.0,"source":"tradingview"}'
# (repeat ×3)
# Wait ~60s for scoring cycle → opportunities appear at /state/opportunities
```

**Confirmed result:** BTC-PERP LONG, score=3.5 (→5.5 with squeeze), 18 opportunities created, evidence trail complete.

---

## Executive Finding

**The system has generated 825 signals and zero opportunities. This is not a UI bug or a filtering issue. Every signal in the DB has a score of exactly ±0.5, and the opportunity threshold is 2.0. The threshold has never been crossed.**

The root cause is structural: the scoring system was designed around **TradingView webhook alerts** as the primary signal driver. Without them, the max achievable score from market data alone is ±0.5 (base funding bias only). The squeeze condition that could reach ±2.5 has never triggered because OI never rose 0.5% within a 30-minute window.

---

## Pipeline Architecture

```
ingest-gateway
  ├── sources/hyperliquid.py — polls Hyperliquid API every 60s
  │     writes → events (source='metrics', kind='market_snapshot')
  ├── sources/drift.py — polls Drift API every 10s  ← was broken, now fixed
  │     writes → events (source='metrics', kind='market_snapshot')
  └── /ingest/tv — webhook receiver for TradingView alerts
        writes → events (source='tradingview', kind='alert')  ← ZERO EVENTS

core-scorer (runs every 60s per symbol)
  reads events WHERE source IN ('tradingview', 'metrics/market_snapshot')
    AND ts > NOW() - 30min
  calculates score → saves to signals table → xadd to x:signals.funding

fusion-engine
  xreadgroup x:signals.funding
  if abs(score) < 2.0 → DISCARD  ← ALL 825 SIGNALS DISCARDED HERE
  if abs(score) >= 2.0 → create opportunity
```

---

## Live Database State (2026-03-29)

| Table | Count | Latest record |
|-------|-------|---------------|
| events | 138 | 2026-03-29 15:24:42 UTC |
| signals | 825 | 2026-03-29 15:25:21 UTC |
| opportunities | **0** | — |
| decisions | 0 | — |
| exec_orders | 0 | — |

**Event source breakdown:**

| source | kind | count |
|--------|------|-------|
| metrics | market_snapshot | 138 |
| tradingview | alert | **0** |

There have been **zero TradingView alerts ever received**.

---

## Signal Score Distribution

| direction | count | avg_score | min | max |
|-----------|-------|-----------|-----|-----|
| LONG | 275 | +0.500 | +0.5 | +0.5 |
| SHORT | 550 | -0.500 | -0.5 | -0.5 |

**Every signal has a score of exactly ±0.5.** The score never varies because the only active input is the base funding bias.

---

## Scoring Logic Breakdown

From `libs/tradesync_core/tradesync_core/core_score.py`:

```python
# 1. TradingView events (source='tradingview')
for event in sorted_events:
    if event.source == "tradingview":
        if bias == "LONG": score += 1.0    # NOT ACTIVE — no TV events
        elif bias == "SHORT": score -= 1.0  # NOT ACTIVE — no TV events

# 2. Metrics events (source='metrics', kind='market_snapshot')
if metrics_events:
    # Squeeze logic — requires BOTH conditions:
    if funding < -0.0001 AND oi_delta_pct > 0.005:  # OI up 0.5% in 30min
        score += 2.0  # NEVER TRIGGERED
    elif funding > 0.0001 AND oi_delta_pct > 0.005:
        score -= 2.0  # NEVER TRIGGERED

    # Base funding bias — THE ONLY ACTIVE PATH
    if funding < 0: score += 0.5   # SOL: funding < 0 → SOL always scores +0.5
    elif funding > 0: score -= 0.5  # BTC/ETH: funding > 0 → always -0.5
```

**Max achievable score from market data alone (no TV alerts): ±0.5**

For the squeeze condition to trigger: OI must rise ≥ 0.5% between the first and last `market_snapshot` event in the 30-minute window. Under normal market conditions, OI does not move 0.5% in 30 minutes. This condition has never been met across 138 events.

**Opportunity threshold: `abs(score) < 2.0` → discard** — confirmed in `fusion-engine/app/worker.py:127`.

---

## What Must Happen to Generate Opportunities

**Path 1: TradingView webhooks (designed path)**
Send POST to `http://<host>:8001/ingest/tv` with:
```json
{
  "symbol": "BTC",
  "bias": "LONG",
  "source": "tradingview",
  "timeframe": "1h",
  "confidence": 0.75
}
```
Each LONG alert adds +1.0, each SHORT adds -1.0.
3 LONG alerts + +0.5 funding bias → score = 3.5 → OPPORTUNITY.

**Path 2: Wait for squeeze conditions**
Funding < -0.0001 AND OI rises 0.5%+ in 30 minutes → score = +2.5 → OPPORTUNITY.
This happens during actual market stress events (short squeeze pressure). Cannot be forced.

**Path 3: Lower the threshold** ← DESIGN DECISION
Lower `OPPORTUNITY_THRESHOLD` env var (default 2.0) to something achievable from funding data alone:
- Set to 0.4 → every funding-biased signal becomes an opportunity (may be too noisy)
- Set to 1.0 → still never reached without TV or squeeze
Requires understanding the trade-off between signal quality and opportunity frequency.

**Path 4: Add new scoring inputs** ← FUTURE WORK
Add additional market data inputs (funding trend, OI acceleration, VWAP deviation) that can independently contribute to score. This is Phase 4A work.

---

## Opportunity Surfacing Verification

The frontend is NOT hiding opportunities. The backend simply has none to show.

Confirmed: `GET /state/opportunities` would return an empty list. No filtering or status issue involved. The cockpit opportunity list is empty because `opportunities` table has zero rows — not because of any UI bug or status filter.

---

## Stack State During Investigation

| Container | Status |
|-----------|--------|
| tradesync-full-postgres-1 | Exited (0) 7h ago |
| tradesync-full-redis-1 | Exited (0) 7h ago |
| tradesync-full-ingest-gateway-1 | Exited (137) 7h ago |
| tradesync-full-core-scorer-1 | Exited (0) 7h ago |
| tradesync-full-fusion-engine-1 | Exited (0) 7h ago |
| tradesync-full-state-api-1 | Exited (0) 7h ago |
| tradesync-full-market-data-1 | **Up 16 min (unhealthy)** |
| tradesync-full-qdrant-1 | Exited (143) 7h ago |
| tradesync-full-exec-hl-svc-1 | Exited (137) 7h ago |
| tradesync-full-exec-drift-svc-1 | Exited (137) 7h ago |

market-data started 16 minutes before investigation (restart policy or manual). It is unhealthy because Redis is down — every polling cycle fetches data successfully from external APIs but fails when trying to write to Redis (`Error -2 connecting to redis:6379`).

---

## Next Recommended Steps (Ordered by Impact)

1. **Restart the full stack** — `docker compose -f ops/compose.full.yml up -d --build`
   (--build is needed to pick up the Drift `/contracts` → `/stats/markets` fixes)

2. **Wire a TradingView alert** OR **lower OPPORTUNITY_THRESHOLD** — without this, the system remains dormant under normal market conditions

3. **Consider the threshold design question** — is 2.0 still the right threshold now that the primary TV input channel is empty? Document the decision.
