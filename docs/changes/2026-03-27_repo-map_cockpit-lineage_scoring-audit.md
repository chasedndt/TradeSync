# Handover: Repo Map, Cockpit Lineage, Scoring Audit

**Date:** 2026-03-27
**Session type:** Architecture audit + documentation sprint
**Triggered by:** System was "partially understood cockpit" — mission to fully map the real system

---

## What Was Done

### Documents Created

| File | Purpose |
|------|---------|
| `docs/roadmap/CANONICAL_ROADMAP.md` | Single source of truth roadmap — replaces root `roadmap.md` |
| `docs/architecture/REPO_SYSTEM_MAP.md` | Full repo tree, service map, port map, DB schema, Redis key map |
| `docs/architecture/COCKPIT_DATA_LINEAGE.md` | Page-by-page: route/hook/API/backend/upstream/data status/gaps |
| `docs/architecture/OPPORTUNITY_PIPELINE_AUDIT.md` | End-to-end pipeline trace + status machine + known bugs |
| `docs/architecture/SCORING_AND_DECISION_AUDIT.md` | Feature usage matrix + brutal gap analysis vs intended model |

### roadmap.md (root) updated

Root `roadmap.md` now clearly states it is superseded and points to the canonical roadmap.

### Low-Risk Fixes Made

None. The audit found no safe single-line fixes that would be worth applying without alignment — all gaps are either:
- Bugs requiring test validation before fixing (e.g., exposure_data=None)
- Architecture gaps requiring design discussion (e.g., blocked status, fill confirmation)
- Future features properly labeled already in the UI

The system is more honest than expected. No misleading labels found that needed immediate removal.

---

## Key Findings Summary

### Phase Assessment
We are at the end of Phase 3D (backtest runner scaffolded). Phase 3E is correctly deferred. The correct next lane is Phase 3F lifecycle hardening.

### Scoring Is Real But Simple
The actual scoring logic is a funding/OI squeeze model with TradingView signal counting. It is not SMC/ICT. It is not CVD-driven. It is not multi-factor confluence in the trading sense.

The scoring is **deterministic rule-based**, not ML or heuristic. Every score can be fully explained.

### Market Data Is Solid
Market-data service provides real, labeled, normalized data. Every metric has a REAL/PROXY/STALE/UNAVAILABLE status. Regime labels have explicit code thresholds. This is good engineering.

### Three Concrete Bugs Found

1. **`exposure_data=None`** in `services/fusion-engine/app/worker.py:82`
   - The exposure penalty in EnhancedScorer is always 0 because the worker never fetches exposure data
   - Fix: call `GET /state/positions` in the worker before calling compute_enhanced_score()

2. **`blocked` status missing** from opportunity state machine
   - Risk-rejected previews leave opportunity in `new` status
   - Fix: add `blocked` status; UPDATE opportunity to `blocked` when RiskGuardian rejects at preview phase

3. **TTL mismatch**: fusion-engine sets `ttl_seconds=900`, state-api background task uses `OPPORTUNITY_TTL_SECONDS=300`
   - Low severity: state-api task is the authoritative expiry mechanism; fusion-engine TTL is advisory
   - Fix: align default values or remove fusion-engine TTL parameter

### What the System Is NOT (Confirmed via Code)
- Not SMC/ICT — zero BOS/CHOCH/FVG/sweep/displacement logic anywhere
- Not CVD-driven — CVD not ingested or computed
- Not using volume for directional bias — volume is regime classification only
- Not auto-sizing positions — leverage/size are user-set, not computed
- Not computing stops/TPs — SL/TP fields exist in DB but are not calculated anywhere

---

## Current Phase Anchor (Confirmed)

| Phase | Status |
|-------|--------|
| Phase 2.5 — Reliability | DONE |
| Phase 3A — Cockpit stabilization | DONE |
| Phase 3B — Market normalization | DONE (Drift book gap remains) |
| Phase 3C — Enhanced scoring | DONE (exposure_data bug remains) |
| Phase 3D — Replay/backtest | PARTIAL (scaffold done, not fully wired) |
| Phase 3E — Wallet/signing | DEFERRED — not now |
| Phase 3F — Lifecycle management | NOT STARTED — this is next |

---

## Recommended Next Build Step

**Phase 3F-1: Fix exposure_data wiring in fusion-engine**

File: `services/fusion-engine/app/worker.py`
Line 82: `exposure_data=None  # TODO: Fetch from state-api when available`

Fix: Before calling `compute_enhanced_score()`, call `GET state-api:8000/state/positions` and build the `exposure_data` dict expected by `EnhancedScorer._compute_exposure_penalty()`:
```python
exposure_data = {
    "by_symbol": {symbol: current_notional_usd},
    "margin_utilization": current_margin_util
}
```

This is the highest-value single fix because the exposure penalty was designed as a meaningful risk filter but has never actually run.

**Phase 3F-2: Add `blocked` status to opportunity state machine**

When RiskGuardian rejects at preview phase, the opportunity should move to `blocked` rather than staying `new`. This prevents repeated preview attempts on an opportunity that is fundamentally ineligible.

---

## What NOT to Build Next

- Phase 3E (wallet signing) — DEFERRED
- Copilot/RAG/Sources Library — Phase 4, not next
- SMC/ICT scoring — no OHLCV data pipeline exists; prerequisite not met
- New venue integrations — fix what's broken on the two existing venues first
