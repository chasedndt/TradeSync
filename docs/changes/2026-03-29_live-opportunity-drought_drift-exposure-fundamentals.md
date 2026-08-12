# Live Investigation: Opportunity Drought, Drift Fix, Exposure, Fundamentals

**Date:** 2026-03-29
**Scope:** Live runtime investigation of why the system produces no trade opportunities; Drift live verification; exposure_data status; fundamentals/RSS audit

---

## Executive Summary

The system has generated 825 signals and zero opportunities. This is a structural gap, not a bug or UI issue. Every signal scores exactly ±0.5 (base funding bias); the fusion-engine threshold is 2.0. The threshold has never been crossed because TradingView alerts — the designed primary input — have never been sent to the system. Without them, the max achievable score is ±0.5 from market data alone.

Three additional findings confirmed during this pass:

1. **Drift `/contracts` 404** — confirmed live. Market-data container confirmed logging the error every few seconds. Fix applied but container needs rebuild.
2. **`ingest-gateway/sources/drift.py`** had the same broken `/contracts` URL — also fixed.
3. **`exposure_data`** is already wired in `fusion-engine/app/worker.py` (done in a prior session). Not a gap.
4. **Macro/RSS** fetches headlines from Cointelegraph/CoinDesk/Bloomberg Crypto but **never participates in scoring** — display-only.

---

## Drift Live Verification

### Before (live log, confirmed)
```
INFO:  HTTP Request: GET https://data.api.drift.trade/contracts "HTTP/1.1 404 Not Found"
ERROR: Error fetching Drift context: Client error '404 Not Found' for url 'https://data.api.drift.trade/contracts'
```
This error repeats every ~6 seconds. Drift context data (funding, OI, volume, price) has never populated from market-data.

### After (code fix applied)
`services/market-data/app/providers/drift.py` — `fetch_context` now calls `/stats/markets`.
`services/ingest-gateway/sources/drift.py` — `fetch_drift_contracts` now calls `/stats/markets`.

Neither container has been rebuilt yet. Both fixes require `docker compose up --build` to take effect.

### Runtime state during investigation
market-data was the only running container (started ~16 minutes before investigation). It was unhealthy because Redis was down — external API calls (Hyperliquid, Drift DLOB) returned 200 OK, but every write attempt failed with `Error -2 connecting to redis:6379`.

### Remaining Drift limitation
`ingest-gateway/sources/drift.py` field names (`ticker_id`, `last_price`, `funding_rate`, `open_interest`) are maintained as an output shim — the `fetch_drift_contracts` function now maps `/stats/markets` fields to those names before returning, so downstream `poll_drift_markets` logic is unchanged.

---

## Opportunity Drought Findings

### Root cause (confirmed from live DB)

```
signals table:  825 rows  (all score = ±0.5)
events table:   138 rows  (all source='metrics', kind='market_snapshot')
opportunities:    0 rows
decisions:        0 rows
exec_orders:      0 rows
```

**The threshold has never been crossed.**

The `fusion-engine/app/worker.py` at line 127:
```python
if abs(score) < OPPORTUNITY_THRESHOLD:  # default 2.0
    await redis_client.client.xack(STREAM_NAME, GROUP_NAME, msg_id)
    return  # ← all 825 signals exit here
```

### Why scores are always ±0.5

The scoring function (`core_score.py`) has two inputs:
1. **TradingView alerts** — `source='tradingview'` — contributes ±1.0 per alert. **Zero TV events in DB.**
2. **Market snapshots** — `source='metrics', kind='market_snapshot'`:
   - Base funding bias: ±0.5 if funding non-zero. **This is the only active path.**
   - Squeeze bonus: ±2.0 if funding extreme AND OI rises ≥0.5% in 30 min. **Never triggered.**

Without TradingView webhooks, the system is capped at ±0.5.

### What is required to generate opportunities

**Minimum**: Send a TradingView alert to `POST /ingest/tv` with `"bias": "LONG"` or `"bias": "SHORT"`. Three aligned alerts + funding bias = ±3.5 → exceeds threshold.

**Alternative**: Lower `OPPORTUNITY_THRESHOLD` env var. Default is 2.0; lowering to ~0.4 would treat every funding-biased signal as an opportunity (high noise risk).

**Alternative**: Wait for a real market squeeze event (funding extreme + OI rising fast). Rare under normal conditions.

---

## Exposure_data Wiring Result

**Status: Already complete.** `services/fusion-engine/app/worker.py` (lines 52–109) contains a fully implemented `fetch_exposure_data()` function that:
- Calls `GET /state/positions`
- Builds `{"by_symbol": {...}, "margin_utilization": float}` for EnhancedScorer
- Degrades gracefully on failure (returns None → exposure_penalty stays 0)
- Is called at line 144: `exposure_data = await fetch_exposure_data(symbol)`

This was done in a prior session. No changes needed. The `exposure_penalty` component in `score_breakdown.confluence` will be non-zero once real positions exist. Currently 0 because there are no positions.

---

## Fundamentals / RSS Audit Result

### What exists

`services/state-api/app/macro_feed.py` — a real, working RSS aggregator:
- Fetches from Cointelegraph (`https://cointelegraph.com/rss`), CoinDesk, Bloomberg Crypto
- Parses RSS/Atom feeds
- Applies basic keyword-based sentiment classification (bullish/bearish/neutral)
- Has in-memory cache with 5-minute TTL
- Configurable via `MACRO_RSS_SOURCES` env var (JSON array of `{name, url, category}`)

### Where it is used

Only in `state-api`'s `/state/macro/headlines` endpoint — **display only**. The cockpit Macro page shows these headlines as context for the operator.

### Does it affect scoring or opportunity generation?

**No.** The RSS feed:
- Does NOT write to the events table
- Does NOT feed into core-scorer
- Does NOT affect fusion-engine
- Does NOT affect RiskGuardian veto logic
- Does NOT affect any signal or score

It is purely a UI context widget.

### The complete answer on fundamentals

**TradeSync does not use fundamentals, news, or RSS in live trade decision logic today.**

The live scoring pipeline uses exactly two inputs:
1. TradingView webhook alerts (zero received)
2. Hyperliquid + Drift market snapshots (138 events, funding/OI only)

All macro/RSS data is display-only. The `sentiment` field on `MacroHeadline` objects is never consumed by any scoring agent.

---

## Files Changed

| File | Change |
|------|--------|
| `services/market-data/app/providers/drift.py` | `fetch_context`: `/contracts` → `/stats/markets` (done in prior sub-pass) |
| `services/ingest-gateway/sources/drift.py` | `fetch_drift_contracts`: `/contracts` → `/stats/markets`; field-name shim maintained |

---

## Verification Results

**Live log confirmation of Drift 404:**
```
HTTP Request: GET https://data.api.drift.trade/contracts "HTTP/1.1 404 Not Found"
Error fetching Drift context: Client error '404 Not Found' ...
```
Seen repeating every ~6s in market-data logs.

**DB state (queried directly via `docker exec postgres psql`):**
- events: 138 rows, all `source='metrics'`
- signals: 825 rows, all score ±0.5
- opportunities: 0 rows

**Redis stream (x:signals.funding):**
- Length: 825 entries (matches DB signal count)
- Last 3 entries: score=0.5 (SOL LONG), score=-0.5 (ETH SHORT), score=-0.5 (BTC SHORT)
- All below the 2.0 threshold

---

## Known Limitations

1. **Container rebuild required** — The Drift fixes (`/contracts` → `/stats/markets`) are in code but not in running containers. Both market-data and ingest-gateway need `--build` to pick up the changes.

2. **Opportunity generation still blocked** — Even after rebuild, zero opportunities will appear until either: (a) TradingView alerts are sent, (b) the threshold is lowered, or (c) a market squeeze event occurs. The rebuild only fixes Drift data quality; it doesn't change the scoring dynamics.

3. **Drift ingest-gateway events** — `sources/drift.py` polls every 10 seconds but the events it creates go into `source='metrics', kind='market_snapshot'` alongside Hyperliquid events. Until the fix is deployed, Drift contributes zero events to the DB. After deploy, Drift will add events that may slightly change the OI delta measurement (Drift OI vs Hyperliquid OI are different venues).

4. **OI delta reliability** — The squeeze trigger uses OI from `metrics` events (both Hyperliquid and Drift combined). OI values from the two venues are not comparable directly (Hyperliquid reports in contracts, Drift in USD). The scoring code mixes them blindly. This could produce incorrect delta calculations.

5. **`exposure_penalty` always 0 today** — Because there are no positions. Correct behavior. Will become non-zero once the first executed order appears.

6. **RSS sentiment not wired** — This is documented as future work (Phase 4B). Not a bug.

---

## Next Recommended Step

**Immediate (before manual cockpit audit):**
1. Restart the full stack with rebuild:
   ```bash
   docker compose -f ops/compose.full.yml up -d --build
   ```
2. **Decide on the threshold question**: Is `OPPORTUNITY_THRESHOLD=2.0` still correct? Options:
   - Keep 2.0 and wire TradingView alerts
   - Lower threshold temporarily to test the full pipeline end-to-end
3. Send at least one test TradingView alert to confirm the pipeline produces an opportunity end-to-end

**Then (manual cockpit audit):**
- With a real opportunity in the DB, audit the full cockpit page-by-page:
  - Does the opportunity list surface it?
  - Does the preview flow work?
  - Does the evidence trail show the correct signal/event chain?
  - Does the score breakdown display (once 3G-4 ScoreBreakdownCard is built)?
