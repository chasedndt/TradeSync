# Frozen liquidation context at paper entry

## Evidence inspection UI — 01:39 BST

Managed-paper entry inspection now summarizes each frozen source's status,
cutoff, retained/excluded observations, coverage and scoring influence. Unknown
counts remain unknown. Older records without separate context are not backfilled.
Raw JSON is retained behind an expandable control. This revision used the existing
dashboard's source/coverage hierarchy, not a new layout or scoring system.

`npm run build` passed (Vite 26.73s; existing dependency/bundle warnings). UI image
rebuilt and cockpit-ui alone replaced. `tools/qa_managed_paper_ui.cjs` passed at
1366/375px: real empty portfolio, fixture open/close, empty liquidation receipt
context, unavailable book context, cutoff summaries, raw inspection, cancelled
open sends nothing, no page errors/document overflow. Phone screenshot inspected:
`E:/Visual QA/TradeSync Visual QA/Current Reviews/2026-09-14-entry-context`.
Fixture results are not a trading track record. No backend/secret/order changes.

## Liquidity-history continuation — 01:36 BST

Entry evidence also includes Hyperliquid book-history snapshots. The filter checks
venue/symbol, positive finite level values, both sides, sample time <= capture
cutoff, one-hour retention and a 240-sample cap. It preserves gaps, labels stale
and empty separately, and deep-copies nested input records. Each optional request
is bounded to three seconds and completes before entry quote acquisition. No
scoring influence is granted; displayed orders can cancel and are not fills.
Unavailable liquidation responses now consistently retain cutoff and authority.

State API suite: **173 passed in 14.21s**. Image rebuilt and State API alone
replaced. Extended isolated live-market API acceptance passed both context cutoff
checks, open/duplicate/close and unchanged evidence; simulated entry
76687.3344, close 76649.667. Fixture opportunity, no performance claim; all SQL
rows rolled back. No UI change, secret, phone send, wallet, commit or push.

Next: concise context inspection in the dashboard and pre-registered source
comparisons. Capturing evidence is implemented for these two feeds; comprehensive
ingestion joins, historical research archive and predictive validation are not.

14 September 2026, 01:31–01:33 BST. Codex / Axiom-Codex; existing dirty branch
preserved, E: 342 GB free. Project-local activity record, no canonical writeback.

Paper entries now request optional Bybit liquidation context before fetching the
entry quote/candles. The request is bounded to three seconds; failure is recorded
as unavailable, not a core dependency. Valid v2 receipts are filtered to a one-hour
window with event_time <= received_at <= capture cutoff. Unknown, nonfinite,
future-received, duplicate and invalid-order timestamps are excluded. Source and
symbol are checked. Snapshot, cutoff, excluded count and coverage caveats are
stored in the existing immutable PostgreSQL entry evidence; no migration needed.

This is a captured observation set, not a new scored feature. No weight, trade
rule, approval or execution authority changed. Other source joins, continuous
durable archival and source-contribution evaluation remain incomplete. Empty
receipts do not establish zero market liquidations. Receipt timestamps are local
collector observations, not independently trusted clock attestations.

Verification: State API suite **170 passed in 11.44s**, including eight causal
filter checks. State API image rebuilt and locally replaced; no frontend change.
The real-market isolated paper API script now checks context cutoff <= entry time,
all retained receipts <= cutoff, and scoring_influence=false, alongside the
existing open/duplicate/close/unchanged-evidence checks. Its runtime result is
recorded in the task output; no public portfolio writes or real trades.

Live acceptance: first attempt refused close with quote-validation ValueError and
rolled back. QA now waits at most five three-second intervals for a fresh valid
close observation without changing prices or relaxing validation. Rerun passed:
entry 76723.3416, operator close 76696.6576, duplicate prevented, context cutoff
checks passed, entry evidence unchanged; all temporary SQL rows rolled back.
These are fixture-opportunity/live-market integration observations, not performance.

No secrets, phone delivery, wallet/signature, commit or push. Next: liquidity-book
entry capture, explicit context inspection, registered source-ablation comparisons
and remaining trading-day/mobile/operator-wallet acceptance.

[Documentation index](../README.md) · [Roadmap](../../roadmap.md).
