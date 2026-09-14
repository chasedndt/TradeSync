# First-received liquidation provenance

14 September 2026, 01:28–01:30 BST. Codex / Axiom-Codex, preserved dirty checkout;
E: 342 GB free. Project-local activity/build record; no canonical writeback.

## Repo-truth delta

The initial Bybit display collector dropped `received_at` to deduplicate events.
That made its stored rows unsuitable for proving when TradeSync knew an event.
The v2 collector now stores payloads by stable fingerprint, with a separate sorted
index and atomic Redis script. A replay cannot replace the first receipt time.
Both structures retain at most 1,000 events per symbol and expire/prune together.

V2 uses a new namespace. Old display-only records remain until their existing TTL
expires; they are not assigned invented receipt timestamps or migrated into v2.
The new view starts collecting at deployment. This is bounded Redis provenance,
**not yet a durable PostgreSQL research archive or a scoring feature**.

## Verification

- `.venv/Scripts/python.exe tools/run_tests.py market-data`: **126 passed in 3.49s**.
- Market-data image rebuilt; only that service replaced locally.
- `tools/qa_liquidation_receipts.py` against real Redis: first receipt preserved
  under replay, ZSET/hash capped together at 1,000, age pruning consistent: passed.
  Used unique QA keys, set to expire after 60 seconds; no production feed mutation.
- Live State API proxy: `receipt_schema=first-received-v2`, connected, zero events
  immediately after restart. Zero is an empty new observation window, not proof
  that no market liquidations occurred. Market-data container healthy.

## Boundaries / next safe action

No source weight, trading rule, wallet, secret, notification, commit or push.
Bybit bankruptcy-price estimates remain context-only and are not Hyperliquid
liquidations. Book-history remains a bounded observed-order display.

Next: persist an entry-time snapshot of these observations with receipt cutoff,
coverage and unavailable states; test no future-received evidence enters a past
decision. Then evaluate source contribution in frozen forward experiments.

[Documentation index](../README.md) · [Roadmap](../../roadmap.md) ·
[Trading-day checklist](../runbooks/TRADING_DAY_READINESS.md).
