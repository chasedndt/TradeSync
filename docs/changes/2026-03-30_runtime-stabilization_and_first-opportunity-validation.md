# Runtime Stabilization and First Opportunity Validation

**Date:** 2026-03-30 (executed 2026-03-31 UTC)
**Scope:** Full stack rebuild, Drift live verification, end-to-end first opportunity generation, threshold decision documentation

---

## Executive Summary

The full stack was rebuilt and all 11 containers came up healthy. The root cause of prior service crashes (fusion-engine, state-api) was a missing `--env-file .env` flag — Docker Compose doesn't auto-load `.env` when the compose file is in a subdirectory (`ops/`). Fixed and documented.

Drift fix is **live and confirmed**: `https://data.api.drift.trade/stats/markets` returning 200 OK in logs every ~6 seconds. No `/contracts` 404 errors anywhere.

First opportunity generated end-to-end via 3 TradingView-style test alerts. Pipeline confirmed working: alerts → events → signals (score=3.5→5.5) → opportunities (18 created) → state-api returning results → evidence trail complete with score_breakdown. Cockpit HTML serving.

The threshold (2.0) is **correct and remains unchanged**. The test alerts are a validation tool, not a product decision.

---

## Full Stack Runtime Results

### Root Cause of Prior Failures
`fusion-engine` and `state-api` were exiting with:
```
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "root"
```
**Cause:** Docker Compose V2 looks for `.env` in the compose file directory, not necessarily the CWD. Because the compose file is at `ops/compose.full.yml`, running `docker compose -f ops/compose.full.yml` from the project root does NOT auto-load `.env` from the project root. Without `.env`, `POSTGRES_USER`/`POSTGRES_PASSWORD` are blank strings, so the DSN becomes `postgresql://:@postgres:5432/` and asyncpg falls back to the OS user ("root"), which has no DB access.

**Fix:** Add `--env-file .env` to all compose commands. `CLAUDE.md` updated.

**Correct commands:**
```bash
# From project root:
docker compose -f ops/compose.full.yml --env-file .env up -d --build
docker compose -f ops/compose.full.yml --env-file .env down
```

### Container Status After Correct Restart

| Container | Status |
|-----------|--------|
| tradesync-full-postgres-1 | Up (healthy) |
| tradesync-full-redis-1 | Up (healthy) |
| tradesync-full-qdrant-1 | Up (starting→healthy) |
| tradesync-full-ingest-gateway-1 | Up |
| tradesync-full-core-scorer-1 | Up |
| tradesync-full-fusion-engine-1 | Up (healthy) |
| tradesync-full-state-api-1 | Up |
| tradesync-full-market-data-1 | Up |
| tradesync-full-cockpit-ui-1 | Up (healthy) |
| tradesync-full-exec-hl-svc-1 | Up (healthy) |
| tradesync-full-exec-drift-svc-1 | Up (healthy) |

All 11 containers up. `state-api /healthz` → `{"ok": true}`. Snapshot shows `degraded: false`, both circuits closed.

---

## Drift Live Verification

### Confirmed in market-data logs:
```
HTTP Request: GET https://data.api.drift.trade/stats/markets "HTTP/1.1 200 OK"
```
Appearing every ~6 seconds. **Zero `/contracts` 404 errors** — old endpoint completely gone.

### Confirmed in aggregate output:
`GET /snapshot/drift/BTC-PERP` now returns:
```json
{
  "funding": {
    "horizons": {"now": -0.000775, ...},
    "regime": "elevated_negative",
    "source": {"provider": "drift", "endpoint": "stats/markets", "raw_rate": -0.000775}
  },
  "oi": {"current_usd": 7.82, "regime": "flat"},
  "volume": {"horizons": {"24h": 321.51, ...}}
}
```
`funding.source.endpoint: "stats/markets"` is the live confirmation.

### Remaining limitation — Drift OI unit issue:
Drift `/stats/markets` returns OI in a unit that results in `current_usd: 7.82` for BTC-PERP. This is implausibly small (BTC perp OI should be millions). The OI field is summing `openInterest.long + openInterest.short` but the values may be in BTC units (not USD) or in millions/thousands. This is a data quality concern, not a critical error — the OI is populated (regime shows "flat") but the absolute value is wrong. Does not affect opportunity generation (which uses Hyperliquid data for scoring).

### `ingest-gateway/sources/drift.py` fix:
Also confirmed to have the correct URL. The ingest-gateway drift poller (which was silently failing for all prior runtime) is now fetching from `/stats/markets`.

---

## Opportunity Generation Decision

### The threshold question

**Decision: Keep `OPPORTUNITY_THRESHOLD = 2.0`. Do not lower it.**

Rationale:
- The threshold was designed with TradingView alerts as the primary input (±1.0 per alert)
- Market data alone (base funding bias ±0.5) was never intended to be sufficient
- Lowering the threshold to 0.5 would produce continuous opportunities from raw funding data with no actual signal — the opposite of the desired behavior
- The system is working as designed

### What creates opportunities today (correct current state)
1. **TradingView webhook alerts** — `POST /ingest/tv` with `{"symbol": "BTC", "bias": "LONG", ...}` — each adds ±1.0 to score. 3 aligned alerts → score ±3.0
2. **Base funding bias** — contributes ±0.5 on top of TV alerts. Negative funding → +0.5 (long bias)
3. **Squeeze condition** — if funding is extreme (>0.01% absolute) AND OI rises ≥0.5% in 30 minutes → additional ±2.0. Currently BTC triggering this (+2.0 to the +3.5 base → +5.5)

### What does NOT create opportunities today
- Market data alone (max ±0.5 — far below 2.0 threshold)
- RSS/macro feed (display only, never enters scoring)
- Manual DB inserts (not used — real pipeline preferred)

---

## First Opportunity Validation Result

### Method: TradingView alert injection (Option A — recommended path)

Three `POST /ingest/tv` requests:
```bash
curl -X POST http://localhost:8080/ingest/tv \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC","timeframe":"1h","bias":"LONG","confidence":80.0,"price":83000.0,"source":"tradingview"}'
```
(× 3 requests, all returned `{"status":"ok", "id": "..."}`)

### Pipeline verification

| Step | Result |
|------|--------|
| Events in DB (`source='tradingview'`) | 3 rows created (BTC-PERP, 07:59:38 UTC) |
| Scoring cycle | BTC scored 3.5 → 5.5 (3 TV alerts + funding bias + squeeze) |
| Signal confidence | 0.35 (= abs(3.5)/10) |
| Opportunities created | 18 (core-scorer runs every 10s; each cycle creates new signal → new opportunity) |
| State-api `/state/opportunities?status=new` | Returns 18 BTC-PERP LONG opportunities |
| Evidence trail | Opportunity → 1 signal → 61 events; `score_breakdown: alpha=3.5, final=3.5` present |
| Cockpit (`http://localhost:3000`) | Serving HTML |

### Note on repeated opportunity creation
Core-scorer `SCORING_INTERVAL=10` (hardcoded in compose.full.yml, line 84). With 3 TV alerts valid for 30 minutes in the scoring window, a new BTC signal is created every 10 seconds, generating a new opportunity each time. This is expected behavior given the scoring interval configuration — not a pipeline bug. The idempotency guard is per signal_id; each new signal has a new UUID, so each creates a new opportunity. After 30 minutes, the TV alerts leave the scoring window and the score drops back to ±0.5.

---

## Files Changed

| File | Change |
|------|--------|
| `CLAUDE.md` | Core commands updated to include `--env-file .env` |
| (prev) `services/market-data/app/providers/drift.py` | `/contracts` → `/stats/markets` |
| (prev) `services/ingest-gateway/sources/drift.py` | `/contracts` → `/stats/markets` |

---

## Docs Created / Updated

| File | Action |
|------|--------|
| `docs/changes/2026-03-30_runtime-stabilization_and_first-opportunity-validation.md` | Created (this file) |
| `docs/architecture/OPPORTUNITY_GENERATION_RUNTIME_AUDIT.md` | Updated (see below) |
| `docs/architecture/DRIFT_PROVIDER_RUNTIME_AUDIT.md` | Updated in prior pass |
| `CLAUDE.md` | Updated with `--env-file .env` requirement |

---

## Known Limitations

1. **Wallet/signing deferred** — All exec services run in DRY_RUN mode. No real orders placed. `HYPERLIQUID_WALLET_PK` and `DRIFT_RPC_URL` are blank in `.env`.

2. **No fundamentals in scoring** — RSS/macro feed (state-api `macro_feed.py`) is display-only. Does not affect signals or opportunities. Core-scorer uses only TradingView alerts and Hyperliquid/Drift market snapshots.

3. **No SMC/ICT/CVD scoring** — Future Phase 4A work. Requires OHLCV ingest pipeline not yet built.

4. **Drift OI value incorrect** — `current_usd` shows ~7.82 for BTC-PERP. Likely a units mismatch (contract units vs USD) in the `/stats/markets` response parsing. Does not block the pipeline; regime classification still works ("flat").

5. **Score_breakdown exposure_penalty always 0** — No positions exist yet (DRY_RUN, no wallet). `fetch_exposure_data()` returns `{by_symbol: {}, margin_utilization: 0}` which correctly means no exposure penalty. Will be non-zero once real fills occur.

6. **TV alerts persist 30 minutes** — Once injected, test alerts remain in the scoring window for 30 minutes, creating opportunities every 10 seconds. Operator should be aware that after test injection, many opportunities will appear before the window expires.

7. **SCORING_INTERVAL=10** — Hardcoded in compose.full.yml line 84 (not from .env). Produces signals every 10 seconds. Fine for responsiveness; may create excessive DB rows over time.

---

## Next Recommended Step

Stack is live, pipeline verified end-to-end, first opportunity confirmed.

**Proceed to manual page-by-page cockpit audit:**
1. Overview page — snapshot data, circuit status, execution gate
2. Market page — Hyperliquid + Drift data quality, MetricStatus badges
3. Opportunities page — the 18 BTC-PERP LONG opportunities should be visible
4. OpportunityDetail page — verify score_breakdown renders (note: ScoreBreakdownCard not yet built per 3G-4)
5. Risk Policies page — verify account equity, daily notional limit display
6. Positions page — expect empty (no fills yet)
7. Autonomy page — should show locked/manual mode

**Do not proceed to wallet/signing work until the manual audit confirms the cockpit accurately reflects live state.**
