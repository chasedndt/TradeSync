# Market Normalization, All-Venues Aggregation & Test Suite Reconciliation

**Date:** 2026-03-25
**Phase:** Post-Backend-Truthfulness-Hardening — Market & Test Correctness
**Files changed:**
- `services/state-api/app/main.py`
- `services/state-api/tests/test_main.py`

---

## Why This Phase Was Needed

After the backend truthfulness hardening pass (TTL expiry, snapshot resilience), two categories of
technical debt remained:

1. **Stale tests** that targeted contracts that no longer existed:
   - `test_execute_action` asserted `status == "placed_dry_run"` and `"execution_id" in data` —
     neither field exists in the current `ExecutionResult` model.
   - `test_preview_action` and `test_preview_action_blocked` used a single `fetchrow.return_value`
     mock that covered all fetchrow calls in the endpoint. The preview endpoint now has three
     sequential fetchrow calls (opportunity, existing decision, signal); the mock returned the same
     dict for all three, causing the idempotency check to fire incorrectly on every test run.

2. **Missing all-venues aggregation**: The cockpit Market page consumed per-venue snapshots from
   `GET /state/market/snapshot?venue=drift&symbol=...` and had no backend endpoint that aggregated
   across venues. Any cross-venue metric (total OI, funding spread) had to be computed client-side
   with no awareness of which venues were available. The system had no way to declare "this OI
   figure only covers one of two venues."

---

## Part 1: Stale Tests Found and Fixed

### 1. `test_execute_action` — STALE → REPLACED

**Problem:**
- Asserted `data["status"] == "placed_dry_run"` — no such status value exists. Valid values are
  `"placed"`, `"rejected"`, `"error"`.
- Asserted `"execution_id" in data` — no such field in `ExecutionResult`. The field is `order_id`.
- Mock only set `conn.execute.return_value`; did not mock `conn.fetchrow`. The default AsyncMock
  for fetchrow returned a truthy AsyncMock, causing `json.loads(AsyncMock()["response"])` to raise
  TypeError, which was caught and returned as `status="error"`. Test expected 200 with
  `"placed_dry_run"` — test was silently broken.

**Fix:** Replaced with two tests:
- `test_execute_action_decision_not_found` — verifies 404 when decision_id is unknown.
- `test_execute_action_result_contract` — verifies the actual `ExecutionResult` shape:
  required fields present, `execution_id` absent, status in `("placed", "rejected", "error")`.

### 2. `test_preview_action` — STALE → FIXED

**Problem:** `conn.fetchrow.return_value = {"symbol": "BTC-PERP"}` applied to all fetchrow calls.
The second fetchrow call (idempotency check for existing decision) returned `{"symbol": "BTC-PERP"}`
which is truthy, triggering the early-return path. That path accessed `existing_decision["id"]`
which raised `KeyError`, caught as HTTPException(500). Test expected 200.

**Fix:** Uses `conn.fetchrow.side_effect = [MOCK_OPP_ROW, None, None]` to correctly return:
1. Full opportunity row (call 1)
2. No existing decision (call 2)
3. No latest signal (call 3)

### 3. `test_preview_action_blocked` — STALE → FIXED

**Same root cause.** Same fix with `side_effect` for `[luna_row, None, None]`.

**Added:** `test_preview_action_returns_cached_when_decision_exists` — explicitly tests the
idempotency path where an existing decision IS returned.

---

## Part 2: Market Normalization Rules (Canonical Definitions)

These rules are implemented in `services/market-data/app/processors/normalizer.py` and
`snapshotter.py`. This document makes them explicit for backend and cockpit consumers.

### Open Interest (OI)

| Field | Unit | Source | Notes |
|-------|------|--------|-------|
| `oi.current_usd` | USD notional | Normalizer | **Always USD.** If exchange reports in asset units, normalizer multiplies by mark_price at poll time. |
| `oi.horizons[window].delta_usd` | USD | Snapshotter | Absolute change in current_usd over window (5m, 15m, 1h, 4h, 24h) |
| `oi.horizons[window].delta_pct` | % | Snapshotter | Percentage change relative to window start |
| `oi.regime` | enum | Snapshotter | `build` / `unwind` / `flat` — derived from delta_pct thresholds |

**OI cross-venue aggregation:** `total_usd` is the arithmetic sum of `oi.current_usd` from venues
where data is available. It is never imputed for missing venues. If any venue is missing, the
`MarketAggregateResponse.partial` flag is `true` and `oi.missing_venues` lists the excluded venues.

### Funding Rate

| Field | Unit | Source | Notes |
|-------|------|--------|-------|
| `funding.horizons.now` | Decimal rate per 8h | Normalizer | e.g., `0.0001` = 0.01% per 8h |
| `funding.horizons.h8` | Same | Snapshotter | 8h rolling average |
| `funding.horizons.h24` | Same | Snapshotter | 24h rolling average |
| `funding.annualized_24h` | % annual | Snapshotter | `h24_avg * (365 * 3) * 100` |
| `funding.regime` | enum | Snapshotter | `extreme_positive / elevated_positive / neutral / elevated_negative / extreme_negative` |

**Funding cross-venue:** Rates are NOT averaged across venues. Venues are independent markets.
The aggregate endpoint provides `funding.spread` (absolute difference in BPS) only when exactly 2
venues have live `horizons.now` data. When spread is `null`, the notes array explains why.

### OI Delta Windows

Defined in `MarketSnapshotter.windows`:
- `5m`, `15m`, `1h`, `4h`, `24h`, `7d`

Exposed per-venue via `per_venue[venue].oi.horizons`. Not re-aggregated at the cross-venue level
(delta timing would not be comparable if venues had different data ages).

### Regime Fields

| Field | Meaning |
|-------|---------|
| `funding.regime` | Qualitative label for current funding pressure |
| `oi.regime` | Qualitative label for OI trend direction |
| `volume.regime` | `high / normal / low` relative to 7d average |
| `regimes.market_condition` | Composite condition: `trending_healthy / squeeze_risk / capitulation / choppy / unknown` |
| `regimes.confidence` | `high / medium / low` — reflects data availability |

---

## Part 3: New Endpoint — `GET /state/market/aggregate/{symbol}`

### Purpose

Provides an explicitly all-venues aggregate for the cockpit Market page. The endpoint:
- Always sets `scope = "all_venues"` — cockpit must not assume single-venue
- Always reports `partial: true` if any known venue was unavailable
- Always includes `per_venue` entries for every `KNOWN_VENUES` member (None if unavailable)
- Never implies an all-venues OI total unless `contributing_venues` = all known venues
- Provides funding spread only when exactly 2 venues have live rate data

### Config

`KNOWN_VENUES` env var (default: `"drift,hyperliquid"`) defines which venues are expected.
If a venue is absent from the snapshot store, it is reported as `available=false`.

### Response Contract

```json
{
  "symbol": "BTC-PERP",
  "scope": "all_venues",
  "aggregate_ts": "2026-03-25T10:00:00.000000",
  "partial": false,
  "venue_availability": [
    {"venue": "drift", "available": true, "data_age_ms": 450},
    {"venue": "hyperliquid", "available": true, "data_age_ms": 310}
  ],
  "oi": {
    "total_usd": 5000000.0,
    "per_venue": {"drift": 3000000.0, "hyperliquid": 2000000.0},
    "contributing_venues": ["drift", "hyperliquid"],
    "missing_venues": [],
    "regime_per_venue": {"drift": "build", "hyperliquid": "flat"}
  },
  "funding": {
    "per_venue": {"drift": 0.0001, "hyperliquid": 0.00015},
    "spread": 0.5,
    "available_venues": ["drift", "hyperliquid"],
    "missing_venues": []
  },
  "per_venue": {
    "drift": { ...full snapshot... },
    "hyperliquid": { ...full snapshot... }
  },
  "notes": []
}
```

**Partial example (hyperliquid down):**

```json
{
  "partial": true,
  "oi": {
    "total_usd": 3000000.0,
    "contributing_venues": ["drift"],
    "missing_venues": ["hyperliquid"]
  },
  "funding": {
    "spread": null,
    "available_venues": ["drift"],
    "missing_venues": ["hyperliquid"]
  },
  "per_venue": {
    "drift": { ...full snapshot... },
    "hyperliquid": null
  },
  "notes": ["hyperliquid: unavailable — connection refused"]
}
```

### Single-Venue Snapshot — `scope` Field Added

`GET /state/market/snapshot?venue=drift&symbol=BTC-PERP` now includes `"scope": "single_venue"` in
the response, added by state-api as a default on `MarketSnapshotResponse`. This allows cockpit code
to distinguish single-venue from aggregate responses without inspecting the URL.

---

## Model Changes

| Model | Change |
|-------|--------|
| `MarketSnapshotResponse` | Added `scope: str = "single_venue"` |
| `VenueAvailability` | New — per-venue availability record |
| `OIAggregate` | New — OI aggregate with per-venue breakdown |
| `FundingAggregate` | New — funding per-venue with spread |
| `MarketAggregateResponse` | New — full all-venues aggregate response |

---

## Endpoint Changes

| Endpoint | Change |
|----------|--------|
| `GET /state/market/snapshot` | Response now includes `scope: "single_venue"` |
| `GET /state/market/aggregate/{symbol}` | New endpoint |

---

## Tests Added / Updated

| Test | Type |
|------|------|
| `test_execute_action_decision_not_found` | New — replaces stale test |
| `test_execute_action_result_contract` | New — replaces stale test |
| `test_preview_action` | Fixed (side_effect mocking) |
| `test_preview_action_blocked` | Fixed (side_effect mocking) |
| `test_preview_action_returns_cached_when_decision_exists` | New |
| `test_single_venue_snapshot_has_scope_single_venue` | New |
| `test_market_aggregate_scope_is_all_venues` | New |
| `test_market_aggregate_all_venues_available` | New |
| `test_market_aggregate_one_venue_down` | New |
| `test_market_aggregate_both_venues_down` | New |
| `test_market_aggregate_per_venue_always_present` | New |
| `test_market_aggregate_venue_availability_flags` | New |
| `test_market_aggregate_funding_spread_none_when_one_venue` | New |
| `test_market_aggregate_oi_regime_per_venue` | New |

---

## Verification Steps

```bash
# Run full test suite
cd services/state-api
pytest tests/test_main.py -v

# Verify aggregate endpoint (with stack running)
docker compose -f ops/compose.full.yml up -d
curl http://localhost:8000/state/market/aggregate/BTC-PERP | jq '{scope, partial, "oi_total": .oi.total_usd, "contributing": .oi.contributing_venues}'

# Verify single-venue snapshot now has scope field
curl "http://localhost:8000/state/market/snapshot?venue=drift&symbol=BTC-PERP" | jq .scope
# → "single_venue"

# Verify partial state when one venue down
docker compose -f ops/compose.full.yml stop exec-drift-svc
curl http://localhost:8000/state/market/aggregate/BTC-PERP | jq '{partial, "missing_oi": .oi.missing_venues}'
```

---

## Known Limitations

- `GET /state/market/aggregate/{symbol}` makes sequential HTTP requests to market-data (one per
  venue). If market-data is down entirely, both venues will be marked unavailable. Consider
  parallelizing with `asyncio.gather` in a future optimization pass.
- OI delta windows (`oi.horizons`) are exposed per-venue but not cross-venue aggregated. Cross-venue
  delta aggregation is left for a future analytics layer.
- Regime synthesis across venues (e.g., a cross-venue `market_condition`) is not implemented.
  Per-venue regimes are available via `per_venue[venue].regimes`.
- `KNOWN_VENUES` is read at module load time. Adding a new venue requires restarting state-api.

---

## Next Recommended Step

**Phase 3E — Execution Authorization Hardening:**
With the backend truthful about both its own state and market data scope, the next step is
execution path hardening:
- Wallet-linked signer validation before `/actions/execute`
- DB-level idempotency enforcement for `exec_orders` (prevent double-execution on network retry)
- Circuit-breaker auto-reset logic in exec services
- On-chain txid verification in the audit trail via `/state/evidence`
