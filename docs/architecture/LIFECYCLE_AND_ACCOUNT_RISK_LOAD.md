# TradeSync: Opportunity Lifecycle and Account Risk Load

**Last updated:** 2026-03-28 (Phase 3F-3)

---

## Opportunity Status Model

### All valid statuses

| Status | Meaning | Who sets it | Terminal? |
|--------|---------|------------|-----------|
| `new` | Created by fusion-engine; awaiting preview | fusion-engine (`db.insert_opportunity`) | No |
| `previewed` | Risk check passed; decision row created; awaiting execution | `preview_action()` on allowed=True | No |
| `executed` | Order dispatched to venue | `execute_action()` on success | Yes |
| `expired` | Aged out by server-side TTL sweep | `expire_stale_opportunities()` background task | Yes |
| `blocked` | Permanently rejected at preview time (non-transient reason) | `preview_action()` on non-transient rejection | Yes |

**DB constraint:** None. Status is `text NOT NULL DEFAULT 'new'`. The application is the sole enforcer of valid values and transitions.

### Transition diagram

```
         fusion-engine
              │
              ▼
           [ new ]
            / | \
           /  |  \
          /   |   \
   allowed  [blocked]  transient
   preview    │        rejection
      │       │          │
      ▼       │          │ (stays new, retry allowed)
  [previewed] │
      │       │
      ▼       ▼
  [executed]  [blocked] ← permanent (non-transient reason)
      │
  [expired] ← TTL sweep (only touches 'new' and 'previewed')
```

---

## TTL Expiry Behavior

**Task:** `expire_stale_opportunities()` runs every 60 seconds.

**SQL:**
```sql
UPDATE opportunities
SET status = 'expired'
WHERE status IN ('new', 'previewed')
  AND (
        (expires_at IS NOT NULL AND expires_at < now())
     OR (expires_at IS NULL AND snapshot_ts < now() - make_interval(secs => $1))
      )
```

**What TTL touches:**
- `new`: yes — unreviewed opportunities age out
- `previewed`: yes — stale previews age out if not executed
- `executed`: no — terminal, never touched
- `blocked`: **NO** — intentionally excluded; blocked rows are permanently rejected by explicit lifecycle logic, not by aging
- `expired`: no — already terminal

**Why `blocked` is excluded by the SQL:** The `WHERE status IN ('new', 'previewed')` clause is the mechanism. `blocked` is not in the list. This is correct and intentional as of Phase 3F-3.

---

## Non-Transient vs Transient Rejections

When `preview_action()` receives `allowed=False` from `RiskGuardian`, it classifies the rejection:

### Non-transient (writes `blocked`)

The opportunity is structurally or permanently ineligible. Retrying will produce the same rejection regardless of time or conditions.

| Reason code | Why it is non-transient |
|-------------|------------------------|
| `DNT` | Symbol is permanently blacklisted |
| `MIN_QUALITY` | Quality is a fixed snapshot property |
| `STALE_DATA` | Signal is too old and will not get fresher |
| `EXPIRED` | Past its TTL window |
| `MIN_SIZE` | Request size is static for this opportunity |
| `MAX_LEVERAGE` | Derived from static size/capital ratio |

### Transient (status stays `new`)

The rejection reason depends on conditions that can change over time.

| Reason code | Why it is transient |
|-------------|---------------------|
| `EXEC_DISABLED` | Global kill-switch; operator-controlled |
| `DUPLICATE` | Also: fires on already-previewed/executed; write-back would be a downgrade |
| `COOLDOWN` | Rate limit clears over time |
| `LIMIT_POSITIONS` | Position count changes as trades open/close |
| `LIMIT_DAILY` | Daily limit resets at midnight |
| `SPREAD_TOO_WIDE` | Market microstructure is volatile |
| `SLIPPAGE_TOO_HIGH` | Market microstructure is volatile |
| `DEPTH_TOO_THIN` | Market microstructure is volatile |
| `LIQUIDITY_TOO_LOW` | Market microstructure is volatile |
| `MARGIN_STRESS` | Account risk load changes as positions close |
| `EXPOSURE_TOO_HIGH` | Symbol exposure changes as positions close |

---

## Account Risk Load Model

### What it is NOT

`margin_utilization` (the internal variable name, kept for `RiskGuardian` interface compatibility) is **not** exchange margin utilization. Exchange margin accounts for leverage, initial margin requirements, and unrealized P&L. This system does not fetch or compute any of those.

### What it IS

A simplified **capital usage ratio**:

```
account_risk_load = total_open_notional_USD_across_all_venues / ACCOUNT_EQUITY_USD
```

Where:
- `total_open_notional_USD` = `sum(abs(pos["size_usd"]) for all positions from all venues)`
- `ACCOUNT_EQUITY_USD` = configured capital base (env var, default $50k)

### Canonical source

**`ACCOUNT_EQUITY_USD`** — module-level constant in `services/state-api/app/main.py`:
```python
ACCOUNT_EQUITY_USD = float(os.getenv("ACCOUNT_EQUITY_USD", "50000.0"))
```

Same env var is also read in `services/fusion-engine/app/worker.py` for scoring-time exposure calculation. The assumption is consistent across both services.

### How it's used in risk checks

| Variable | RiskGuardian parameter | Fires when |
|----------|----------------------|-----------|
| `margin_utilization` | `margin_utilization` | > `MARGIN_STRESS_THRESHOLD` (default 0.80) → `MARGIN_STRESS` |
| `symbol_exposure_usd` | `symbol_exposure_usd` | `symbol_exposure_usd + size_usd > MAX_EXPOSURE_PER_SYMBOL_USD` (default $25k) → `EXPOSURE_TOO_HIGH` |
| `ACCOUNT_EQUITY_USD` | `account_equity` | Used for: `implied_leverage = size_usd / account_equity`; fires if > `MAX_LEVERAGE` |

### Discoverability

`GET /state/risk/limits` returns `account_equity_usd` in the response body. Operators can query the running system to see the active assumption.

### Known limitations

1. Static assumption — does not update with real account balance changes from exchanges.
2. Only covers positions returned by exec services. If an exec service is unavailable, its positions are excluded from the calculation (partial aggregation).
3. No cross-asset netting. Two positions in opposite directions on the same symbol both add to total notional.

---

## Position Aggregation Contract

### Source

Positions are fetched from exec services via `_fetch_aggregated_positions(client)`:

```python
async def _fetch_aggregated_positions(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    tasks = [client.get(url, timeout=2.0) for url in _EXEC_POSITIONS_URLS.values()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ...
```

**`_EXEC_POSITIONS_URLS`** (module-level constant, `services/state-api/app/main.py`):
```python
_EXEC_POSITIONS_URLS = {
    "drift":       "http://exec-drift-svc:8003/exec/drift/positions",
    "hyperliquid": "http://exec-hl-svc:8004/exec/hl/positions",
}
```

### Position payload shape (identical for both venues)

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
  "timestamp": "2026-03-28T10:00:00"
}
```

**Key field:** `size_usd` — USD notional value of the position. (`notional` is NOT a field in the model.)

### Symbol exposure calculation

```python
symbol_exposure_usd = 0.0
for pos in all_positions:
    if pos.get("symbol") == symbol:
        symbol_exposure_usd += abs(pos.get("size_usd", 0))  # SUM across all venues
```

**Phase 3F-3 fix:** Previously used `=` (overwrite). Now uses `+=` (sum). With multiple positions in the same symbol across venues, the old code would only count the last position encountered.

---

## Config Source Reference

| Parameter | Source | Default | Used by |
|-----------|--------|---------|---------|
| `ACCOUNT_EQUITY_USD` | `os.getenv("ACCOUNT_EQUITY_USD", "50000.0")` | $50,000 | state-api preview, fusion-engine scoring |
| `MAX_EXPOSURE_PER_SYMBOL_USD` | `os.getenv("MAX_EXPOSURE_PER_SYMBOL_USD", "25000")` | $25,000 | RiskGuardian (`EXPOSURE_TOO_HIGH`) |
| `MARGIN_STRESS_THRESHOLD` | `os.getenv("MARGIN_STRESS_THRESHOLD", "0.8")` | 0.80 | RiskGuardian (`MARGIN_STRESS`) |
| `OPPORTUNITY_TTL_SECONDS` | `os.getenv("OPPORTUNITY_TTL_SECONDS", "300")` | 300s | expire_stale_opportunities |

All are readable from `GET /state/risk/limits`. None are writable via API — require env var update + restart.
