# Watch-only wallet onboarding

9 September 2026 — Codex. Continues the Canvas/adapter slice without changing its pending work. Existing dirty changes preserved.

## Implemented

- Execution page public-address form, validation, explicit View account action and Clear account.
- Session-only query; no localStorage persistence and no change to WALLET_ADDRESS. Address sent through TradeSync to the configured Hyperliquid public info endpoint. Public addresses can appear in HTTP access logs; this is not an anonymity feature.
- Existing wallet-preview API accepts an optional validated EVM public address, reports lookup mode, network inferred from the configured Hyperliquid URL, and response observation time.
- Account value, withdrawable funds, margin used and perpetual positions/unrealized P&L. Does not promise spot balances, open orders or historical P&L.
- Invalid public addresses rejected before HTTP calls. Incomplete/non-finite balance fields return unavailable, not fabricated zeros.
- Explicit fetch, loading, failure and clear states. No automatic account polling, order controls, key input, signer activation or ownership claim.

## Tests

`PYTHONPATH=services/state-api;libs/tradesync_core .venv/Scripts/python.exe -m pytest services/state-api/tests/test_adapters.py services/state-api/tests/test_watch_only_wallet.py -q`: 9 passed. Tests mock the venue; no real user's wallet was queried.

`npx tsc --noEmit --pretty false`: passed. Docker updates are bounded to state-api and cockpit-ui, sequentially, with `--no-deps`; volumes and producer services are retained. Final runtime/build readbacks are reported in the task closeout. Rendered-browser and mobile acceptance remain unverified, not implied by TypeScript or HTTP checks.

## Boundaries and remaining work

Runtime closeout: both bounded Docker rebuilds passed; Cockpit bundle `index-Bq-iSQgB.js` was built. State API became healthy, invalid-address readback returned 422, configured-wallet readback remained `not_configured`, and PostgreSQL still recorded 15 signals in the preceding five minutes. Existing bundle-size/Browserslist warnings remain. No orphan cleanup ran. Browser interaction acceptance is still pending.

This is read-only account inspection, not “connecting” signing authority. No wallet address has been selected by the operator yet. No private keys, approvals, signers, execution settings, Discord jobs, paid feeds, canonical vaults or provider configuration were changed.

Unified backend connector status, screenshot/interaction acceptance, full paper rehearsal, net-cost-aware signal lifecycle and public webhook setup remain unfinished. The canonical ChaseOS path conflict is still unresolved. The dashboard skill guided clear source/authority labels and missing-value behavior.
