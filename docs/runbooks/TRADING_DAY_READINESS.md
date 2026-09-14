# Trading-day readiness — paper rehearsal first

Snapshot updated: 14 September 2026, 02:00 BST. This checklist is not approval to trade
real money. Refresh live health before each session; an old passing check expires.

## Current decision

**Ready for supervised paper-workstation testing; not verified for unattended
trading, dependable phone delivery or live execution.** The integrated end state
remains incomplete. A profitable strategy has not been demonstrated.

| Requirement | Evidence now | Remaining acceptance |
|---|---|---|
| Current market/timeframe views | Locally deployed 1h/4h/8h/1d analysis and market views | Check freshness and symbol coverage at session start |
| Liquidity context | Observed Hyperliquid top-of-book history and separate Bybit liquidation receipts | Not complete depth history or a predicted liquidation map; direct Hyperliquid liquidation feed unavailable |
| Managed paper interface | Desktop/375px action QA passed with labelled fixtures | Operator uses a genuinely fresh eligible opportunity |
| Paper API with real prices | Isolated API test opened/closed on live Hyperliquid quotes/candles; duplicate prevented and evidence unchanged | Sustained real-signal forward cohort, stops/targets and outage behaviour under real elapsed time |
| Cost-aware outcomes | Fees/slippage and adverse funding scenario recorded | Actual funding settlement, account fee tier and deeper fill modelling |
| Entry provenance | Opportunity, quotes, candles, plan, digest, Bybit receipts and Hyperliquid book-history cutoffs frozen | Broader source joins and continuous durable external archive |
| Android/iPhone notification path | Enrollment/outbox/worker and opt-in lifecycle preferences deployed; live configured=false | Private control setup, explicit subscription, both phones receive tests and sustained delivery acceptance |
| Wallet visibility | Public-address positions/orders/recent fills implemented | Operator wallet readback; not ownership or signing authority |
| Strategy evidence | Saved experiments, historical diagnostics, source comparison and immutable trial API/UI deployed; populated fixture evaluation passed | Real registration, later entries and elapsed forward outcomes; no automatic weight promotion |
| Live execution | Deliberately disabled | Separate signer, permissions, approvals, risk, reconciliation and explicit live authority |

## Before opening the first paper position

Current runtime acceptance snapshot: zero real registrations and managed paper
positions, paper/mobile workers without reported errors, mobile configured=false.
This is a working empty system, not a completed real trading day. The code/test
checks do not establish phone receipt, operator-wallet correctness or predictive skill.

Operator steps that cannot be replaced with fixtures: subscribe/confirm actual
Android and iPhone devices after private mobile setup; inspect the intended public
wallet address; choose and register a research style; take a supervised paper entry
from a genuine fresh opportunity and review its later outcome. No seed phrase is
required for watch-only acceptance. Live-money execution is a separate gated task.

1. Confirm paper mode and disabled execution. Do not paste a seed phrase or private
   key into TradeSync, a terminal, a notification or this checklist.
2. Open Market and Timeframes. Confirm correct symbol, venue, interval and current
   timestamps. A connected stream with no events is different from unavailable.
3. Inspect Fleet and ingestion health. Treat missing optional sources as missing;
   their absence must not silently fabricate evidence or block core market views.
4. On Signal Ledger, separate historical StrikeZone results, saved replay results
   and managed-paper positions. Do not add these overlapping cohorts together.
5. Select a fresh directional opportunity; choose a holding style intentionally.
   Scalp uses 15m candles/up to 3h; intraday 1h/up to 24h; swing 4h/up to 7 days.
   The source opportunity's chart interval can differ; the profile does not turn
   that source into a validated strategy for the chosen horizon.
6. Start with the default 250 USDC **simulated notional**, not account balance or
   leveraged risk. Read costs and refusal messages. Do not loosen a risk gate just
   because there is no admissible trade.
7. Confirm paper entry, then inspect its frozen evidence and exact stop/target.
   No selection opens a real venue position.

## During and after the session

- Keep the observer running. Check per-position quote time, not just service
  uptime. If a gap is flagged, unseen stop/target crossings remain unknown.
- Use paper close when appropriate. A failed close is not a completed exit;
  inspect the refreshed status and exit reason.
- Phone notifications are not yet operationally accepted. Until setup/receipt
  tests pass, do not rely on the phone to monitor a paper position. A notification
  never approves a trade, and provider acceptance does not prove delivery.
- Record why the opportunity was taken, its intended holding style and which
  evidence was genuinely available. Do not backfill later news into the thesis.
- Review net estimated return, price move, holding time, fees, funding assumption,
  adverse excursions when available and data gaps. A positive single session is
  not proof of an edge; do not increase risk to make dollar results look larger.
- Keep stopped, refused and losing experiments in the research record. Freeze
  any proposed changed weights as a new candidate; do not overwrite prior results.

## Reproducible acceptance evidence

`tools/qa_managed_paper_api.py` runs inside State API with its configured database
and market-data connection. It creates session-local temporary relations, invokes
the actual API handlers with a **fixture opportunity and live market data**, tests
duplicate prevention and immutable evidence, then rolls back. It starts no worker
and writes no public portfolio rows. This is integration evidence, not a strategy
trade or a profitability sample. Do not report its P&L as performance.

See [mobile setup](MOBILE_ALERTS.md), [paper research protocol](../research/2026-09-14_managed-paper-protocol.md),
[dashboard acceptance](../changes/2026-09-14_managed-paper-dashboard.md) and
[full remaining register](../ROADMAP_RECONCILIATION_2026-09-13.md).
