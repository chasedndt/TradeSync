# Regime Lab Operating Slice — 2026-09-01

## Repo-truth delta

Previously the feature catalog and normalizer were isolated paper-shadow
foundations. Market-data did not retain admitted feature series, the State API
did not aggregate or compare rulebooks, the documented migration runner did not
exist, and there was no Regime Lab UI.

This change adds catalog sampling cadences, nine snapshot extractors,
cadence-governed seven-day history, shared Python aggregation, State API
overview/evaluate/save/history routes, operator learning gates, responsive
`/regime-lab`, and transactional Compose migrations. It adds no activation,
wallet, approval, or execution endpoint.

## Verification

- shared feature/regime/migration suite: 33 tests passed;
- market-data focused suite: 19 tests passed, including async rate limiting;
- Regime Lab API and context suite: 5 tests passed;
- TypeScript: `npx tsc --noEmit` passed;
- Cockpit production build: 1,858 modules transformed and bundle completed;
- browser: degraded source state rendered, inputs enabled evaluation,
  same-evidence comparison appeared, and save failed closed with PostgreSQL
  unavailable;
- responsive: 390 × 844 had no document-level horizontal overflow;
- Docker daemon: unavailable, so container builds, SQL transactions, live
  feature accumulation, and durable save remain unverified.

Four older `services/state-api/tests/test_main.py` cases still fail because
their mocks omit fields required by current expanded endpoints. They are not
counted as passing.

## Visual evidence

`E:\Visual QA\TradeSync Visual QA\Current Reviews\2026-09-01-regime-lab`

The operating panel is not yet a fully live evidence/persistence surface on
this host, and it does not replace the legacy active opportunity scorer.
