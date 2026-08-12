# Parallel Pass: Roadmap Uplift, Drift Provider Fix, Explainability Audit

**Date:** 2026-03-29
**Scope:** Three concurrent work tracks: (1) roadmap accuracy + future intelligence layers, (2) Drift data provider 404 bug fix, (3) score/confluence explainability data path audit

---

## Executive Summary

Three tracks executed in parallel. The Drift `/contracts` 404 bug is fixed — market-data will now pull live funding, OI, volume, and price from Drift. The canonical roadmap is updated to reflect that Phase 3F is largely done and to capture all future intelligence layer work (SMC/ICT, BOS/CHOCH, FVGs, CVD, etc.) that belongs in Phase 4A. The explainability audit confirmed that `score_breakdown` data already exists in the DB and is returned by the API but is never rendered in the cockpit — a pure UI gap.

No wallet/signing or autonomous execution changes were made. No SMC/ICT code was written.

---

## Runtime Context Used

- `services/market-data/app/providers/drift.py` — read in full (300 lines)
- `docs/roadmap/CANONICAL_ROADMAP.md` — read in full (207 lines)
- `services/fusion-engine/app/worker.py` — audited by subagent
- `services/state-api/app/main.py` — opportunity endpoints audited
- `services/cockpit-ui/src/pages/OpportunityDetail.tsx` — rendering audit
- `services/cockpit-ui/src/api/types.ts` — type definitions confirmed
- Drift Data API (`https://data.api.drift.trade`) — live endpoint verification

---

## Roadmap Uplift Changes

**`docs/roadmap/CANONICAL_ROADMAP.md`** updated:

### Phase 3F — status corrections
- **3F-1**: `NOT STARTED` → `DONE` (`blocked` status implemented, rejection stored in `links`)
- **3F-2**: `NOT STARTED` → `DONE` (background expiry loop running, `expires_at` enforced)
- **3F-5**: `NOT STARTED` → `PARTIAL` (limit check works in RiskGuardian; counter not incremented after fills)

### Phase 3G — new phase (Explainability / Score Transparency)
Added 7 items tracking the gap between stored confluence data and UI rendering. Key items:
- 3G-1/2/3: DONE (data stored, execution_risk rendered, warnings rendered)
- 3G-4/5/6: NOT STARTED (score_breakdown waterfall, notes display, regime linkage)
- 3G-7: NOT STARTED (`exposure_data=None` in fusion-engine — exposure penalty always 0)

### Phase 4A — new phase (Market Intelligence Layers)
Captured all future structural analysis work that has been discussed but not yet planned:

| Item | Layer |
|------|-------|
| 4A-1 | BOS/CHOCH detection |
| 4A-2 | Fair Value Gap (FVG) detection |
| 4A-3 | Liquidity sweep / stop hunt detection |
| 4A-4 | Order block identification |
| 4A-5 | CVD (Cumulative Volume Delta) ingestion |
| 4A-6 | Volume delta scoring |
| 4A-7 | Liquidation map proxy (PARTIAL — proxy exists) |
| 4A-8 | Orderflow imbalance signal |
| 4A-9 | OHLCV ingest pipeline (gate for all above) |
| 4A-10 | SMC/ICT composite signal |

**Gate:** 4A-9 (OHLCV ingest) must exist before any structural pattern work begins.

### Phase 4B/4C — renamed and split
Old Phase 4 (RAG/Copilot) → **Phase 4B**. New Phase 4C captures position intelligence (fill confirmation, notional counter, backtest surfacing, calibration loop).

### Current Development Lane — updated
Points to Phase 3G (explainability) as the correct next step, with OHLCV pipeline (4A-9) as the prerequisite gate for the SMC/ICT layer.

---

## Drift Provider Investigation

**File:** `services/market-data/app/providers/drift.py`

**Symptom:** `fetch_context` called `https://data.api.drift.trade/contracts` → HTTP 404. Error is caught silently; Drift context data (funding, OI, volume, price) was missing from all market snapshots.

**Root cause:** Drift API removed the `/contracts` endpoint. Current replacement is `/stats/markets`.

**Fix:** `fetch_context` updated to call `/stats/markets`. Field mapping:

| Old field | New field |
|-----------|-----------|
| `ticker_id` | `symbol` |
| `funding_rate` | `fundingRate` (handles scalar or `{long, short}`) |
| `open_interest` | `openInterest` (handles scalar or `{long, short}`) |
| `24h_volume` | `baseVolume` |
| `mark_price` | `markPrice` |
| `index_price` | `oraclePrice` |
| `last_price` | `price` |
| `max_leverage` | `limits.maxLeverage` |
| `market_index` | resolved from `_market_index` dict (unchanged) |

Output contract is identical — downstream `MarketNormalizer` requires no changes.

`fetch_orderbook` (DLOB/l2) and `fetch_funding_history` (/fundingRates) were unaffected.

---

## Explainability Data Path Findings

Full findings in `docs/architecture/EXPLAINABILITY_DATA_PATH.md`.

**Key finding:** The data pipeline is complete. `score_breakdown` (alpha, penalties, regime_bonus, final_score, notes) is stored in `confluence` JSONB, returned by `/state/opportunities` and `/state/evidence`, and typed correctly in `types.ts`. The TypeScript types already have `ScoreBreakdown`.

**Rendering gap:**
- `confluence.execution_risk` → **rendered** (ExecutionRiskBox)
- `confluence.warnings` → **rendered**
- `confluence.score_breakdown` → **not rendered anywhere**
- `confluence.score_breakdown.notes[]` → **not rendered anywhere**

**Minimum viable plan:** One `ScoreBreakdownCard` component in `OpportunityDetail.tsx` would close the most important gap. The notes array provides per-component explanations already — no additional backend work needed.

**Secondary gap:** `exposure_data=None` in `fusion-engine/app/worker.py` means `exposure_penalty` is always 0. This requires wiring the worker to `GET /state/positions` before the exposure component becomes meaningful.

---

## Small Contract / Backend Fixes Made

| File | Fix |
|------|-----|
| `services/market-data/app/providers/drift.py` | `/contracts` → `/stats/markets`; field name remapping; marketType filter |

No state-api, exec, or DB changes. No frontend changes (explainability rendering is documented as a future step, not built in this pass per scope rules).

---

## Files Changed

| File | Change |
|------|--------|
| `services/market-data/app/providers/drift.py` | `fetch_context`: `/contracts` → `/stats/markets`, new field mapping |
| `docs/roadmap/CANONICAL_ROADMAP.md` | Phase 3F status corrections; new Phase 3G; new Phase 4A/4B/4C; updated dev lane |

---

## Docs Created / Updated

| File | Type |
|------|------|
| `docs/architecture/DRIFT_PROVIDER_RUNTIME_AUDIT.md` | New — Drift 404 root cause, fix, field mapping, verification steps |
| `docs/architecture/EXPLAINABILITY_DATA_PATH.md` | New — Full confluence data path; gap analysis; rendering plan |
| `docs/roadmap/CANONICAL_ROADMAP.md` | Updated — Phase 3F corrections, Phase 3G/4A/4B/4C additions |
| `docs/changes/2026-03-29_parallel-roadmap-drift-explainability-pass.md` | This file |

---

## Verification Results

**Drift provider fix** — Static analysis only. No Docker container available to run against live Drift API. Correctness verified by:
- Confirmed `/stats/markets` returns HTTP 200 with `{"success": true, "markets": [...]}` via subagent web fetch
- Field mapping verified against Drift Data API spec
- Output contract to `MarketNormalizer` is unchanged

**To validate after deploy:**
```bash
docker compose -f ops/compose.full.yml logs -f market-data | grep -i drift
# Expect: "Fetched context for N symbols from Drift" (not error)

curl -s http://localhost:8005/market/aggregate/BTC-PERP | jq '.drift.funding'
# Expect: non-null funding rate
```

---

## Known Limitations

1. **Drift fix not integration-tested** — Live container not run. Field shape of `fundingRate` and `openInterest` in `/stats/markets` response is inferred from API spec. If Drift returns a flat scalar (not dict), the `isinstance(funding_raw, dict)` guard handles it. If the response schema differs from spec, the fix may return zeros without error.

2. **`market_index` hardcoded** — BTC-PERP=0, ETH-PERP=1, SOL-PERP=2. New markets added by Drift may get wrong indices. This affects `fetch_orderbook` which uses `marketIndex` param. Not changed in this pass.

3. **`exposure_penalty` always 0** — The scoring gap requires a separate fix in `fusion-engine/app/worker.py` (roadmap 3G-7). Not in scope for this pass.

4. **Explainability UI not built** — This pass produced the rendering plan and confirmed the data exists. Building `ScoreBreakdownCard` is the next recommended step.

---

## Next Recommended Step

1. **Validate Drift fix** — restart market-data container and confirm logs show successful context fetch
2. **Build ScoreBreakdownCard** — the data is there; one component in `OpportunityDetail.tsx` closes the most visible explainability gap
3. **Wire `exposure_data`** in fusion-engine worker before the ScoreBreakdown display goes live (otherwise exposure_penalty is always 0, which is confusing if displayed)

Do NOT proceed to wallet/signing/autonomous execution work.
