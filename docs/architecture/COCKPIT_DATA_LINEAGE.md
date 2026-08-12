# TradeSync — Cockpit Page Data Lineage Map

**Last Updated:** 2026-03-27
**Purpose:** For every cockpit page, trace exactly where the data comes from.

---

## Legend

- **REAL** — data comes from live backend, real DB queries, real external APIs
- **DERIVED** — computed from real data (regime labels, scores, aggregates)
- **PARTIAL** — real data exists but some fields are missing or not fully wired
- **PROXY** — estimated/approximated data, labeled as such
- **PLACEHOLDER** — no backend; UI renders static or disabled state
- **LOCAL** — stored in browser localStorage, no backend

---

## 1. Overview Page

**Route:** `/`
**Component:** `Overview.tsx`

| Layer | Detail |
|-------|--------|
| Hooks | `useSnapshot`, `useOpportunities`, `useRiskLimits` |
| API calls | `GET /state/snapshot`, `GET /state/opportunities`, `GET /state/risk-limits` |
| Backend handler | `get_state_snapshot()`, `get_opportunities()`, `get_risk_limits()` |
| Upstream services | postgres, redis, exec-drift-svc (circuit), exec-hl-svc (circuit), ingest-gateway (source mirror) |
| DB tables | events (latest ts), signals (latest ts), opportunities (latest ts, count by status) |
| Data status | **REAL** for timestamps and counts; **PARTIAL** for exec-service circuit data (if services down, degraded flag set) |
| Truthfulness | Snapshot never throws on optional upstream failure — returns partial data with `service_health` map |
| Known gaps | If exec services unreachable, drift_status/hl_status show "error" — this is correct behavior, not a bug |
| Future | Add per-symbol opportunity summary, recent PnL from exec_orders |

---

## 2. Opportunities Page

**Route:** `/opportunities`
**Component:** `Opportunities.tsx`

| Layer | Detail |
|-------|--------|
| Hooks | `useOpportunities` |
| API calls | `GET /state/opportunities?symbol=X&status=new` |
| Backend handler | `get_opportunities()` in state-api |
| DB tables | `opportunities` — SELECT with optional symbol/status filter |
| Data status | **REAL** |
| Fields shown | symbol, dir, bias (enhanced score), quality, status, snapshot_ts, expires_at, confluence summary |
| Truthfulness | Bias field is the enhanced final score (raw + microstructure penalty + exposure penalty + regime bonus) |
| Known bugs | confluence field is stored in DB as JSON but UI may not render score breakdown panel; check `confluence` display in OpportunityCard |
| Known gaps | `confluence.score_breakdown` contains the full scoring explanation but is not rendered as structured UI |
| Future | Add filter by direction, by score range; render score breakdown inline |

---

## 3. Opportunity Detail Page

**Route:** `/opportunities/:id`
**Component:** `OpportunityDetail.tsx`

| Layer | Detail |
|-------|--------|
| Hooks | `useEvidence`, `usePreview`, `useExecute` |
| API calls | `GET /state/evidence?opp_id=X`, `POST /actions/preview`, `POST /actions/execute` |
| Backend handlers | `get_evidence()`, `preview_action()`, `execute_action()` |
| DB tables | `opportunities` (opp record), `signals` (linked via signal_id), `events` (linked via event_ids), `decisions` (if previewed), `exec_orders` (if executed) |
| Data status | **REAL** — full chain from event to execution |
| Evidence trail | events → signal → opportunity → decision → exec_order |
| Preview flow | RiskGuardian.check() → INSERT decision → return PreviewResponse with risk_verdict |
| Execute flow | Fetch decision → route to exec-drift-svc or exec-hl-svc → INSERT exec_order → return result |
| Truthfulness | risk_verdict is honest: includes reason_code, reason, suggested_adjustment |
| Known gaps | score_breakdown inside opportunity.confluence not rendered as structured panel in OpportunityDetail |
| Future | Render EnhancedScore breakdown visually (alpha, microstructure_penalty, exposure_penalty, regime_bonus) |

---

## 4. Market Page

**Route:** `/market`
**Component:** `Market.tsx`

| Layer | Detail |
|-------|--------|
| Hooks | `useMarketSnapshots`, `useMarketStatus` |
| API calls | `GET /state/market/snapshot?venue=X&symbol=Y`, `GET /state/market/aggregate/{symbol}` |
| Backend handlers | `get_market_snapshot()`, `get_market_aggregate()` in state-api |
| Upstream | market-data:8005 `/snapshot/{venue}/{symbol}` |
| Data status | **REAL** for funding, OI, volume; **REAL (derived)** for microstructure; **PROXY** for liquidations |
| Metric status badges | Every metric has REAL/PROXY/UNAVAILABLE/STALE badge — fetched from `available_metrics` array |

**Panels and their data sources:**

| Panel | Data | Status | Notes |
|-------|------|--------|-------|
| Funding | `snapshot.funding` — current rate + 8h/24h/3d/7d averages + regime | **REAL** | Source: Hyperliquid/Drift APIs |
| Open Interest | `snapshot.oi` — current_usd + delta per horizon + regime | **REAL** | OI for Drift is converted from asset units using mark price |
| Volume | `snapshot.volume` — 24h value + regime | **REAL** (24h); **DERIVED** (5m/1h/4h estimates from 24h/n) | 5m/1h/4h are not real granular data — they are 24h divided by periods |
| Orderbook | `snapshot.orderbook` — spread, depth, imbalance, bid/ask | **REAL** | Hyperliquid only; Drift orderbook not implemented |
| Microstructure | `snapshot.microstructure` — depth_usd, impact_est_bps, liquidity_score, heatmap | **REAL (derived)** | Derived from orderbook; Hyperliquid only |
| Liquidations | `snapshot.liquidations` | **PROXY** | Estimated from OI delta (OI drop ≈ liqs). Labeled as PROXY. Not real liquidation feed. |
| Regime Summary | `snapshot.regimes` — funding/oi/volume/trend + market_condition | **DERIVED** | All regime labels come from explicit thresholds in snapshotter.py |

**Regime label definitions (not heuristic labels — actual code thresholds):**

| Regime | Threshold |
|--------|-----------|
| `extreme_positive` funding | annualized_24h > 50% |
| `elevated_positive` funding | annualized_24h > 20% |
| `neutral` funding | -20% to +20% |
| `elevated_negative` funding | annualized_24h < -20% |
| `extreme_negative` funding | annualized_24h < -50% |
| OI `build` | delta_24h > +3% AND delta_4h > 0 |
| OI `unwind` | delta_24h < -3% AND delta_4h < 0 |
| OI `flat` | everything else |
| Volume `high` | vol_24h > 2x 7d average |
| Volume `low` | vol_24h < 0.5x 7d average |
| Volume `normal` | between |

**Known issues:**
- Drift orderbook not available → microstructure data is Hyperliquid-only
- Volume sub-24h intervals (5m, 1h, 4h) are derived estimates, not granular data — should be labeled DERIVED
- Aggregate endpoint (`/state/market/aggregate/{symbol}`) fetches both venues and merges but does NOT mathematically blend funding rates — it returns both venue snapshots separately
- OI USD conversion for Drift: `oi_value * mark_price` — depends on mark_price being accurate

**Future (Phase 3B gap work):**
- Add Drift orderbook polling
- Label volume sub-24h estimates as PROXY/DERIVED in available_metrics
- Add cross-venue OI comparison normalization notes in UI

---

## 5. Execution Page

**Route:** `/execution`
**Component:** `Execution.tsx`

| Layer | Detail |
|-------|--------|
| Hooks | `usePreview`, `useExecute`, `useExecutionStatus` |
| API calls | `POST /actions/preview`, `POST /actions/execute`, `GET /state/execution/status` |
| Backend handlers | `preview_action()`, `execute_action()`, `get_execution_status()` |
| Data status | **REAL** for preview/execute flow; circuit status from exec services |
| DRY_RUN flag | Set at env level; state-api propagates to exec services; result.dry_run=true in response |
| Risk verdict | Returned by RiskGuardian — includes reason_code and suggested_adjustment |
| Circuit breaker | Checked before routing; 5 failures → 600s disable |
| Idempotency | `exec:idempo:{venue}:{key}` prevents double-sends on retry |
| Truthfulness | If DRY_RUN=true, execution result is simulated — labeled clearly in response |
| Known gaps | Autonomous mode execution not implemented (mode=autonomous returns same manual path) |
| Future | Wire mode switching; autonomous execution gate |

---

## 6. Positions Page

**Route:** `/positions`
**Component:** `Positions.tsx`

| Layer | Detail |
|-------|--------|
| Hooks | `usePositions` |
| API calls | `GET /state/positions` |
| Backend handler | `get_positions()` — calls exec-drift-svc:8003/exec/drift/positions and exec-hl-svc:8004/exec/hl/positions |
| Data status | **PARTIAL** |
| Truthfulness gap | exec services return positions from `DRY_RUN` mock data when DRY_RUN=true; in dry-run mode these are not real positions |
| Second source | `exposures` table is also available but may not be in sync with real on-chain state |
| Known gaps | No reconciliation between exposures table and what exec services return; no fill confirmation loop means `placed` orders are not confirmed as real positions |
| Future | Phase 3F: position reconciliation; fill confirmation loop |

---

## 7. Sources Library Page

**Route:** `/sources`
**Component:** `Sources.tsx`

| Layer | Detail |
|-------|--------|
| Hooks | None |
| API calls | None |
| Backend | None |
| Data status | **PLACEHOLDER** |
| Truthfulness | UI explicitly says "COMING IN PHASE 4" with disabled inputs |
| What it will become | Document upload, chunking, Qdrant vector embeddings, semantic search — Phase 4 |

---

## 8. Copilot Page

**Route:** `/copilot`
**Component:** `Copilot.tsx`

| Layer | Detail |
|-------|--------|
| Hooks | None |
| API calls | None |
| Backend | None |
| Data status | **PLACEHOLDER** |
| Truthfulness | UI explicitly says "COMING IN PHASE 4", input is disabled, message says "Copilot backend has not been implemented" |
| What it will become | LLM + Qdrant RAG + Sources Library integration — Phase 4 |

---

## 9. Autonomy Page

**Route:** `/autonomy`
**Component:** `Autonomy.tsx`

| Layer | Detail |
|-------|--------|
| Hooks | `useExecutionStatus` (from ExecutionContext) |
| API calls | `GET /state/execution/status` |
| Backend handler | `get_execution_status()` — checks exec service circuit breakers |
| Data status | **REAL** for readiness checklist items; **LOCKED** for autonomous mode gate |
| Mode context | `useExecution()` from ExecutionContext — reads mode (observe/manual/autonomous) |
| Truthfulness | Autonomous mode explicitly locked in UI; Phase 3E prerequisite shown as unmet |
| Known gaps | Mode switching itself lives on Execution page; autonomous mode execution path doesn't exist yet |
| What it shows | Governance page only — what authority the system has, what prerequisites are unmet. Not a control page. |

---

## 10. Decisions & Orders

**Not a dedicated page.** This data surfaces in:
- `OpportunityDetail` via the Evidence Trail (`/state/evidence`)
- The SQL audit query in `CLAUDE.md`

**Data location:**
- `decisions` table — one per preview, contains risk/leverage/stops/TPs
- `exec_orders` table — one per execution, contains full request/response payloads

---

## 11. Risk Policies Page

**Route:** `/risk-policies`
**Component:** `RiskPolicies.tsx`

| Layer | Detail |
|-------|--------|
| Hooks | `useRiskLimits` |
| API calls | `GET /state/risk-limits` |
| Backend handler | `get_risk_limits()` — reads from RiskGuardian instance (env-var backed) |
| Data status | **REAL** |
| Limits displayed | max_leverage, min_quality, max_open_positions, min_size_usd, max_event_age, max_signal_age, blacklist, daily_notional_limit |
| Truthfulness gap | `current_counters` (daily notional spent, open position count) are returned but may not be live — the daily_notional_limit counter is never incremented in code |
| Edit capability | Read-only in UI; limits are env-var backed, not user-editable at runtime |
| Future | Phase 3F: editable policies, persistent user-set limits, daily notional counter |

---

## 12. Settings Page

**Route:** `/settings`
**Component:** `Settings.tsx`

| Layer | Detail |
|-------|--------|
| Hooks | None (localStorage) |
| API calls | None |
| Data status | **LOCAL** |
| What it stores | API base URL, auth token (if any), theme preferences |
| Truthfulness | No backend sync — settings are browser-local only |

---

## Summary Table

| Page | Backend? | Real Data? | Placeholder? | Main Gap |
|------|----------|-----------|-------------|----------|
| Overview | Yes | Yes | No | Exec circuit status degrades gracefully |
| Opportunities | Yes | Yes | No | confluence breakdown not rendered |
| OpportunityDetail | Yes | Yes | No | score breakdown panel missing |
| Market | Yes | Yes (REAL+PROXY labeled) | No | Volume sub-24h = derived; Drift book missing |
| Execution | Yes | Yes | No | Autonomous mode gate not implemented |
| Positions | Yes | Partial | No | Dry-run mode returns mocks; no reconciliation |
| Sources | No | No | Yes (Phase 4) | Entire backend missing |
| Copilot | No | No | Yes (Phase 4) | Entire backend missing |
| Autonomy | Yes | Yes (readiness only) | No | Mode switching not fully wired |
| Risk Policies | Yes | Yes | No | daily_notional counter not incremented |
| Settings | No (local) | N/A | No | No backend persistence |
