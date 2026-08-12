# TradeSync: Cockpit Lifecycle and Reason Data Path

**Last updated:** 2026-03-28

---

## Blocked Status Data Flow

### Write Path (state-api → DB)

When `preview_action()` receives a non-transient rejection from `RiskGuardian.check()`:

```
POST /actions/preview
  → opportunity.status == 'new'
  → verdict.reason_code in _NON_TRANSIENT_CODES
  → DB: UPDATE opportunities
         SET status = 'blocked',
             links = jsonb_set(links, '{rejection}', $json, true)
         WHERE id = $1 AND status = 'new'
        where $json = {"reason_code": "DNT", "reason": "..."}
```

The rejection data is stored in the existing `links` JSONB column under the key `rejection`. No schema migration required — `links` was already `jsonb NOT NULL DEFAULT '{}'`.

**Write guard:** `WHERE status = 'new'` prevents writing `blocked` over a higher-lifecycle status (`previewed`, `executed`). This is the secondary guard; the primary is that `DUPLICATE` is excluded from `_NON_TRANSIENT_CODES`.

### Read Path (DB → cockpit)

```
GET /state/opportunities?status=blocked
  → SELECT id, symbol, timeframe, bias, quality, dir, status,
           snapshot_ts, expires_at, links, confluence
    FROM opportunities
    WHERE status = 'blocked'
    ORDER BY snapshot_ts DESC
    LIMIT 100
```

`links` field is returned as-is (JSON object). The `rejection` key inside it contains the reason data.

### Cockpit Rendering

`Opportunities.tsx`:
- Filter chip `'blocked'` is now in `statusOptions` — clicking it fetches blocked opportunities.
- No client-side expiry filtering for `blocked` (only 'new' is filtered by TTL client-side).

`OpportunityCard.tsx`:
- Reads `opportunity.links.rejection`.
- If present: renders red banner with `reason_code` (monospaced) and `reason` (truncated).

`StatusBadge.tsx`:
- `blocked` → `bg-red-950 text-red-300 border border-red-800` (dark red, distinguished from `expired` gray).

---

## Opportunity Status Filter Chips (Complete)

| Status | Button visible | What it shows | TTL client-side filter |
|--------|---------------|---------------|----------------------|
| `new` | ✓ | Unreviewed, awaiting preview | Yes — hides items > 15 min old |
| `previewed` | ✓ | Risk approved, awaiting execution | No |
| `executed` | ✓ | Order sent to venue | No |
| `expired` | ✓ | Aged out by TTL sweep | No |
| `blocked` | ✓ (Phase 2 addition) | Permanently rejected | No |

---

## Reason Code Display

The cockpit only shows `reason_code` (short) and `reason` (human text) for `blocked` opportunities. Other rejection codes (transient: COOLDOWN, MARGIN_STRESS, etc.) are returned in `risk_verdict` from the `/actions/preview` response but are NOT stored on the opportunity row — they are shown only in the PreviewPanel at preview time.

### Why Only Blocked Gets Stored

Transient rejections are expected to change. Storing MARGIN_STRESS at preview time on the opportunity row would be misleading — the margin stress may have cleared by the time the operator views it. Only non-transient rejections (permanently ineligible) are worth persisting on the row itself.

---

## links.rejection Schema

```json
{
  "rejection": {
    "reason_code": "DNT",
    "reason": "Symbol LUNA-PERP is on the Do Not Trade (DNT) list"
  }
}
```

`reason_code` values for blocked (non-transient codes):

| Code | Human reason |
|------|-------------|
| `DNT` | Symbol is on the Do Not Trade list |
| `MIN_QUALITY` | Quality below minimum threshold |
| `STALE_DATA` | Signal too old, will not get fresher |
| `EXPIRED` | Past TTL window |
| `MIN_SIZE` | Request size below minimum |
| `MAX_LEVERAGE` | Implied leverage exceeds maximum |

---

## Known Limitations

1. **`links.rejection` is not a typed column** — stored in `links` JSONB as a nested key. A future migration adding `rejection_reason jsonb` column to `opportunities` would be cleaner.

2. **No reason shown for non-blocked rejections in the opportunity list** — transient rejections (COOLDOWN, MARGIN_STRESS, etc.) are only visible during the preview flow itself, not in the opportunities list.

3. **Old blocked rows (before Phase 2)** — rows written to `blocked` before this phase have `links.rejection = null`. The cockpit renders no banner for these (graceful: `rejection &&` guard in OpportunityCard). They still show with the blocked status badge.
