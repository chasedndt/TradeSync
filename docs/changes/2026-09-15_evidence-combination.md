# Evidence combination — sources combined by their measured likelihood ratios, as a shadow reading

Date: 2026-09-15
Branch: `claude/evidence-combination`, from `codex/2026-09-01-dashboard-overhaul` at `db27305`; worktree
`E:\Projects\TradeSync\evidence-combination-2026-09-15`. **Not merged, not deployed.**
Scope: `libs/tradesync_core/tradesync_core/evidence_combination*.py` (ten modules),
`services/state-api/app/evidence_combination.py` (+ its registration in `main.py`), the Cockpit panel in
`services/cockpit-ui/src/components/learning/combination/` (mounted in `LearningView.tsx`), the design
[docs/research/2026-09-15_evidence-combination.md](../research/2026-09-15_evidence-combination.md) and its
[appendix](../research/2026-09-15_evidence-combination-appendix.md), tests.

## Why

The Market Command plan (§5.1, §8) named one piece of maths still to design: the system could say whether
a source has skill but could not combine sources by their likelihood ratios. The operator wants to learn
that maths, so the design teaches it with hand-worked numbers before the formulas.

## What changed

- **Library (pure, typed).** Per source and horizon: the likelihood ratio of an up call and a down call,
  from Beta-binomial shrinkage toward 1 at effective counts (no evidence, no update), with delta-method 95%
  intervals; regime-specific ratios only where a source has 20 or more effective windows in that regime,
  shrunk toward the other regimes. Combination in log odds from the fitting period's own base rate;
  residual within-outcome correlation, shrunk toward full redundancy, sets a redundancy weight, so an exact
  copy counts once, a silent source dilutes no one and missing sources contribute nothing. Validation: a
  chronological purged split, Kish effective and non-overlapping windows, Brier score, log loss,
  equal-count reliability bins with Wilson intervals, Murphy's decomposition and detectability, paired
  differences with intervals at effective windows, the Platt-calibrated rulebook score as a baseline, the
  break-even probability for the 0.12% round trip, a plain-language reading and a SHA-256 method digest.
- **Endpoint.** `GET /state/research/evidence-combination?horizon=15|60|240` runs two SELECTs over
  `opportunity_attributions` (with `opportunities.confluence.directional_score`) and
  `opportunity_entry_features` for the 14-day learning window. One statistics-cache entry per horizon is
  measured in a worker thread (202 while first measured, 600 s lifetime, kept warm by the shared refresh
  loop). The response says `authority: research_only` and `promotion_allowed: false`; 422 for any other
  horizon, 503 without a database.
- **Cockpit.** An "Evidence combination" panel follows the verdict table in Opportunities → Learning at
  the selected horizon: the reading with its measured time; a forecast table (Brier score, log loss,
  calibration gap and whether it is detectable, log loss minus the base rate with interval and verdict); a
  reliability chart with a hover and focus readout and a table view; a source table (ratios with
  intervals, fitting record, regime conditioning, share of face value kept on test decisions); and a
  footer with the split, break-even levels and method digest. CSS modules per component.
- **Docs.** Thirteen worked examples, formulas, validation design, live numbers, governance with a proposed
  pre-registered forward comparison, limitations and exercises; the appendix holds every live table,
  reproduction steps and the exercise answers.

## Boundaries kept

- No scorer, rulebook, catalog, weight, opportunity-learning, managed-paper, security or fleet code changed.
  No migration. No write path: a test asserts the endpoint never calls `execute`.
- Only new files, plus the registration in `main.py` (an import and a call, the file's own pattern) and the
  panel mount (an import and one JSX line). `main.py` is 3,368 lines and was not split: it is outside this
  change's ownership and shared with parallel work.
- Live data was read only: GET requests and read-only transactions. Nothing was deployed and no container
  was touched.

## Live result

Read-only run at 01:19 UTC on 15 September with the branch code (`build_response`, the function the
endpoint runs), **local, not the deployed endpoint**. Test sets are the newest 30% of attributed decisions.

| Horizon | Test decisions · effective windows | Log loss: base rate / rulebook / combined | Calibration gap: base / combined | Combined − base rate, log loss (95%) |
|---|---|---|---|---|
| 15 min | 882 · 78.3 | 0.6936 / 0.6932 / 0.6958 | 1.54 / 4.21 pts | +0.0022 (−0.0121 to +0.0165) |
| 1 hour | 972 · 22.7 | 0.6930 / 0.6978 / 0.6934 | 1.34 / 1.95 pts | +0.0004 (−0.0152 to +0.0159) |
| 4 hours | 940 · 6.2 | 0.7390 / 0.7172 / 0.7461 | 14.99 / 15.93 pts | +0.0071 (−0.0349 to +0.0491) |

Brier score at 1 hour: base rate 0.2499, rulebook 0.2523, combined 0.2501. Every comparison, against both
baselines and at every horizon, is not distinguishable; no reliability bin's interval excludes its
forecast; no source's likelihood ratio has an interval excluding 1. No combined probability reached the
break-even levels (86.4% / 16.5% at 15 minutes, 70.7% / 36.0% at 1 hour). At 4 hours the fitting window's
base rate (36.7%) alone sat below the short level; the reading says so.

## Verification

- `tools/run_tests.py root`: **885 passed**, 17 deselected, 2 warnings, 49 subtests passed in 61.47 s
  (82 evidence-combination tests collected among them).
- `tools/run_tests.py state-api`: **293 passed** in 39.32 s.
- Cockpit `npm test`: **70 passed**, 0 failed (includes the new format tests and `ui-wording.test.mjs`);
  `tsc --noEmit` clean; `npm run build`: passed (Vite, 1 m 34 s after the last panel change; only the existing chunk-size warning).
- Palette validator for the chart pair (blue `#3a8bef`, amber `#c28400`) on the panel surface `#0d1928`,
  dark, all pairs: every check passes (CVD ΔE 28.4, normal-vision ΔE 30.9, contrast at least 3:1).
- Visual QA: a local Vite dev server on this worktree, with `/api` sent to a read-only mock. The mock
  served this endpoint from the live-data result and passed other GETs to the live state API; it refused
  every other method. Saved to `E:\Visual QA\TradeSync Visual QA\Current Reviews\2026-09-15-evidence-combination`:
  `learning-view-1366.png`, `panel-1366-top.png`, `panel-1366-bottom.png`, `chart-1366-zoom.png`. The
  375 px layout was checked in the Browser pane's mobile emulation with data loaded: document, body and
  main scroll widths all 375 (with the panel shown and hidden), panel 355 px, chart 328 px, and both wide
  tables scroll inside their own containers (329 of 565 px and 329 of 760 px). The saved 375 px Edge
  captures are clipped by Edge headless's minimum layout width and are not evidence of the phone layout.
  The rendered page text contains no retired wording.
- Fixed from QA before commit: the base-rate point was hidden under the combined dots (now a ring drawn
  on top); sources were described as leaning from point estimates such as ×0.99 (a lean is now named only
  when an interval excludes ×1.00).
- Fixed from the first live run (`0093eef`): pairs involving sources without a fitting record were
  dropped from the report; clearance caused by the base rate alone is flagged; the reading says whether a
  calibration gap is detectable.

## Deploy (for the lead)

1. Merge `claude/evidence-combination`. No migration and no environment change.
2. Rebuild and replace only the two services:
   `docker compose --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env -f ops\compose.full.yml -f ops\compose.market-command.yml up -d --build state-api cockpit-ui`
3. Read back `GET /state/research/evidence-combination?horizon=60`: first 202 `computing`, then 200 with
   `status: ready`, `schema_version: evidence_combination_v1`, `method.digest` beginning `96539f87` and
   `authority: research_only`. Then open Opportunities → Learning and step through 15m, 1h and 4h.
4. Roll back by reverting the merge and rebuilding the same two services.

## Open

- The forward comparison in the design is proposed, not registered: registration is the operator's
  decision, and freezing the fit needs a store (a research-trial specification or migration 034).
- TradingView and Discord claims (source cards) are not yet aligned to decisions.
- Context-only features show `label_for`'s fallback names (for example "hl resting liquidity imbalance");
  display labels belong in the shared label map or the catalog, outside this change.
- Playwright is not installed here, so saved captures used Edge headless and the phone layout was verified
  by measurement.
