# Phase 3F-2: Fix Preview-Time Exposure in state-api

**Date:** 2026-03-27
**Phase:** 3F-2 — Lifecycle Hardening (second item)
**Scope:** Narrow fix — preview_action now uses correct exec service URLs and correct position field name

---

## Summary

### What bug existed
`preview_action()` in `services/state-api/app/main.py` fetched position data from exec services
to compute `symbol_exposure_usd` and `margin_utilization` before calling `RiskGuardian.check()`.
Three bugs in the same 12-line block caused those values to always be 0.0:

1. **Wrong URL for drift** — path used `req.venue[:2]` = `"dr"`, producing `/exec/dr/positions`.
   The real endpoint is `/exec/drift/positions`.
2. **Wrong URL for hyperliquid** — hostname used `exec-{req.venue}-svc` = `exec-hyperliquid-svc`,
   and path was `/exec/hy/positions`. The real host is `exec-hl-svc` and path is `/exec/hl/positions`.
3. **Wrong field name** — two lines used `pos.get("notional", 0)`. The Position model field
   is `size_usd`. `notional` does not exist in the Position schema and always defaults to 0.

### Why it mattered in real system behavior
`RiskGuardian` checks `symbol_exposure_usd` and `margin_utilization` at preview time to fire
`EXPOSURE_TOO_HIGH` and `MARGIN_STRESS` vetoes. With both inputs always 0.0, those two veto codes
could never fire during preview, regardless of actual portfolio state. An account at $30k BTC-PERP
(above the $25k limit) would pass preview as if it had zero existing exposure.

---

## Confirmed Contract

### Positions endpoint shape — confirmed from exec service source

Both exec services define an identical `Position` model:

| Field | Type | Source file |
|-------|------|-------------|
| `venue` | str | exec-hl-svc/app/main.py:45, exec-drift-svc/app/main.py:55 |
| `symbol` | str | exec-hl-svc/app/main.py:46, exec-drift-svc/app/main.py:56 |
| `side` | str | |
| **`size_usd`** | **float** | **exec-hl-svc/app/main.py:48, exec-drift-svc/app/main.py:58** |
| `entry_price` | float | |
| `mark_price` | float | |
| `pnl_usd` | float | |
| `leverage` | float | |
| `timestamp` | datetime | |

**`notional` does not exist in either Position model.** It is not an alias, not a legacy field,
not a computed field. `pos.get("notional", 0)` always returns 0 by default-fallback.

### Canonical endpoint URLs — confirmed from `get_aggregated_positions()` in same file

```python
# services/state-api/app/main.py lines 865–868
urls = {
    "drift":       "http://exec-drift-svc:8003/exec/drift/positions",
    "hyperliquid": "http://exec-hl-svc:8004/exec/hl/positions"
}
```

This URL map already existed in the same file and is used correctly by `get_aggregated_positions`.
`preview_action` was the only caller using a different (broken) derivation.

### Venue-specific notes
No differences in field names between venues. Both return `size_usd: float` as the USD notional
of the position. The `venue` default differs (`"hyperliquid"` vs `"drift"`) but this is irrelevant
to the exposure calculation.

---

## Root Cause

**File:** `services/state-api/app/main.py`
**Location:** `preview_action()`, lines 955–967 (before fix)

```python
# BROKEN: three bugs in this block
exposure_resp = await client.get(
    f"http://exec-{req.venue}-svc:800{3 if req.venue == 'drift' else 4}/exec/{req.venue[:2]}/positions",
    timeout=2.0
)
if exposure_resp.status_code == 200:
    positions = exposure_resp.json()
    for pos in positions:
        if pos.get("symbol") == symbol:
            symbol_exposure_usd = abs(pos.get("notional", 0))   # Bug 3
    total_notional = sum(abs(p.get("notional", 0)) for p in positions)  # Bug 3 again
    margin_utilization = total_notional / 50000.0
```

**Bug 1 (drift path):** `req.venue[:2]` = `"dr"` → `/exec/dr/positions` → 404 from exec-drift-svc.
**Bug 2 (hyperliquid host+path):** `exec-hyperliquid-svc` does not exist as a hostname; `/exec/hy/positions` is not a registered route. Both result in connection failure caught by the outer `try/except`, leaving exposure at 0.0.
**Bug 3 (field name):** `pos.get("notional", 0)` always 0. Even on the (theoretical) drift case where the host resolves, the field read was wrong.

Because all three bugs existed simultaneously, the `try/except` on the outer block silently swallowed connection errors for hyperliquid and returned exposure=0 for both venues.

---

## Fix Implemented

**File changed:** `services/state-api/app/main.py`

### Exact change

Replaced:
```python
exposure_resp = await client.get(
    f"http://exec-{req.venue}-svc:800{3 if req.venue == 'drift' else 4}/exec/{req.venue[:2]}/positions",
    timeout=2.0
)
if exposure_resp.status_code == 200:
    positions = exposure_resp.json()
    for pos in positions:
        if pos.get("symbol") == symbol:
            symbol_exposure_usd = abs(pos.get("notional", 0))
    total_notional = sum(abs(p.get("notional", 0)) for p in positions)
    margin_utilization = total_notional / 50000.0  # Assuming $50k account
```

With:
```python
_EXEC_POSITIONS_URLS = {
    "drift": "http://exec-drift-svc:8003/exec/drift/positions",
    "hyperliquid": "http://exec-hl-svc:8004/exec/hl/positions",
}
exposure_url = _EXEC_POSITIONS_URLS.get(req.venue)
if exposure_url:
    exposure_resp = await client.get(exposure_url, timeout=2.0)
    if exposure_resp.status_code == 200:
        positions = exposure_resp.json()
        for pos in positions:
            if pos.get("symbol") == symbol:
                symbol_exposure_usd = abs(pos.get("size_usd", 0))
        total_notional = sum(abs(p.get("size_usd", 0)) for p in positions)
        margin_utilization = total_notional / 50000.0  # Assuming $50k account
```

### What now gets passed to RiskGuardian
- `symbol_exposure_usd`: sum of `size_usd` for positions where `pos["symbol"] == symbol`
- `margin_utilization`: `sum(size_usd for all positions) / 50000.0`, capped implicitly at whatever the positions return

If the exec service is unreachable, the outer `try/except` still catches exceptions and `symbol_exposure_usd` / `margin_utilization` remain 0.0 — the same graceful degradation behavior as before, now applied to real positions when available.

---

## RiskGuardian Inputs After Fix

From `risk.py` thresholds (all env-configurable):

| Input | Default threshold | Veto code |
|-------|-------------------|-----------|
| `symbol_exposure_usd + size_usd > max_exposure_per_symbol` | $25,000 | `EXPOSURE_TOO_HIGH` |
| `margin_utilization > margin_stress_threshold` | 0.80 | `MARGIN_STRESS` |

**Before fix:** Both inputs always 0.0 → neither veto could fire.
**After fix:** Both inputs reflect real position sizes from exec services.

Check order in `RiskGuardian.check()` (relevant gates before exposure):
`EXEC_DISABLED` → `DNT` → `DUPLICATE` → `EXPIRY` → `STALE_DATA` → `MIN_QUALITY` → microstructure checks → **`MARGIN_STRESS`** → **`EXPOSURE_TOO_HIGH`**

`MARGIN_STRESS` fires first (line 189), then `EXPOSURE_TOO_HIGH` (line 198). Both are now reachable
with real position data.

---

## Tests Added / Updated

File: `services/state-api/tests/test_main.py`

### New helper
`_make_preview_http_mock(mock_http_cls, positions, venue)` — builds an httpx mock that:
- Returns `{}` for market-data URL (no microstructure)
- Returns `positions` for the canonical exec service URL for the given venue
- Returns HTTP 404 for any other URL (catches old broken URL patterns)

### Tests

| Test | What It Proves |
|------|----------------|
| `test_preview_action_exposure_uses_size_usd` | With `EXECUTION_ENABLED=true`, `size_usd=5000` and `notional=0` in positions: $5k+$5k=$10k < $25k limit → `allowed=True`, `reason_code="OK"`. Confirms low exposure passes cleanly. |
| `test_preview_action_exposure_too_high_vetoes` | **Decisive proof of fix:** With `EXECUTION_ENABLED=true`, `size_usd=30000` in positions: $30k+$5k=$35k > $25k limit → `allowed=False`, "EXPOSURE" in reason. With old `notional=0` code this would be $0+$5k=$5k → passes. Only reads correctly because `size_usd` is used. |
| `test_preview_action_positions_unavailable_does_not_block` | All HTTP calls raise exception. `symbol_exposure_usd=0`, `margin_utilization=0` → `allowed=True`. Graceful degradation preserved. |
| `test_preview_action_uses_canonical_hl_url` | Tracks all HTTP URLs called during preview with `venue="hyperliquid"`. Asserts: exactly one exec call, URL contains `exec-hl-svc` and `/exec/hl/positions`, does NOT contain `exec-hyperliquid-svc` or `/exec/hy/`. |

### Why `test_preview_action_exposure_too_high_vetoes` is the decisive test

With old code: `pos.get("notional", 0)` = 0 → `symbol_exposure_usd=0` → `0+5000=$5k < $25k` → `allowed=True` → assertion `allowed is False` **would fail**.
With new code: `pos.get("size_usd", 0)` = 30000 → `symbol_exposure_usd=30000` → `30000+5000=$35k > $25k` → `allowed=False` → assertion passes.

The test cannot pass on the old code. It is not watered down.

---

## Verification Steps

```bash
# 1. Syntax check
cd services/state-api
python -c "
import ast
with open('app/main.py', encoding='utf-8-sig') as f:
    ast.parse(f.read())
print('main.py OK')
"

# 2. Run the new exposure tests specifically
pip install pytest httpx fastapi asyncpg pydantic
pytest tests/test_main.py -v -k "exposure"

# 3. Run full test suite to check for regressions
pytest tests/test_main.py -v

# 4. Integration check (system running, EXECUTION_ENABLED=true)
# Send a preview request for an opportunity while BTC-PERP position > $25k exists.
# Expected: risk_verdict.allowed=False, reason contains "EXPOSURE"
# Before fix:  allowed=True (exposure always 0)
```

---

## Known Limitations

1. **`_EXEC_POSITIONS_URLS` is a local dict** — duplicates the map from `get_aggregated_positions`.
   Cosmetic debt; not a correctness issue.

2. **`ACCOUNT_EQUITY_USD` hardcoded at 50,000** — same static assumption used by fusion-engine
   (Phase 3F-1) and the existing preview handler. Real account equity is not fetched.
   `margin_utilization` is therefore approximate.

3. **`symbol_exposure_usd` accumulates only the first matching position** — the loop overwrites
   `symbol_exposure_usd` on each matching position rather than summing. If two venues both hold
   BTC-PERP, only the last one's value is used. This pre-existed the fix and is left in scope
   for a future cleanup; the URL fix alone makes the existing code meaningfully better.

4. **Only the venue in `req.venue` is queried** — preview fetches from the single target venue,
   not all venues. A full cross-venue exposure check would require both exec services.
   This also pre-existed the fix.

---

## Next Recommended Step

**Phase 3F-3: Fix `blocked` opportunity status**

When `RiskGuardian` rejects at preview phase with a non-transient reason (DNT, DUPLICATE,
MIN_QUALITY, STALE_DATA), the opportunity stays in `new` status, allowing repeated preview
attempts on a permanently ineligible opportunity.

Fix: In `preview_action()`, after `risk_engine.check()` returns `allowed=False` with a
non-transient reason code:
- `UPDATE opportunities SET status = 'blocked' WHERE id = $opp_id`
- Return the PreviewResponse with rejection details

Requires adding `'blocked'` to the valid status set and updating the TTL expiry query to
skip `'blocked'` rows. Do not introduce wallet or signing code.
