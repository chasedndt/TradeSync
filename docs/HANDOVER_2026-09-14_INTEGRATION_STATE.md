# TradeSync integration handover — 14 September 2026

## Repo-truth delta

Snapshot 02:02 BST; Codex / Axiom-Codex. Canonical working checkout:
`E:/Projects/TradeSync/dashboard-overhaul-2026-09-01`, branch
`codex/2026-09-01-dashboard-overhaul`. Large shared dirty worktree preserved;
recent changes are uncommitted/unpushed. E: approximately 342 GB free.
Repository authority identifies ChaseOS at
`C:/Users/chaseos/Documents/chaseos_chaseintech`; no canonical writeback performed.

## Changes now locally deployed

- Market: internal observed top-ten-level Hyperliquid history and separate Bybit
  liquidation receipts; first-received timestamps survive replay deduplication.
  Neither is a predicted liquidation map or complete market-wide liquidation feed.
- Timeframes: 1h/4h/8h/1d descriptive intraday views, distinct from daily analysis.
- Wallet: session-only public-address position/open-order/recent-fill inspection,
  including partial-source failure states. No imported keys or signing authority.
- Signal Ledger: existing loss-making StrikeZone ledger retained; saved cost-aware
  replays and separate operator-managed paper positions with scalp/intraday/swing
  profiles, entry evidence, stops/targets/time/manual exits and gap flags.
- Frozen entry context: eligible Bybit receipts and Hyperliquid book samples stored
  in PostgreSQL alongside quotes/candles/initial plan. Cutoffs precede entry.
  Optional-source failures are explicit, bounded and do not block the core path.
- Source comparison: hypothetical liquidity abstention filter, same opportunity
  denominator and style cohorts; missing context and exclusions are explicit.
- Research registry: immutable specifications/fingerprints/timestamps, idempotent
  registration, forward-only evaluation and explicit dashboard controls. No real
  registration or managed position exists at the latest acceptance readback.
- Mobile: ntfy generic transport, Android/iPhone enrollment, outbox/dedupe/retries,
  expiry, receipt attestation, opt-in paper open/close events, quiet hours and
  per-device rolling budget. **Runtime configured=false; no phone delivery proved.**

## Untouched boundaries

Paper/research only; no live order, wallet signature, seed/private-key import,
automatic weight promotion, new public endpoint, external publication, paid
service, commit or push. Existing scheduled Hermes jobs were not manually run to
manufacture receipts. No canonical graph edits. Optional connectors remain
separate from core availability. Notifications never grant approval authority.

## Tests and verification status

Most recent full Python run: **659 root / 177 State API passed**, 17 integration
deselected, two existing warnings. Market-data suite: **126 passed** in its latest
relevant run. These are dated per-slice results, not a single whole-stack soak.

Real isolated PostgreSQL checks: paper open/close with live market observations,
frozen evidence, mobile policy and authenticated routes, registry protections,
registration/evaluation including populated synthetic outcomes. All QA rows/schema
rolled back. Real Redis receipt deduplication/retention tested in expiring QA keys.
UI builds and headless Chromium checks at 1366/375px passed for paper, context,
comparison, registry and notifications; screenshots inspected in the dedicated
TradeSync Visual QA home. Fixtures are labelled and not trading performance.

Last runtime readback: zero trials/managed positions, paper/mobile worker errors
null, mobile unconfigured. No whole trading-day, physical Android/iPhone, operator
wallet, independent strategy edge or unattended/live execution acceptance claimed.

## Remaining unknowns and next safe actions

1. **Paper portfolio safety:** persistent pause/kill state, capital accounting,
   daily loss/drawdown/exposure controls, restart reconciliation and observed
   MFE/MAE. Current three-position/one-symbol/size gates are not a full risk engine.
2. **Operator acceptance:** private mobile control setup, both phone subscriptions
   and actual receipts; intended public wallet readback; real supervised paper
   entries. No private wallet material is needed for watch-only acceptance.
3. **Evidence/research:** broader causal ingestion joins, continuous durable
   history, actual funding settlement, forward observations and uncertainty/
   dependence/multiple-test assessment. A source filter's threshold is a hypothesis.
4. **Security:** review local-storage control credentials/session isolation and
   API authorization before remote access. Do not repurpose the Pine tunnel to
   publish the dashboard. WalletConnect still needs project-ID/pairing acceptance.
5. **Hermes:** retain scheduled receipt/freshness, ownership/transport and graph
   hygiene items from the September 13 register. Not all connector work is done.
6. **Later authority:** testnet/non-broadcast signer/approval/nonce/reconciliation
   gates and explicit operator live authority. No calendar date overrides them.

The full goal remains active, not blocked or complete. Next implementation should
prioritize paper portfolio safety, alongside operator onboarding, rather than
adding feeds without a decision/evaluation role.

## Logs and indexes

[Documentation index](README.md) · [Roadmap](../roadmap.md) ·
[Trading-day checklist](runbooks/TRADING_DAY_READINESS.md) ·
[Full inherited handover register](ROADMAP_RECONCILIATION_2026-09-13.md) ·
[Research registry acceptance](changes/2026-09-14_research-registration.md) ·
[Mobile policy acceptance](changes/2026-09-14_mobile-lifecycle-policy.md) ·
[Entry context acceptance](changes/2026-09-14_entry-liquidation-context.md).
