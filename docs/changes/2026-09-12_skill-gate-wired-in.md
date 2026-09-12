# The corrected skill gate, wired in

Date: 2026-09-12
Scope: migration `012_entry_regimes.sql`, `services/core-scorer/app/{outcome_regime,outcome_job}.py`,
`services/state-api/app/skill_gate.py` (`GET /state/outcomes/skill-gate`),
`services/cockpit-ui/src/components/SkillGatePanel.tsx` on the Regime Lab, tests.

Slice 3 of the delivery sequence: the measurement built on 2026-09-11
(`changes/2026-09-11_measurement-hardening-core.md`) now runs on real data and
is visible on the dashboard. `/state/outcomes/by-regime` remains for
comparison; it is the old method and its note says so.

## What changed

- **Entry-time regimes are recorded.** The outcome job now starts its candle
  fetch an hour earlier and, after measuring each opportunity, labels the
  regime from candles that had fully closed before the signal — once, never
  overwritten. Opportunities measured before today are backfilled at 120 per
  pass without re-measuring their outcomes, so a fetch at 5m today cannot
  change a result recorded at 1m earlier.
- **The endpoint assesses every cell together.** All horizons × regimes go
  through `edge_evidence.assess_cells` in one call, so the Holm adjustment
  sees every cell that was looked at. Costs are stated: 2 × the venue's
  published taker fee plus conservative spread and slippage defaults, source
  on the response.
- **Three verdicts on the Regime Lab.** Detectable / positive skill /
  economic edge per cell, with the pooled independent-window count beside the
  raw n, the hold-out skill, and the net return after costs.

## Live, minutes after deploy (labels still backfilling)

```
cells 11 | gate CLOSED | any_detectable False | any_positive_skill False | any_economic_edge False
  15m unknown   n=1059 independent(pooled)=243  skill -1.8 pts  z -0.56   net -0.123%
  60m unknown   n=1217 independent(pooled)= 70  skill -0.6 pts  z -0.10   net -0.125%
  240m unknown  n=1217 independent(pooled)= 20  skill -4.8 pts  z -0.43   net -0.227%
```

Same verdict as every earlier reading, on firmer ground: the independence is
counted, not estimated, and the returns are net of stated costs — negative in
every cell. "unknown" is the honest label for opportunities not yet backfilled;
the regime split fills in over the following hour.

## Tests

487 root, 65 state-api (three new: grouping by entry regime with "unknown"
kept, costs naming their source, and one marginal cell among nulls not
becoming "positive skill" because cells are adjusted together).
