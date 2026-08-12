# Phase 3F-1: Exposure Data Wiring in fusion-engine

**Date:** 2026-03-27
**Phase:** 3F-1 — Lifecycle Hardening (first item)
**Scope:** Narrow fix — exposure penalty now works in EnhancedScorer

---

## What Bug Was Fixed

The `fusion-engine` worker called `EnhancedScorer.compute_enhanced_score()` with
`exposure_data=None` on every signal. This meant the **exposure penalty was always 0.0**
regardless of how concentrated positions were.

The `EnhancedScorer` already had full logic for:
- Symbol concentration penalty (up to -0.5 when exposure > 50% of limit)
- Margin stress penalty (up to -1.0 when margin utilization > 80%)

Neither of these ever fired. A trade with $24,900 in BTC exposure (just under the $25k limit)
got the same opportunity score as a trade with zero existing exposure.

---

## Why It Mattered

EnhancedScorer is the only place in the pipeline that applies portfolio-level awareness before
an opportunity is created. The RiskGuardian also checks exposure — but at preview time, which
is after the opportunity already exists. The EnhancedScorer check is earlier (scoring phase)
and affects the final score that determines whether an opportunity is actionable at all.

Without exposure data, over-concentrated positions could generate high-scoring opportunities
that would pass the threshold check and enter the DB, only to be rejected later at preview.
The fix makes the scoring phase reflect the real portfolio state.

---

## Files Changed

| File | Change |
|------|--------|
| `services/fusion-engine/app/worker.py` | Added `fetch_exposure_data()` function; wired into `process_message()` before `compute_enhanced_score()` call |
| `services/fusion-engine/requirements.txt` | Added `httpx==0.27.2`, `pytest==8.3.3`, `pytest-asyncio==0.24.0` |
| `services/fusion-engine/tests/__init__.py` | Created (empty, marks tests as package) |
| `services/fusion-engine/tests/test_worker.py` | Created — 8 tests covering exposure wiring and fallback |

---

## The /state/positions Contract Used

**Endpoint:** `GET http://state-api:8000/state/positions`

**Response:** `List[Position]` where each position is:
```json
{
  "venue": "hyperliquid",
  "symbol": "BTC-PERP",
  "side": "LONG",
  "size_usd": 15000.0,
  "entry_price": 93000.0,
  "mark_price": 93500.0,
  "pnl_usd": 80.0,
  "leverage": 3.0,
  "timestamp": "2026-03-27T10:00:00"
}
```

The relevant field is `size_usd` — the USD notional of the position.

Note: the state-api `preview_action` handler fetches positions directly from exec services
and uses `pos.get("notional", 0)` instead of `size_usd`. That is a separate pre-existing bug
in the preview handler, not fixed here.

---

## exposure_data Shape Passed into EnhancedScorer

```python
{
    "by_symbol": {
        "BTC-PERP": 15000.0,   # total USD notional across all venues for this symbol
        "ETH-PERP": 5000.0,
    },
    "margin_utilization": 0.40  # total_notional / ACCOUNT_EQUITY_USD, capped at 1.0
}
```

**How it's built from positions:**
```python
by_symbol = {}
for pos in positions:
    sym = pos["symbol"]
    by_symbol[sym] = by_symbol.get(sym, 0.0) + abs(pos["size_usd"])

total_notional = sum(by_symbol.values())
margin_utilization = min(total_notional / ACCOUNT_EQUITY_USD, 1.0)
```

**ACCOUNT_EQUITY_USD default:** `$50,000` — configurable via `ACCOUNT_EQUITY_USD` env var.
This matches the assumption already used in `state-api/app/main.py` preview_action handler.

---

## What EnhancedScorer Does with exposure_data

From `libs/tradesync_core/tradesync_core/scoring.py`:

```python
# Symbol concentration penalty
symbol_exposure = exposure_data["by_symbol"].get(symbol, 0)
if symbol_exposure > max_exposure_per_symbol * 0.5:  # > $12,500 (default)
    exposure_ratio = symbol_exposure / max_exposure_per_symbol  # max_exposure = $25,000
    concentration_penalty = min(exposure_ratio, 1.0) * -0.5    # max -0.5

# Margin stress penalty
if margin_utilization > margin_stress_threshold:  # > 0.80
    stress_fraction = (margin_utilization - 0.80) / (1.0 - 0.80)
    margin_penalty = stress_fraction * -1.0        # max -1.0
```

Combined maximum exposure penalty: **-1.5 points** off the final score.

---

## New Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `STATE_API_URL` | `http://state-api:8000` | Base URL for state-api (positions fetch) |
| `ACCOUNT_EQUITY_USD` | `50000.0` | Assumed account equity for margin utilization |
| `POSITIONS_FETCH_TIMEOUT` | `1.5` | Timeout in seconds for positions HTTP call |

---

## Fallback Behavior When state-api Is Unavailable

The fetch is fully wrapped:

- HTTP non-200 response → logs `"HTTP {status}"` → returns `None`
- Any exception (timeout, connection refused, JSON error) → logs the exception → returns `None`
- `None` is passed as `exposure_data` to `EnhancedScorer`
- `EnhancedScorer` skips the exposure penalty block when `exposure_data is None` (existing behavior)
- Opportunity creation proceeds normally — exposure_penalty = 0.0 in this case

**The worker loop never blocks or crashes due to a positions fetch failure.**

---

## Tests Added

File: `services/fusion-engine/tests/test_worker.py`

| Test | What It Proves |
|------|---------------|
| `test_fetch_exposure_data_success` | Correct `by_symbol` and `margin_utilization` from real position list |
| `test_fetch_exposure_data_empty_positions` | Returns zero-exposure dict (not None) when position list is empty |
| `test_fetch_exposure_data_multiple_venues_same_symbol` | size_usd summed correctly across venues for same symbol |
| `test_fetch_exposure_data_margin_utilization_capped_at_one` | margin_utilization never > 1.0 |
| `test_fetch_exposure_data_http_error_returns_none` | Non-200 HTTP response → None |
| `test_fetch_exposure_data_timeout_returns_none` | Network exception → None |
| `test_process_message_passes_exposure_data_to_scorer` | Confirms `compute_enhanced_score` receives fetched exposure_data (not None) |
| `test_process_message_falls_back_to_none_when_positions_unavailable` | Opportunity still created when positions endpoint fails |
| `test_process_message_exposure_data_symbol_key_matches_normalized_symbol` | Symbol is normalized before being passed to fetch_exposure_data |
| `test_process_message_below_threshold_does_not_fetch_exposure` | Sub-threshold signals are skipped before any upstream fetch |

---

## Verification Steps

```bash
# 1. Syntax check
cd services/fusion-engine
python -c "import ast; ast.parse(open('app/worker.py').read()); print('OK')"

# 2. Run tests (requires pytest-asyncio installed)
pip install pytest pytest-asyncio httpx
pytest tests/test_worker.py -v

# 3. Integration check (system running)
# Start the stack and watch fusion-engine logs:
docker compose -f ops/compose.full.yml logs -f fusion-engine
# Expected on each processed signal: one of:
#   [Worker] Exposure fetched: BTC-PERP=$15000 total=$15000 margin_util=30.0%
#   [Worker] /state/positions returned HTTP 503 — exposure_data=None
#   [Worker] Failed to fetch exposure data: ... — falling back to exposure_data=None
```

---

## Known Limitations

1. **ACCOUNT_EQUITY_USD is a static assumption.** Real account equity changes as positions are filled and PnL accrues. A proper fix would fetch account equity from the exchange API. For now, the $50k default matches the assumption already in state-api's preview handler.

2. **The preview_action handler has a related bug** — it uses `pos.get("notional", 0)` but the Position model field is `size_usd`, so its exposure check also always gets 0. This is a separate bug in `state-api/app/main.py` and was explicitly left out of scope for this fix.

3. **Positions from exec services may include mock data** — when `DRY_RUN=true`, exec services return hardcoded mock positions (BTC-PERP $1200.50). This means in dry-run mode, the exposure penalty will fire based on mock data, not real positions. This is acceptable for development; when `DRY_RUN=false` is set for real trading, positions will be real.

4. **Timeout is 1.5s** — if state-api is slow (DB contention, cold pool), it may time out during peak scoring cycles. Monitor `[Worker] Failed to fetch exposure data: connection timeout` in logs. Adjust `POSITIONS_FETCH_TIMEOUT` env var if needed.

---

## Next Recommended Step

**Phase 3F-2: Fix `blocked` opportunity status**

When `RiskGuardian` rejects at preview phase, the opportunity currently stays in `new` status.
This allows repeated preview attempts on an opportunity that is fundamentally ineligible
(e.g., wrong symbol on DNT list, signal permanently stale).

Fix: In `state-api/app/main.py` `preview_action()`, when `risk_verdict.allowed == False`
and the reason is non-transient (DNT, DUPLICATE, MIN_QUALITY, STALE_DATA):
- `UPDATE opportunities SET status = 'blocked' WHERE id = $opp_id`
- Return the PreviewResponse with the rejection details

This requires adding `'blocked'` to the valid status set, updating the TTL expiry query
to also skip `'blocked'` rows, and ensuring the cockpit Opportunities page can filter/display it.
