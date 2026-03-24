# Step 0: Contract Freeze Verification Runbook

This runbook documents the verification steps performed to confirm the successful completion of **Step 0: API Contract Standardization & Service Renaming**.

## 1. Service Renaming: `fusion-engine`
The `opportunity-builder` service has been renamed to `fusion-engine`.

### 1.1 Docker Compose Health
**Command:**
```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```
**Expected Output:**
`tradesync-full-fusion-engine-1` is `Up` and `healthy`.

### 1.2 Internal Discovery (Alias)
**Command:**
```bash
docker compose -f ops/compose.full.yml exec state-api curl -s http://opportunity-builder:8002/healthz
```
**Actual Output:**
`{"ok":true}`

---

## 2. API Contract: Canonical Routes
Standardized endpoints under `/state/*` and `/actions/*`.

### 2.1 Aggregated Health
**Command:**
```bash
curl -s http://localhost:8000/state/health
```
**Actual Output Snippet:**
```json
{"status":"healthy","postgres":true,"last_event_ts":"2026-01-16T...","latency_ms":...}
```

### 2.2 System Snapshot
**Command:**
```bash
curl -s http://localhost:8000/state/snapshot
```
**Expected:** Returns stream lengths and circuit breaker statuses.

---

## 3. Legacy Alias Compatibility
Confirming that deprecated routes still function and return proper headers.

### 3.1 `/opps` Alias
**Command:**
```bash
curl -I http://localhost:8000/opps
```
**Actual Output:**
```
HTTP/1.1 200 OK
deprecation: true
link: </state/opportunities>; rel="successor-version"
...
```

---

## 4. Normalization Logic
Ensuring symbols and venues are normalized system-wide.

### 4.1 Symbol: `BTCUSDT` -> `BTC-PERP`
**Command:**
```bash
curl "http://localhost:8000/state/opportunities?symbol=BTCUSDT"
```
**Expected:** The `symbol` in the JSON response is `BTC-PERP`.

---

## 5. Summary of Completion
- [x] Rename `opportunity-builder` -> `fusion-engine`.
- [x] Standardize `state-api` routes.
- [x] Implement legacy aliases with headers.
- [x] Symbol & Venue normalization utilities.
- [x] Sync all technical documentation.
