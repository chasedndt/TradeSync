# TradeSync — Canonical Roadmap

**Last Updated:** 2026-03-29
**Status:** ACTIVE — this supersedes `roadmap.md` (root)

---

## How to read this document

- **DONE** = merged and running in the real repo
- **PARTIAL** = code exists but has gaps, known bugs, or incomplete wiring
- **NOT STARTED** = agreed future work, no code yet
- **DEFERRED** = explicitly pushed to a later phase; do not build now

Each phase has a **Gate** — what must be true before moving to the next phase.

---

## Phase 2.5 — Reliability / Observability / Execution Realism
**Theme:** Make the already-built pipeline honest and reliable before adding more features.
**Status:** DONE (largely complete as of 2026-03-25 patch set)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 2.5-1 | Connection pool (asyncpg) in state-api | DONE | min/max configurable via env |
| 2.5-2 | Background TTL expiry for opportunities | DONE | Runs every 60s, respects `expires_at` |
| 2.5-3 | Trace-ID middleware in state-api | DONE | X-Trace-Id header propagated |
| 2.5-4 | Prometheus `/metrics` endpoint | DONE | HTTP latency + DB table counts |
| 2.5-5 | Circuit breakers on exec venues | DONE | 5 failures → 600s disable, Redis-backed |
| 2.5-6 | Exec idempotency keys | DONE | 24h cache, no double-sends |
| 2.5-7 | Snapshot endpoint partial-failure handling | DONE | Never fails on optional upstream being down |
| 2.5-8 | DRY_RUN / demo mode propagation | DONE | DryRunBanner in UI |
| 2.5-9 | Snapshot TTL enforcement via `expires_at` | DONE | fusion-engine sets explicit expires_at |

**Gate:** System observable, no silent failures, execution paths honest about mode.

---

## Phase 3A — Cockpit Stabilization and Truthfulness
**Theme:** Make the cockpit accurately reflect what the backend actually knows.
**Status:** DONE (2026-01-21 + 2026-03-25 patch sets)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 3A-1 | All cockpit routes wired to real endpoints | DONE | |
| 3A-2 | Opportunity list reads from DB | DONE | Status filter, symbol filter |
| 3A-3 | Evidence trail (signals → events chain) | DONE | `/state/evidence` endpoint |
| 3A-4 | Preview/execute flow end-to-end | DONE | RiskGuardian wired, decisions persisted |
| 3A-5 | Positions page wired to exec services | PARTIAL | Exec services return positions but real on-chain query not verified |
| 3A-6 | MetricStatus badges on Market page | DONE | REAL/PROXY/UNAVAILABLE/STALE |
| 3A-7 | Copilot page labeled Phase 4 placeholder | DONE | Honest "not implemented" message |
| 3A-8 | Sources Library labeled Phase 4 placeholder | DONE | Honest "not implemented" message |
| 3A-9 | service_health map in snapshot response | DONE | Per-service ok/latency/error |
| 3A-10 | `degraded` flag in snapshot | DONE | |
| 3A-11 | Snapshot test reconciliation | DONE | Tests match real field names |
| 3A-12 | Market normalization audit | DONE | OI USD conversion, staleness flags |

**Gate:** No cockpit page shows fabricated or misleading data without explicit PROXY/UNAVAILABLE label.

---

## Phase 3B — Market Data Expansion / Normalization
**Theme:** Reliable, multi-horizon, multi-venue market data in a canonical format.
**Status:** DONE (2026-01-21)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 3B-1 | market-data service (separate microservice) | DONE | Port 8005 |
| 3B-2 | Hyperliquid provider (funding, OI, volume, orderbook) | DONE | |
| 3B-3 | Drift provider (funding, OI, volume) | DONE | Orderbook not yet on Drift side |
| 3B-4 | MarketNormalizer: canonical event schema | DONE | REAL/PROXY/STALE status per metric |
| 3B-5 | MarketSnapshotter: rolling windows + regimes | DONE | 5m/15m/1h/4h/24h/7d windows |
| 3B-6 | Funding regime classification | DONE | Annualized rate thresholds |
| 3B-7 | OI regime classification | DONE | delta_24h + delta_4h thresholds |
| 3B-8 | Volume regime classification | DONE | vs 7d average |
| 3B-9 | MarketCondition composite label | DONE | squeeze_risk/capitulation/trending_healthy/choppy |
| 3B-10 | Regime-change alerts (x:alerts stream) | DONE | |
| 3B-11 | Rate limiter per provider | DONE | Configurable per-provider |
| 3B-12 | Proxy liquidation estimate from OI delta | DONE | Clearly labeled PROXY |
| 3B-13 | Drift orderbook polling | NOT STARTED | Drift L2 book endpoint needed |
| 3B-14 | Multi-venue aggregate endpoint in state-api | DONE | `/state/market/aggregate/{symbol}` |
| 3B-15 | Timeseries endpoint | DONE | `/state/market/timeseries/{venue}/{symbol}/{metric}` |

**Gate:** Market page shows real, labeled, comparable data for both venues.

**Known gaps:**
- Drift orderbook is missing (no L2 book poller implemented for Drift)
- Volume horizon estimates (5m/1h/4h) are derived from 24h average, not real per-period data

---

## Phase 3C — Scoring Upgrade / Quality
**Theme:** Enhance scoring to account for microstructure, exposure, and regime context.
**Status:** DONE (2026-02-11)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 3C-1 | EnhancedScorer in tradesync_core library | DONE | |
| 3C-2 | Microstructure deriver from orderbook | DONE | depth_usd, impact_est_bps, liquidity_score |
| 3C-3 | Microstructure penalty in scoring | DONE | spread, depth, impact weighted penalty |
| 3C-4 | Exposure penalty in scoring | DONE | symbol concentration + margin stress |
| 3C-5 | Regime bonus in scoring | DONE | squeeze potential, market condition alignment |
| 3C-6 | EnhancedScore attached to opportunity.confluence | DONE | Full breakdown stored |
| 3C-7 | Microstructure-based RiskGuardian vetoes | DONE | SPREAD_TOO_WIDE, DEPTH_TOO_THIN, etc |
| 3C-8 | Exposure-based RiskGuardian vetoes | DONE | MARGIN_STRESS, EXPOSURE_TOO_HIGH |
| 3C-9 | ScoreBreakdown visible in Evidence Trail / cockpit | PARTIAL | confluence field stored but UI display incomplete |
| 3C-10 | Exposure data wired to EnhancedScorer | PARTIAL | TODO comment in worker.py — exposure_data=None |

**Gate:** Scoring incorporates real execution cost and portfolio context, not just raw signal.

**Known gaps:**
- `exposure_data=None` in fusion-engine worker — exposure penalty always 0 (never fetches from state-api)
- Score breakdown in confluence field is stored but cockpit OpportunityDetail does not render it as structured UI

---

## Phase 3D — Replay + Backtesting
**Theme:** Enable historical scenario replay for scoring validation.
**Status:** DONE (2026-02-13, service scaffolded)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 3D-1 | backtest-runner service scaffold | DONE | main.py, replay.py, evaluator.py |
| 3D-2 | Replay data samples | DONE | data/replay/ directory |
| 3D-3 | Evaluator logic | PARTIAL | Structure exists, full metric evaluation not verified |
| 3D-4 | Backtest wired to cockpit | NOT STARTED | No cockpit page or API endpoint for backtest results |
| 3D-5 | Calibration params table | DONE (schema) | Table exists, nothing writes to it yet |

**Gate:** Can replay historical signals through the scoring pipeline and measure outcome quality.

---

## Phase 3E — Wallet / Signing Authority
**Status:** DEFERRED — NOT NOW

| # | Item | Status |
|---|------|--------|
| 3E-1 | Server-side key custody | DEFERRED |
| 3E-2 | Drift real order signing | DEFERRED |
| 3E-3 | Hyperliquid real order signing | DEFERRED |
| 3E-4 | Autonomous mode unlock | DEFERRED |

**Why deferred:** Autonomous mode requires wallet authority. The system is not ready for that. Manual mode is the correct current target. The Autonomy page in the cockpit explicitly shows this as locked.

---

## Phase 3F — Lifecycle Management
**Status:** PARTIAL (most items done in 2026-03-25/2026-03-29 passes)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 3F-1 | Opportunity status machine hardening | DONE | `blocked` status implemented; rejection stored in `links` |
| 3F-2 | Stale signal detection + expiry loop | DONE | Background loop runs every 60s, `expires_at` enforced |
| 3F-3 | Position reconciliation (exec vs DB) | NOT STARTED | Exposures table vs real on-chain positions unverified |
| 3F-4 | Order fill confirmation loop | NOT STARTED | `placed` status = assumed done; no fill poll loop |
| 3F-5 | Daily notional limit enforcement | PARTIAL | Limit check exists in RiskGuardian; counter not incremented post-fill |

**Known gaps:**
- `exposure_data=None` in fusion-engine worker — exposure penalty in scoring is always 0
- Daily notional counter: limit correctly vetoes when set, but nothing increments it after fills

---

## Phase 3G — Explainability / Score Transparency
**Status:** PARTIAL

| # | Item | Status | Notes |
|---|------|--------|-------|
| 3G-1 | `score_breakdown` stored in confluence JSONB | DONE | alpha, penalties, regime_bonus, final_score, notes all stored |
| 3G-2 | `execution_risk` rendered in OpportunityDetail | DONE | Spread, depth, slippage, flags shown in ExecutionRiskBox |
| 3G-3 | `warnings` array rendered in OpportunityDetail | DONE | Human-readable warnings shown |
| 3G-4 | ScoreBreakdown waterfall UI in OpportunityDetail | NOT STARTED | `score_breakdown` stored but never rendered |
| 3G-5 | Explainability notes displayed | NOT STARTED | `score_breakdown.notes` array never shown to user |
| 3G-6 | Regime contribution linked to score_breakdown | NOT STARTED | Regime shown separately; regime_bonus never cross-referenced |
| 3G-7 | Wire `exposure_data` in fusion-engine worker | NOT STARTED | `exposure_data=None` → exposure_penalty always 0 |

---

## Phase 4A — Market Intelligence Layers
**Theme:** Add structural market analysis beyond raw funding/OI/volume.
**Status:** NOT STARTED — do not build until Phase 3F/3G gates are cleared

| # | Item | Status | Notes |
|---|------|--------|-------|
| 4A-1 | BOS/CHOCH detection (Break of Structure / Change of Character) | NOT STARTED | Requires per-bar OHLCV data ingestion |
| 4A-2 | Fair Value Gap (FVG) detection | NOT STARTED | 3-candle imbalance pattern on OHLCV |
| 4A-3 | Liquidity sweep / stop hunt detection | NOT STARTED | Equal highs/lows + wick extension pattern |
| 4A-4 | Order block identification | NOT STARTED | Last opposing candle before impulsive move |
| 4A-5 | CVD (Cumulative Volume Delta) ingestion | NOT STARTED | Requires per-trade bid/ask aggression data |
| 4A-6 | Volume delta scoring | NOT STARTED | CVD divergence from price as signal feature |
| 4A-7 | Liquidation map proxy (from OI delta + funding) | PARTIAL | Exists as PROXY label in market-data; no structured scoring |
| 4A-8 | Orderflow imbalance signal | NOT STARTED | Bid vs ask volume ratio per interval |
| 4A-9 | OHLCV ingest pipeline | NOT STARTED | Required prereq for all SMC/ICT features |
| 4A-10 | SMC/ICT framework integration (composite signal) | NOT STARTED | Dependent on 4A-1 through 4A-5 |

**Gate:** OHLCV ingest pipeline (4A-9) must exist before any structural pattern work begins.

---

## Phase 4B — Intelligence Ingestion (RAG / Copilot)
**Status:** NOT STARTED

| # | Item | Status | Notes |
|---|------|--------|-------|
| 4B-1 | Sources Library backend | NOT STARTED | Document upload, chunking, Qdrant embeddings |
| 4B-2 | Qdrant RAG pipeline | NOT STARTED | Copilot backend |
| 4B-3 | AI Copilot endpoint | NOT STARTED | LLM + retrieval |
| 4B-4 | Macro headline feed (real data) | NOT STARTED | `/state/macro/headlines` returns stub |
| 4B-5 | Sentiment scoring from headlines | NOT STARTED | |

---

## Phase 4C — Position Intelligence
**Status:** NOT STARTED

| # | Item | Status | Notes |
|---|------|--------|-------|
| 4C-1 | Real on-chain position reconciliation | NOT STARTED | Query exec services for live positions, compare to DB |
| 4C-2 | Fill confirmation loop | NOT STARTED | Poll order status after `placed`; update to `completed` or `failed` |
| 4C-3 | Daily notional counter post-fill | NOT STARTED | Increment counter on confirmed fills |
| 4C-4 | Backtest result surfacing in cockpit | NOT STARTED | No cockpit page or API endpoint for backtest results |
| 4C-5 | Calibration params written by backtest-runner | NOT STARTED | Table exists; nothing writes to it |
| 4C-6 | Calibration feedback loop | NOT STARTED | Auto-tune scoring params from backtest outcomes |

---

## Phase 5 — Multi-Agent / Learning Loops
**Status:** NOT STARTED

| # | Item | Status |
|---|------|--------|
| 5-1 | Scoring parameter auto-tuning | NOT STARTED |
| 5-2 | Multi-agent coordination | NOT STARTED |
| 5-3 | Voice interface | NOT STARTED |

---

## Current Development Lane (2026-03-29)

**Phase 3F is largely done. Phase 3G (explainability) is the correct next focus.**

The correct next build steps, in priority order:

1. **ScoreBreakdown waterfall UI** (3G-4) — `score_breakdown` data exists in DB, just needs a component in `OpportunityDetail.tsx`
2. **Wire `exposure_data`** (3G-7) — fusion-engine worker currently passes `exposure_data=None`; wire to `/state/positions`
3. **Fill confirmation loop** (4C-2) — `placed` status is a lie; nothing confirms fills
4. **Daily notional counter** (4C-3) — limit check works; counter never increments
5. **OHLCV ingest pipeline** (4A-9) — prereq gate for any future structural analysis

---

## What is NOT the next step

- Phase 3E (wallet/signing) — DEFERRED
- SMC/ICT implementation — requires OHLCV pipeline first (4A-9 gate)
- CVD/orderflow — requires per-trade data feed not yet ingested
- Phase 4B (Copilot/RAG) — not until core scoring/lifecycle is solid
