# TradeSync — Opportunity Pipeline Audit

**Last Updated:** 2026-03-27
**Purpose:** End-to-end trace of how an opportunity is created, enriched, acted on, and expired.

---

## 1. Pipeline Overview

```
External Market APIs
        ↓
  ingest-gateway          ← polls Hyperliquid + Drift, receives TradingView webhooks
        ↓ (events table + x:events.norm stream)
  core-scorer             ← reads events, runs calculate_score(), saves signals
        ↓ (signals table + x:signals.funding stream)
  fusion-engine           ← consumes signal, fetches microstructure, runs EnhancedScorer
        ↓ (opportunities table)
  state-api               ← opportunity available via REST
        ↓ (preview call)
  state-api/RiskGuardian  ← validates trade, creates decision record
        ↓ (execute call)
  exec-drift-svc / exec-hl-svc  ← routes order to venue
        ↓
  exec_orders table       ← full result persisted
```

---

## 2. Step-by-Step: Actual Pipeline Today

### Step 1: Event Ingestion

**Actor:** `ingest-gateway`
**Source A — Polling:**
- `poll_hyperliquid_markets()` every 60s: fetches `metaAndAssetCtxs` from Hyperliquid `/info`
- `poll_drift_markets()` every 10s: fetches contracts from Drift `/contracts`
- Each poll creates a `market_snapshot` event (kind=`market_snapshot`, source=`metrics`)
- Events are inserted into `events` table with:
  - `hash` = UUID5(source:symbol:ts:bias) for deduplication
  - `payload` = raw market data (funding, OI, price, volume)

**Source B — TradingView Webhooks:**
- `POST /ingest/tv` receives bias signal
- Creates event with source=`tradingview`, kind=`signal`
- Payload contains `bias: "LONG"` or `bias: "SHORT"`

**Deduplication:** `ON CONFLICT (hash) DO NOTHING`

**Redis:** Events also written to `x:events.norm` stream (for any future consumers)
**Redis mirror:** `ingest:source_mirror:{source}` HSET stores latest payload per source (24h TTL)

---

### Step 2: Signal Scoring

**Actor:** `core-scorer`
**Trigger:** `score_loop()` runs every `SCORING_INTERVAL` seconds (default 60s)

**Data fetch:**
```sql
SELECT id, ts, source, kind, symbol, payload
FROM events
WHERE symbol = $1
  AND ts > now() - interval '30 minutes'
  AND (source = 'tradingview' OR (source = 'metrics' AND kind = 'market_snapshot'))
```

**Scoring (`tradesync_core.calculate_score`):**
1. Count TradingView bias events: +1.0 per LONG, -1.0 per SHORT
2. From latest market_snapshot: get funding rate
3. From first + latest market_snapshot: compute OI delta %
4. Apply squeeze rules:
   - funding < -0.0001 AND oi_delta_pct > 0.005 → +2.0 (negative funding + rising OI)
   - funding > +0.0001 AND oi_delta_pct > 0.005 → -2.0 (positive funding + rising OI)
5. Apply base funding bias: funding < 0 → +0.5; funding > 0 → -0.5
6. Clamp to [-10.0, 10.0]
7. Confidence = abs(score) / 10.0

**Output:**
- `signals` table INSERT: agent=`core_scorer`, timeframe=`1m`, kind=`bias_score`
- `x:signals.funding` XADD: `{id, agent, symbol, score, confidence, direction, event_ids}`

---

### Step 3: Opportunity Creation

**Actor:** `fusion-engine`
**Trigger:** Redis consumer group on `x:signals.funding`

**Threshold check:**
```python
if abs(score) < OPPORTUNITY_THRESHOLD:  # default 2.0
    xack and skip
```

**Traceability check:**
```python
if not event_ids:
    skip  # No evidence chain = not actionable
```

**Microstructure fetch:**
```python
GET market-data:8005/snapshot/hyperliquid/{symbol}
# Returns microstructure.spread_bps, microstructure.depth_usd, microstructure.impact_est_bps
# Returns regimes.funding, regimes.oi, regimes.market_condition
```

**Enhanced scoring (`tradesync_core.EnhancedScorer`):**
```
final_score = raw_score
            + microstructure_penalty (spread, depth, impact — max ~ -1.75)
            + exposure_penalty (position concentration, margin — always 0 TODAY due to bug)
            + regime_bonus (squeeze alignment, market condition — max +0.8)
```

**Opportunity record:**
```python
{
    symbol, timeframe,
    bias: final_score,           # enhanced score
    quality: confidence * 100,   # 0-100
    dir: direction,              # LONG/SHORT/NEUTRAL
    links: {signal_id, event_ids},
    signal_id,                   # for UNIQUE constraint dedup
    ttl_seconds: 900,            # 15 min default
    confluence: enhanced_score.to_dict()  # full breakdown
}
```

**DB write:** `INSERT INTO opportunities ... ON CONFLICT (signal_id) DO NOTHING`

**ACK:** XACK only after successful DB commit (strict ordering, no data loss)

**Pending recovery:** On startup, `recover_pending()` runs XCLAIM on idle messages > 60s

---

### Step 4: Opportunity Available in Cockpit

**Actor:** `state-api`
**Endpoint:** `GET /state/opportunities?symbol=X&status=new`

Returns opportunities from DB with status filter. The `confluence` field (EnhancedScore breakdown) is included.

**Expiry background task:**
```sql
UPDATE opportunities SET status = 'expired'
WHERE status IN ('new', 'previewed')
  AND (expires_at < now() OR snapshot_ts < now() - $ttl_seconds)
```
Runs every 60s. Default TTL: 300s in state-api (overrides fusion-engine's 900s TTL via the background task).

---

### Step 5: Preview (User Action)

**Actor:** User → cockpit → state-api
**Endpoint:** `POST /actions/preview` body: `{opportunity_id, size_usd, venue}`

**Flow:**
1. Fetch opportunity from DB (must be status=`new`)
2. Fetch latest signal for the symbol
3. Fetch microstructure from market-data (for RiskGuardian microstructure checks)
4. Fetch current positions (for exposure check)
5. Run `RiskGuardian.check()` — full validation:
   - Global killswitch check
   - DNT list (LUNA, FTX, FTT)
   - Duplicate/status check (must be `new`)
   - Expiry check (expires_at)
   - Signal staleness check (> max_signal_age)
   - Quality gate (< min_quality)
   - Microstructure vetoes (spread, depth, impact, liquidity)
   - Margin stress veto
   - Symbol exposure veto
   - Max open positions check
   - Cooldown/duplicate decision check
   - Size and leverage checks
6. If allowed: INSERT into `decisions` table
7. UPDATE opportunity status → `previewed`
8. Return `PreviewResponse` with:
   - `decision_id`
   - `plan` (symbol, venue, size, direction, leverage, stops, TPs)
   - `risk_verdict` (allowed, reason_code, reason, suggested_adjustment)

---

### Step 6: Execute (User Confirmation)

**Actor:** User → cockpit → state-api
**Endpoint:** `POST /actions/execute` body: `{decision_id, confirm: true}`

**Flow:**
1. Fetch decision from DB
2. Fetch opportunity (must be `new` or `previewed`)
3. Run RiskGuardian again (`phase="execute"`)
4. Generate idempotency_key
5. Check `exec:idempo:{venue}:{key}` in Redis — if exists, return cached result
6. Check circuit breaker `exec:disabled:{venue}` — if open, reject
7. Route to venue:
   - venue=`drift` → POST exec-drift-svc:8003/exec/drift/order
   - venue=`hyperliquid` → POST exec-hl-svc:8004/exec/hl/order
8. Cache result in `exec:idempo:{venue}:{key}` for 24h
9. INSERT into `exec_orders` table
10. UPDATE opportunity status → `executed`
11. Return `ExecutionResult` with:
    - `ok`, `venue`, `dry_run`, `execution_enabled`
    - `status`: `placed` / `rejected` / `error`
    - `order_id`, `idempotency_key`
    - `request_payload`, `response_payload`

---

## 3. Status State Machine

```
new  →  previewed  →  executed
 ↓          ↓
expired   expired

blocked  (NOT IMPLEMENTED — risk-vetoed opportunities currently stay 'new')
```

**What creates `new`:**
- fusion-engine inserts the opportunity (score above threshold, has event_ids)

**What creates `previewed`:**
- state-api preview action runs RiskGuardian — if allowed, status → `previewed`

**What creates `executed`:**
- state-api execute action succeeds — status → `executed`

**What creates `expired`:**
- Background TTL task in state-api: `expires_at < now()` OR `snapshot_ts + TTL < now()`

**What should create `blocked` (not yet implemented):**
- RiskGuardian rejects at preview — currently the opportunity stays `new`
- This means a rejected preview leaves the opp available for another preview attempt
- Phase 3F should add `blocked` status for permanently risk-vetoed opportunities

---

## 4. Evidence Retrieval

**Endpoint:** `GET /state/evidence?opp_id=X`

Returns full chain:
```json
{
  "opportunity": { ...opp record with confluence... },
  "signals": [ ...all signals linked via signal_id... ],
  "events": [ ...all events linked via event_ids... ],
  "decisions": [ ...all decisions for this opp... ],
  "exec_orders": [ ...all orders for linked decisions... ]
}
```

This is the "audit trail" that makes every opportunity fully explainable.

---

## 5. Key Questions Answered

**What creates a new opportunity?**
fusion-engine: signal score >= OPPORTUNITY_THRESHOLD (default 2.0) AND has event_ids.

**What changes it to `previewed`?**
User triggers `/actions/preview`, RiskGuardian passes all checks.

**What changes it to `executed`?**
User triggers `/actions/execute` with `confirm=true`, exec service returns success.

**What expires it?**
Background task in state-api every 60s. Default TTL 300s from snapshot_ts (or explicit expires_at).

**What makes it blocked?**
Nothing today — `blocked` status does not exist. Risk-rejected previews leave opp in `new`.

**What gets persisted where?**
- Event: `events` table + `x:events.norm` stream
- Signal: `signals` table + `x:signals.funding` stream
- Opportunity: `opportunities` table (with full confluence data)
- Decision: `decisions` table (with risk, leverage, stops, TPs)
- Order: `exec_orders` table (with full request/response payloads)

---

## 6. Known Pipeline Bugs / Gaps

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| 1 | `exposure_data=None` in fusion-engine worker | Medium | `services/fusion-engine/app/worker.py:82` — `exposure_data=None` passed to EnhancedScorer, so exposure penalty is always 0 |
| 2 | `blocked` status not implemented | Medium | Status machine is incomplete; risk-rejected opportunities stay `new` |
| 3 | TTL mismatch: fusion-engine sets 900s, state-api TTL task uses 300s env default | Low | Both values configurable but out of sync |
| 4 | No fill confirmation loop | High | `placed` status means "sent to venue" not "filled"; there is no loop that polls exec services for fill status |
| 5 | Daily notional limit counter never incremented | Low | `RiskGuardian` has `LIMIT_DAILY` reason code but counter at 0 always |
| 6 | Opportunity score displayed as `bias` field, not labeled clearly | Low | UI shows raw float, no label explaining it's the enhanced final score |
