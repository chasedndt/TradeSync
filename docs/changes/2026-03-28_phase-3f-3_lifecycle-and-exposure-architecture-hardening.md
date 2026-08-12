# Phase 3F-3: Lifecycle and Exposure Architecture Hardening

**Date:** 2026-03-28
**Phase:** 3F-3 — Lifecycle Hardening (third pass)
**Scope:** Blocked status, TTL correctness, cross-venue exposure, account risk load centralization

---

## Summary

### What was wrong before

1. **No blocked status** — when `RiskGuardian` rejected a preview for a permanent reason (DNT, bad quality, stale signal), the opportunity stayed in `new` indefinitely. The cockpit could keep re-submitting it. The TTL sweep would eventually expire it, masking the real rejection reason.

2. **TTL sweep interacted correctly by accident, not by design** — the SQL `WHERE status IN ('new', 'previewed')` would never expire a future `blocked` row, but this was not documented and `blocked` didn't exist yet.

3. **Exposure overwrite bug** — the `for pos in positions` loop used `=` instead of `+=` for `symbol_exposure_usd`. With multiple positions in the same symbol across venues, only the last one's value was used. This underestimated exposure.

4. **Single-venue blindness** — `preview_action` only fetched positions from the request venue. A $20k position on drift was invisible when previewing a hyperliquid trade, allowing `EXPOSURE_TOO_HIGH` to be silently bypassed.

5. **Hardcoded 50000.0 literal** — the `margin_utilization` divisor was a raw literal buried inside `preview_action`. `account_equity` in `risk_engine.check()` defaulted to a different value (10000.0) since it was never passed. Two different equity assumptions in the same preview call.

6. **Account risk load undiscoverable** — no system endpoint revealed what capital base was assumed. Operators could not know the value without reading source code.

### What was fixed now

1. `blocked` status is now written when preview rejects with a non-transient reason code.
2. TTL docstring updated to explicitly exclude `blocked` — the exclusion is now intentional and documented, not accidental.
3. Symbol exposure now sums (`+=`) across all matching positions.
4. Preview now calls `_fetch_aggregated_positions()` which queries ALL venues, not just the request venue.
5. `ACCOUNT_EQUITY_USD` is a module-level constant derived from env var `ACCOUNT_EQUITY_USD` (default $50k). It is passed consistently to both the `margin_utilization` calculation and `risk_engine.check(account_equity=...)`.
6. `/state/risk/limits` now returns `account_equity_usd` so the assumption is discoverable from the running system.

### What remains out of scope

- Real-time account equity from exchange APIs (still static assumption)
- `blocked` status UI filtering in the cockpit (deferred to 3F-4)
- `blocked` opportunity cleanup/archival (no TTL sweep for blocked rows — they persist indefinitely)
- `DUPLICATE` reason code not classified as non-transient (intentional: writing blocked over a `previewed` or `executed` opportunity would be a lifecycle downgrade)

---

## Confirmed Status Model

| Status | Set by | When | TTL sweep touches? |
|--------|--------|------|--------------------|
| `new` | fusion-engine (DB insert) | On opportunity creation | YES — expires if stale |
| `previewed` | preview_action | On successful preview (allowed=True) | YES — expires if stale |
| `executed` | execute_action | After order confirmed | NO |
| `expired` | expire_stale_opportunities background task | When TTL elapsed | N/A (terminal) |
| `blocked` | preview_action (Phase 3F-3) | Non-transient risk rejection | NO (intentionally excluded) |

**DB constraint:** None. Status is `text NOT NULL DEFAULT 'new'`. Valid values enforced by application logic only.

---

## Blocked Classification Rule

### Definition
- **Non-transient**: The opportunity is structurally or permanently ineligible. Retrying will produce the same rejection regardless of time, market conditions, or portfolio state. Write `blocked`.
- **Transient**: The rejection reason depends on conditions that can change (rate limits, market microstructure, portfolio state, global kill-switch). Leave status as `new` to allow retrying.

### Classification table

| Reason code | Classification | Rationale |
|-------------|---------------|-----------|
| `EXEC_DISABLED` | TRANSIENT | Global kill-switch; operator can re-enable without changing the opportunity |
| `DNT` | **NON-TRANSIENT** | Symbol permanently blacklisted; the opportunity itself is worthless |
| `STALE_DATA` | **NON-TRANSIENT** | The signal that generated this opportunity is too old and will not get fresher |
| `EXPIRED` | **NON-TRANSIENT** | The opportunity has passed its TTL window; mirrors what the background task would do |
| `DUPLICATE` | TRANSIENT (excluded) | Fires when status is already `previewed` or `executed` — writing `blocked` would be a lifecycle downgrade; SQL guard `WHERE status = 'new'` also prevents it |
| `COOLDOWN` | TRANSIENT | Rate limit on preview attempts; clears as time passes |
| `LIMIT_POSITIONS` | TRANSIENT | Position count changes as trades open and close |
| `LIMIT_DAILY` | TRANSIENT | Daily notional limit resets at midnight |
| `MIN_QUALITY` | **NON-TRANSIENT** | Quality is a fixed property of this opportunity snapshot; won't improve |
| `MIN_SIZE` | **NON-TRANSIENT** | Request size is static for this opportunity lifecycle |
| `MAX_LEVERAGE` | **NON-TRANSIENT** | Derived from size/capital; static for this opportunity |
| `SPREAD_TOO_WIDE` | TRANSIENT | Market microstructure changes continuously |
| `SLIPPAGE_TOO_HIGH` | TRANSIENT | Market microstructure changes continuously |
| `DEPTH_TOO_THIN` | TRANSIENT | Market microstructure changes continuously |
| `LIQUIDITY_TOO_LOW` | TRANSIENT | Market microstructure changes continuously |
| `MARGIN_STRESS` | TRANSIENT | Account risk load changes as positions close |
| `EXPOSURE_TOO_HIGH` | TRANSIENT | Symbol exposure changes as positions close |
| `OK` | N/A | Allowed — no write needed |

**Implementation:** `_NON_TRANSIENT_CODES = frozenset({"DNT", "MIN_QUALITY", "STALE_DATA", "EXPIRED", "MIN_SIZE", "MAX_LEVERAGE"})`

**Write guard:** `WHERE id = $1 AND status = 'new'` — blocked write is only applied to opportunities currently in `new` status, preventing any lifecycle downgrade.

---

## Confirmed Position / Exposure Contract

**Source:** Both exec services define identical `Position` models (confirmed from source):

```
venue: str, symbol: str, side: str, size_usd: float,
entry_price: float, mark_price: float, pnl_usd: float,
leverage: float, timestamp: datetime
```

**Field for exposure:** `size_usd` (USD notional). No `notional` field exists.

**Aggregation rule (after Phase 3F-3):**
```python
all_positions = await _fetch_aggregated_positions(client)  # both venues
for pos in all_positions:
    if pos.get("symbol") == symbol:
        symbol_exposure_usd += abs(pos.get("size_usd", 0))  # SUM, not overwrite
total_position_usd = sum(abs(p.get("size_usd", 0)) for p in all_positions)
margin_utilization = total_position_usd / ACCOUNT_EQUITY_USD
```

**Is aggregation cross-venue?** YES. `_fetch_aggregated_positions` calls both `exec-drift-svc` and `exec-hl-svc` in parallel via `asyncio.gather`. Partial results are returned if one service is unavailable.

**Fallback:** If both services fail, `all_positions = []` → `symbol_exposure_usd = 0`, `margin_utilization = 0`. `EXPOSURE_TOO_HIGH` and `MARGIN_STRESS` won't fire. This is acceptable degraded behavior; the logging layer will show why.

---

## Account Risk Load / Capital Usage Model

### What the metric actually measures
`margin_utilization` (variable name kept for `RiskGuardian` interface compatibility) is NOT exchange margin utilization. It is:

```
account_risk_load = total_open_notional_across_all_venues / ACCOUNT_EQUITY_USD
```

This is a simplified **capital usage ratio** — what fraction of the configured account capital is currently deployed in open positions. It is not derived from exchange margin requirements, leverage, or actual unrealized P&L.

### Canonical source after Phase 3F-3
`ACCOUNT_EQUITY_USD = float(os.getenv("ACCOUNT_EQUITY_USD", "50000.0"))` — module-level constant in `services/state-api/app/main.py` (line ~136).

**Same env var used in fusion-engine** (`services/fusion-engine/app/worker.py`) — the assumption is now consistent across both services.

**Both `risk_engine.check()` calls now use this constant:**
- `margin_utilization = total_position_usd / ACCOUNT_EQUITY_USD`
- `account_equity=ACCOUNT_EQUITY_USD` passed to `risk_engine.check()`

### Discoverability
`GET /state/risk/limits` now returns `account_equity_usd` in the response. Operators can see the active assumption without reading source code.

### Env fallback
If `ACCOUNT_EQUITY_USD` is not set: defaults to `50000.0`. Set in Docker Compose / `.env` to match the real funded account size.

### Remaining imperfection (intentional)
Real account equity changes as positions are filled and P&L accrues. A complete implementation would fetch account balance from the exchange API. This is a static assumption — accurate at initial configuration, increasingly stale as trading activity occurs. Explicitly deferred.

---

## Files Changed

| File | Change |
|------|--------|
| `services/state-api/app/main.py` | Added `ACCOUNT_EQUITY_USD`, `_EXEC_POSITIONS_URLS`, `_NON_TRANSIENT_CODES` constants; added `_fetch_aggregated_positions()` helper; updated `get_aggregated_positions` route; rewrote preview exposure block; added blocked write-back; updated `expire_stale_opportunities` docstring; updated `RiskLimitResponse` + `/state/risk/limits` response |
| `services/state-api/tests/test_main.py` | Updated `test_preview_action_blocked` (stale assertion fix + new assertions); updated `test_preview_uses_canonical_urls_for_both_venues` (formerly `test_preview_action_uses_canonical_hl_url`); added 11 new tests |
| `docs/changes/2026-03-28_phase-3f-3_lifecycle-and-exposure-architecture-hardening.md` | This file |
| `docs/architecture/LIFECYCLE_AND_ACCOUNT_RISK_LOAD.md` | Architecture reference document |

---

## Tests Added / Updated

### Updated
| Test | What changed |
|------|--------------|
| `test_preview_action_blocked` | Added `EXECUTION_ENABLED=true` + httpx mock; fixed assertion from stale "blacklisted" to `reason_code=="DNT"`; added blocked write assertion |
| `test_preview_uses_canonical_urls_for_both_venues` | Renamed from `test_preview_action_uses_canonical_hl_url`; updated assertion from `len==1` to `len==2` (both venues now called) |

### New
| Test | What it proves |
|------|----------------|
| `test_preview_non_transient_min_quality_writes_blocked` | MIN_QUALITY rejection writes blocked, decision_id=None |
| `test_preview_transient_exec_disabled_does_not_write_blocked` | EXEC_DISABLED does NOT write blocked |
| `test_preview_transient_cooldown_does_not_write_blocked` | COOLDOWN does NOT write blocked |
| `test_preview_blocked_does_not_downgrade_previewed_status` | DUPLICATE on previewed opp → no blocked write |
| `test_preview_allowed_writes_previewed_not_blocked` | Happy path still writes `previewed`, not `blocked` |
| `test_expire_stale_does_not_touch_blocked` | TTL SQL WHERE clause has `new`+`previewed` but NOT `blocked` |
| `test_preview_exposure_sums_same_symbol_across_venues` | $15k HL + $10k drift summed to $25k, not last-write $10k → EXPOSURE_TOO_HIGH fires |
| `test_preview_cross_venue_position_included_in_exposure` | $20k drift position blocks HL preview even with 0 HL positions |
| `test_preview_account_risk_load_uses_account_equity_usd_env` | $41k total / $50k = 0.82 > 0.80 → MARGIN_STRESS fires (verifies $50k denominator) |
| `test_risk_limits_endpoint_includes_account_equity_usd` | GET /state/risk/limits returns `account_equity_usd` field |
| `test_fetch_aggregated_positions_helper_calls_both_venues` | Helper calls both exec URLs; combines results |
| `test_fetch_aggregated_positions_helper_partial_on_failure` | One venue failure returns partial results, not an error |

---

## Verification Steps

```bash
# 1. Syntax check
cd services/state-api
python -c "
import ast
with open('app/main.py', encoding='utf-8-sig') as f:
    ast.parse(f.read())
print('OK')
"

# 2. Run new Phase 3F-3 tests
pip install pytest pytest-asyncio httpx fastapi asyncpg pydantic
pytest tests/test_main.py -v -k "blocked or expire or cross_venue or account_risk or aggregated_positions or canonical_urls"

# 3. Run full test suite
pytest tests/test_main.py -v

# 4. Integration check (system running, EXECUTION_ENABLED=true)
# Preview a LUNA opportunity — expect blocked status written to DB:
# SELECT id, symbol, status FROM opportunities WHERE symbol = 'LUNA-PERP' ORDER BY snapshot_ts DESC LIMIT 5;
# Expected: status = 'blocked'

# 5. Verify capital base is discoverable:
# curl http://localhost:8000/state/risk/limits | jq '.account_equity_usd'
# Expected: 50000.0 (or configured override value)
```

---

## Known Limitations

1. **ACCOUNT_EQUITY_USD is still a static assumption** — real account balance from exchange APIs not implemented. Phase 3F-3 only centralizes the assumption; it doesn't make it dynamic.

2. **Blocked rows persist indefinitely** — no cleanup/archival. High-volume systems may accumulate blocked rows over time. A future cleanup sweep could archive `blocked` rows older than N days.

3. **No cockpit UI for blocked status** — the cockpit Opportunities page doesn't yet filter or surface `blocked` rows distinctly. Deferred to 3F-4.

4. **Partial position aggregation** — if one exec service is down, exposure is underreported. `EXPOSURE_TOO_HIGH` may not fire on the incomplete data. Acceptable degraded behavior.

5. **`account_equity_usd` not writable from system** — `/state/risk/limits` is GET-only. Changing `ACCOUNT_EQUITY_USD` requires env var update and service restart. A POST endpoint for live policy changes is out of scope for this phase.

---

## Next Recommended Step

**Phase 3F-4: Cockpit opportunity lifecycle visibility**

- Surface `blocked` status in the Opportunities page (filter chip, distinct visual treatment)
- Show `reason_code` for blocked rows so operators know why an opportunity was permanently rejected
- Optionally: add a cleanup endpoint to archive old `blocked`/`expired` rows beyond a retention window

Do NOT add wallet or signing work.
