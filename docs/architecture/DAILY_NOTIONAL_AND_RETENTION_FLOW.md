# TradeSync: Daily Notional Enforcement and Retention Flow

**Last updated:** 2026-03-28

---

## Daily Notional Enforcement

### What It Measures

`daily_notional_usd` = sum of `request->>'size_usd'` across all `exec_orders` rows where `created_at >= CURRENT_DATE` (UTC calendar day boundary).

This counts the notional of orders *submitted* today, regardless of fill status. A placed, completed, or failed order all contribute equally. The check is conservative — it counts intent, not confirmed fill.

### Config

| Var | Default | Effect |
|-----|---------|--------|
| `DAILY_NOTIONAL_LIMIT` | 50000.0 | Hard cap in USD. Set to 0 to disable (no daily cap). |

Readable from `GET /state/risk/limits` as `daily_notional_limit`.
Current usage returned in `current_counters.daily_notional_usage`.

### Enforcement Point

Preview action only — `POST /actions/preview`.

At preview time, after the cooldown/position-count checks pass:
1. `daily_notional_usd` is fetched from `exec_orders` via DB query.
2. Passed to `RiskGuardian.check(daily_notional_usd=..., daily_notional_limit=...)`.
3. Check: if `limit > 0` and `used + size_usd > limit` → reject with `LIMIT_DAILY`.

Execute action (`POST /actions/execute`) does NOT re-check daily notional — only validates a pre-approved decision exists.

### Check Position in RiskGuardian.check()

```
EXEC_DISABLED → DNT → DUPLICATE → EXPIRY → STALE_DATA → MIN_QUALITY
→ microstructure (SPREAD, DEPTH, SLIPPAGE, LIQUIDITY) → MARGIN_STRESS
→ EXPOSURE_TOO_HIGH → LIMIT_POSITIONS → LIMIT_DAILY ← NEW
→ COOLDOWN → MIN_SIZE → MAX_LEVERAGE
```

`LIMIT_DAILY` is **transient** — the limit resets at UTC midnight. Not in `_NON_TRANSIENT_CODES`. Does NOT write `blocked` status; opportunity stays `new` and can be retried next day.

### DB Query

```sql
SELECT COALESCE(SUM((request->>'size_usd')::float), 0.0)
FROM exec_orders
WHERE created_at >= CURRENT_DATE
```

**Note:** `CURRENT_DATE` is evaluated by Postgres in the server's timezone, which defaults to UTC in the Docker image. Verify `SHOW timezone;` if day-boundary resets are wrong.

### Known Limitations

1. **Uses submitted size, not confirmed fill.** A $5k order that fills at $4.9k still counts $5k.
2. **No partial-day carry.** Filled orders removed from positions don't reduce the daily counter — it's a one-way accumulator until midnight.
3. **`request->>'size_usd'` relies on exec_orders.request JSON shape.** If the exec service writes a different key, the sum returns 0 (COALESCE). No error surfaces. Verify the exec order payload includes `size_usd` at the top level.

---

## Retention / Cleanup

### Why Cleanup Is Needed

`blocked` rows persist indefinitely (no TTL sweep — by design, they are not time-based rejections). `expired` rows also accumulate. On a busy system, these can grow to millions of rows over months.

### Cleanup Endpoint

```
POST /admin/cleanup?dry_run=true&days=30
```

**What it deletes:** Rows in `opportunities` where:
- `status IN ('blocked', 'expired')`
- `snapshot_ts < now() - N days`

**CASCADE:** `decisions` table has `opportunity_id REFERENCES opportunities(id) ON DELETE CASCADE`. Deleting an opportunity automatically deletes its associated decisions. `exec_orders` references `decisions(id) ON DELETE CASCADE` — so the full chain is cleaned.

**Safety:**
- Default `dry_run=true` returns count without deleting. Always use dry_run first.
- Never touches `executed`, `new`, or `previewed` rows.
- `days` param: 1–365, default 30.

### Suggested Maintenance Schedule

For systems running continuously:
- Weekly dry run to monitor accumulation: `POST /admin/cleanup?dry_run=true&days=30`
- Monthly actual cleanup: `POST /admin/cleanup?dry_run=false&days=30`

Or use a cron job / scheduled task in ops.

### What Is Not Cleaned

- `executed` opportunities — permanent record of real trades
- `signals`, `events` — not touched by cleanup endpoint
- `exposures`, `regimes`, `calibration_params` — separate tables, no cleanup endpoint

---

## Interaction Between Daily Notional and Blocked Status

`LIMIT_DAILY` is transient — it does NOT write `blocked`. The opportunity stays `new` and can be retried next UTC day.

`blocked` is only written for `_NON_TRANSIENT_CODES`:
```python
_NON_TRANSIENT_CODES = frozenset({"DNT", "MIN_QUALITY", "STALE_DATA", "EXPIRED", "MIN_SIZE", "MAX_LEVERAGE"})
```

`LIMIT_DAILY` is NOT in this set. Correct: the daily limit is time-dependent.

### TTL vs. Blocked

The TTL sweep (`expire_stale_opportunities`) runs every 60s and touches only `status IN ('new', 'previewed')`. It never touches `blocked`. So:
- An opportunity rejected with `LIMIT_DAILY` stays `new` → TTL sweep will eventually expire it if not retried.
- An opportunity rejected with `DNT` is written to `blocked` → TTL sweep never touches it → cleanup endpoint is the only removal path.
