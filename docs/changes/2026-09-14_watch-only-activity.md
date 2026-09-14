# 14 September — watch-only wallet activity

## Repo-truth delta / changes

Codex / Axiom-Codex continued the active integration goal after the verified
liquidity/intraday slice. Existing dirty work on
`codex/2026-09-01-dashboard-overhaul` was preserved. E: 342 GB free at 00:23 BST.
This is the project-local activity/build record, not canonical ChaseOS writeback.

Execution Readiness now includes public-address open-order and recent-fill
inspection beside account balances and positions. New `wallet_activity.py`
reads Hyperliquid `frontendOpenOrders` and `userFills` independently and returns
per-dataset status, observation time, invalid-row count and display coverage.
The UI retains venue instrument IDs, order types, trigger/reduce-only details,
size/price, order IDs, closed P&L and fees. Latest 100 valid rows displayed;
the provider's recent-fill endpoint returns at most 2,000, not lifetime history.

Positions additionally expose entry price, leverage and liquidation price.
Optional 30-second visible-page refresh covers all three public reads. Clearing
the account removes the panel and resets refresh; it does not configure a signer.

Correctness repairs: string `"0"` position size no longer creates a spurious SHORT
position. Non-finite or malformed sizes fail closed. Numeric conversion excludes
NaN/infinity. Provider errors no longer echo raw exception text in account reads.
Data dashboard guidance informed explicit partial-failure and coverage labels.

## Untouched boundaries

No seed phrase, private key, signature request, account-ownership claim, wallet
configuration change or place/amend/cancel endpoint. No real trade or live
execution enablement. No commit/push, paid service or public publication.
Address-only WalletConnect still needs the operator's public project ID;
ordinary address inspection does not depend on it. Spot balances, cross-dex
account reconciliation and complete portfolio net performance remain unimplemented.

## Tests and verification

- `.venv/Scripts/python.exe tools/run_tests.py state-api`: **138 passed**.
  New tests cover side mapping, trigger/reduce-only retention, fee/P&L separation,
  malformed rows, latest-row cap, independent source failure, invalid key-shaped
  input rejected before HTTP, and zero/non-finite position sizes.
- `npm run build`: passed (24.10s); existing bundle-size/Browserslist/annotation
  warnings remain. State API and Cockpit Docker images built and deployed locally.
- Live `/state/execution/wallet-activity` check with the official documentation's
  zero-address sample: both datasets available; 0 open orders, 2,000 returned
  fills. This sample is **not** the operator's wallet and not assumed empty.
  No user account was selected or inferred. No lifetime completeness claim.
- `node tools/qa_wallet_activity.cjs`: **1366 / 375px passed**, no document
  overflow or uncaught errors. Explicit QA fixtures exercise a position and
  trigger order beside unavailable fills; clear-account removes activity.
  The phone screenshot was visually inspected. Tables scroll locally.
- Final `.venv/Scripts/python.exe tools/run_tests.py root state-api`:
  **640 root passed** (17 integration deselected, two warnings, 10 subtests),
  **138 State API passed**. `git diff --check` passed with line-ending warnings.

Visual QA:
`E:/Visual QA/TradeSync Visual QA/Current Reviews/2026-09-14-wallet-activity`.
Fixture screenshots are not evidence of a funded account or successful trade.

## Remaining unknowns / next safe action

Operator account acceptance needs a public Hyperliquid address supplied in the
panel (never a key). Physical Android/iPhone wallet-app pairing is unverified.
Mobile-alert implementation is next: explicit device enrollment, generic
non-sensitive free-provider payloads, durable outbox, retry/expiry/dedupe and
separate provider-accepted versus phone-received states. A non-blocking prompt
asks which phone can run the first ntfy acceptance test. No message was sent.

The wider goal remains active: mobile delivery, durable entry-time evidence,
managed paper positions, registered quant research and evaluated strategy
improvements remain required. Profitable trading and live readiness are not
established by account visibility.

## Learning note

Order side (BUY/SELL) is not position side (LONG/SHORT): selling can reduce a
long or open a short. A trigger price is a condition, not a guaranteed fill.
Closed P&L and a separately reported fee cannot be labelled portfolio net return
without reconciliation, funding and complete coverage. Exercise: for a 3 USDC
closed-P&L field and a 0.1 USDC fee, calculate the local difference, then name
the missing evidence that prevents treating it as the account's total profit.

Primary schema: [Hyperliquid Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint).
