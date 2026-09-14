# Managed-paper dashboard — 14 September 2026

## Repo-truth delta and changes

Codex / Axiom-Codex continued on the preserved dirty dashboard-overhaul branch,
01:07–01:15 BST. E: had 342 GB free. This is the project-local activity/build
record; no canonical ChaseOS writeback was performed.

Signal Ledger now exposes the previously deployed managed-paper backend:

- Select a fresh directional BTC/ETH/SOL opportunity from the latest 100 new
  records, then choose scalp, intraday or swing and a simulated notional.
- Explicit confirmation before paper entry or operator close. Server-side
  freshness, displayed liquidity, costs and portfolio caps still decide admission.
- Inspect each position's entry, stop, target, estimated net, fees, funding
  scenario, expiry, quote observations and gap warnings.
- Retrieve frozen entry evidence and its fingerprint on demand.
- Keep this operator-managed cohort separate from the existing StrikeZone ledger.

The dashboard guidance informed the separation of controls, observed lifecycle
state and evidence inspection, including explicit unavailable values and mobile
wrapping. This is an existing-app revision, not a new hosted dashboard.

## Untouched boundaries

Only cockpit-ui was rebuilt/replaced. No real portfolio entry, close, wallet,
signature, mobile message, strategy weight, secret, commit, push or public
deployment. Existing dirty changes and all other services were preserved.
New liquidation/book-history context is not yet joined into entry decisions;
the panel explicitly discloses this. Funding remains a scenario.

## Tests and verification

- `npm run build` in `services/cockpit-ui`: TypeScript and Vite passed. Existing
  bundle-size, old Browserslist-data and dependency annotation warnings remain.
- `docker build -f ops/cockpit-prebuilt.Dockerfile -t tradesync/cockpit-ui:dev services/cockpit-ui`: passed.
- Local compose replacement of cockpit-ui only: passed.
- `node tools/qa_managed_paper_ui.cjs`: passed at 1366 and 375 CSS pixels.
  Real empty portfolio readback; fixture-only open/close/evidence inspection;
  dismissed confirmation sends no write; no page errors or document overflow.
- Desktop real-empty and phone fixture-populated screenshots visually inspected.
  Evidence: `E:/Visual QA/TradeSync Visual QA/Current Reviews/2026-09-14-managed-paper/`.
- Live API still returned zero positions, current observer heartbeat, no worker
  error and `execution_authority=false`. No live-data completed trade is claimed.
- Backend was unchanged in this slice; its prior 648 root / 149 API passing
  results are recorded in the backend change log, not presented as a new run.

## Remaining unknowns and next safe action

1. Exercise a real-data paper entry/lifecycle with auditable test isolation; the
   browser's populated action tests used fixtures, not an actual opportunity fill.
2. Add opt-in lifecycle notification producers, quiet hours and delivery budgets.
   Device setup and real Android/iPhone receipt acceptance remain outstanding.
3. Archive external evidence with first-received timestamps and coverage; join
   only evidence available at entry. Displayed resting orders are not predicted
   liquidation levels. Bybit liquidation receipts are not Hyperliquid closures.
4. Measure source contribution with frozen variants and forward observations;
   more intake does not establish higher predictive accuracy or profitability.
5. Complete trading-day readiness checks, settled funding, operator wallet
   acceptance and the remaining handover register. Live execution stays gated.

See [backend/protocol](2026-09-14_managed-paper-backend.md),
[goal register](2026-09-14_liquidity-intraday-and-integration-goal.md),
[documentation index](../README.md), and [roadmap](../../roadmap.md).
