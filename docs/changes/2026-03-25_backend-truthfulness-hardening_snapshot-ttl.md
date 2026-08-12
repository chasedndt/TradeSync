# Backend Truthfulness Hardening: Snapshot Resilience & Opportunity TTL

**Date:** 2026-03-25
**Phase:** Post-Cockpit Truthfulness Pass — Backend Hardening
**File:** `services/state-api/app/main.py`, `services/state-api/tests/test_main.py`

---

## Why This Phase Was Needed

The cockpit truthfulness pass (2026-03-25) fixed 13 UI/backend bugs — including wrong service URLs,
misleading empty-array defaults, and stale status labels. Those fixes made the cockpit read the backend
more faithfully. However, the backend itself had two remaining categories of dishonesty:

1. **`/state/snapshot` would 500 or silently swallow errors** when any optional upstream was down.
   The cockpit would receive either an opaque failure or a response that claimed things were fine when
   they weren't. There was no degraded-state model.

2. **Opportunity expiry was client-only.** The OPPORTUNITY_CONTRACT.md documented a 300-second TTL,
   but the backend never enforced it. The database would accumulate stale `new`/`previewed` rows
   indefinitely. The cockpit had to apply the TTL itself — meaning any client that didn't implement
   the filter would see ghost opportunities.

This phase makes the backend truthful about its own state and enforces lifecycle rules server-side.

---

## What Changed

### 1. `/state/snapshot` — Partial Response Model

**Before:** One large try/except block. Any failure (DB, Redis, or any HTTP call) raised
`HTTPException(500)`. Optional upstream failures silently passed but left error flags empty — no
explicit record that a service was unavailable.

**After:** Critical and optional sections are separated with independent error capture:

- **Critical section (postgres):** DB timestamp query runs first. If it fails, the response still
  returns 200 with `degraded=True` and an `errors.postgres` entry. Timestamps will be `null` but the
  response shape is stable.
- **Optional section (exec-drift-svc, exec-hl-svc, ingest-gateway):** Each HTTP call has its own
  error capture. Failures populate `errors.<service>` and `service_health.<service>.ok = false`.
  They never propagate to the outer handler.
- **Optional section (Redis):** Stream length queries are wrapped. Redis failure populates
  `service_health.redis` and `errors.redis` but does not crash the snapshot.
- A degraded-state warning is logged when any upstream is unavailable.

### 2. `SnapshotResponse` Model — New Fields

Added to the existing model (backward-compatible; existing fields preserved):

| Field | Type | Description |
|-------|------|-------------|
| `service_health` | `Dict[str, Any]` | Per-service `{ok, latency_ms, error}` map |
| `degraded` | `bool` | `true` if any upstream failed |
| `errors` | `Dict[str, str]` | Map of service name → error message |
| `snapshot_ts` | `Optional[datetime]` | UTC timestamp when this snapshot was captured |

Existing fields `drift_status` / `hl_status` are preserved as backward-compatible string values
(`"ok"` / `"error"`).

### 3. `OpportunityResponse` Model — `expires_at` Field

Added `expires_at: Optional[datetime] = None` to the opportunity response model.

- Populated from the `expires_at` column in the `opportunities` table (set by fusion-engine if an
  explicit TTL override is needed).
- `null` means the row's expiry is governed by the server-side TTL background task (see below).
- The `/state/evidence` endpoint also now returns `expires_at` and `confluence` in the embedded
  opportunity object.

### 4. Server-Side Opportunity TTL Expiry — `expire_stale_opportunities`

Added a background `asyncio` task that runs every **60 seconds** and executes:

```sql
UPDATE opportunities
SET status = 'expired'
WHERE status IN ('new', 'previewed')
  AND (
        (expires_at IS NOT NULL AND expires_at < now())
     OR (expires_at IS NULL AND snapshot_ts < now() - make_interval(secs => $1))
      )
```

Where `$1` = `OPPORTUNITY_TTL_SECONDS` (default: `300`, configurable via environment variable).

**Status transition rules (now server-authoritative):**

| From | To | Condition |
|------|----|-----------|
| `new` | `expired` | `snapshot_ts + TTL < now()` or `expires_at < now()` |
| `previewed` | `expired` | Same TTL rule — a previewed-but-not-executed opp can expire |
| `executed` | _(no change)_ | Executed orders are never expired by TTL |
| `expired` | _(no change)_ | Idempotent — already terminal |

The task is launched via `asyncio.create_task` in the FastAPI lifespan context and is cleanly
cancelled on shutdown.

### 5. Config

Added `OPPORTUNITY_TTL_SECONDS` environment variable (default `300`). Can be set in
`ops/compose.full.yml` under the `state-api` service environment block.

---

## Endpoints Changed

| Endpoint | Change |
|----------|--------|
| `GET /state/snapshot` | Returns partial response with `service_health`, `degraded`, `errors`, `snapshot_ts` |
| `GET /state/opportunities` | Includes `expires_at` in each opportunity row |
| `GET /state/evidence` | Includes `expires_at` and `confluence` in embedded opportunity |

---

## Opportunity Lifecycle (Authoritative Status Model)

```
[fusion-engine inserts] → status: new
       │
       ▼ (server-side TTL after 300s or at expires_at)
  status: expired   ← terminal, never re-activated
       │
       ▼ (if /actions/preview is called before TTL)
  status: previewed
       │
       ▼ (server-side TTL also applies here)
  status: expired   ← terminal
       │
       ▼ (if /actions/execute succeeds before TTL)
  status: executed  ← terminal, TTL does NOT apply
```

`blocked` is not a persisted status — it is reported at query time as a risk verdict.

---

## Degraded-State Response Model

When one or more upstreams are unavailable, `/state/snapshot` returns HTTP 200 with:

```json
{
  "latest_event_ts": "2026-03-25T10:00:00",
  "latest_signal_ts": null,
  "latest_opportunity_ts": null,
  "execution_gate": "false",
  "drift_status": "error",
  "hl_status": "error",
  "drift_circuit": null,
  "hl_circuit": null,
  "stream_lengths": {},
  "ingest_sources": [],
  "service_health": {
    "postgres": {"ok": true, "latency_ms": 3.1},
    "exec-drift-svc": {"ok": false, "error": "Connection refused"},
    "exec-hl-svc": {"ok": false, "error": "Connection refused"},
    "ingest-gateway": {"ok": false, "error": "Connection refused"},
    "redis": {"ok": true, "latency_ms": 0.8}
  },
  "degraded": true,
  "errors": {
    "exec-drift-svc": "Connection refused",
    "exec-hl-svc": "Connection refused",
    "ingest-gateway": "Connection refused"
  },
  "snapshot_ts": "2026-03-25T10:00:01.234Z"
}
```

The cockpit can use `degraded` and `service_health` to show accurate status banners instead of
inferring health from null fields.

---

## Tests Added

| Test | Covers |
|------|--------|
| `test_snapshot_returns_200_when_all_upstreams_down` | Snapshot returns 200 + degraded=True when all optional services fail |
| `test_snapshot_includes_per_service_health_map` | Response includes `service_health` dict with postgres entry |
| `test_snapshot_ingest_gateway_failure_does_not_crash` | Ingest-gateway failure leaves ingest_sources=[] with error metadata |
| `test_snapshot_includes_snapshot_ts` | `snapshot_ts` field is always present |
| `test_snapshot_not_degraded_when_all_ok` | `degraded=False` and `errors={}` when all services healthy |
| `test_expire_stale_opportunities_updates_db` | Background task calls correct UPDATE SQL |
| `test_get_opportunities_includes_expires_at` | Opportunity response includes `expires_at` field |
| `test_opportunities_endpoint_does_not_return_expired_by_default` | Default `status=new` filters exclude expired rows |
| `test_opportunities_endpoint_can_query_expired_status` | Clients can explicitly query `status=expired` |

---

## Verification Steps

1. **Start full stack:** `docker compose -f ops/compose.full.yml up -d`
2. **Verify snapshot with all services up:**
   ```bash
   curl http://localhost:8000/state/snapshot | jq .degraded
   # → false
   ```
3. **Stop ingest-gateway, verify partial snapshot:**
   ```bash
   docker compose -f ops/compose.full.yml stop ingest-gateway
   curl http://localhost:8000/state/snapshot | jq '{degraded, errors}'
   # → {"degraded": true, "errors": {"ingest-gateway": "..."}}
   ```
4. **Verify TTL expiry (accelerated test):**
   ```bash
   # Set short TTL
   OPPORTUNITY_TTL_SECONDS=10 docker compose ... up -d state-api
   # Insert a new opportunity, wait 70 seconds (one background task cycle)
   # Query status=expired
   curl "http://localhost:8000/state/opportunities?status=expired"
   ```
5. **Run tests:**
   ```bash
   cd services/state-api
   pytest tests/test_main.py -v
   ```

---

## Known Limitations

- The TTL background task runs every 60 seconds, so there is up to a 60-second window where a stale
  opportunity may still appear as `new` or `previewed`. This is acceptable — the task is a best-effort
  sweep, not a hard real-time gate.
- `make_interval(secs => $1)` requires PostgreSQL 9.4+. The project uses PostgreSQL 16 so this is safe.
- The `service_health` map does not include `market-data` at this time (it is used for position/preview
  calls but not directly polled in `/state/snapshot`). Market data health is available via
  `GET /state/market/status`.
- The `errors` dict truncates messages to 200 characters to prevent oversized responses.

---

## Next Recommended Step

**Phase 3E — Execution Authorization Hardening:**
With the backend now truthful about its own state and opportunity lifecycle enforced server-side,
the next logical step is hardening the execution path:
- Add authorization checks before `/actions/execute` (wallet-linked signer validation)
- Enforce idempotency at the DB level for exec_orders (prevent double-execution on network retry)
- Add circuit-breaker auto-reset logic in exec services
- Expose execution audit trail via `/state/evidence` with on-chain txid verification
