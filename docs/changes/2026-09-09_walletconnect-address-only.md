# Optional WalletConnect address sharing

9 September 2026. Operator approved proceeding with the Community License and free-only scope. Operator has no project ID; live QR pairing remains setup-required.

## Implemented in source

WalletPairing is embedded in the watch-only account panel. It uses pinned `@walletconnect/sign-client` 2.24.0 and `qrcode` 1.5.4, with lazy imports. No provider initialization occurs just by opening the dashboard. User must supply their own public project ID and press Pair.

The required namespace is `eip155:1`, with empty methods/events. This is Ethereum-format address discovery, not an Ethereum trade, HyperEVM connection, network switch or Hyperliquid execution approval. Wallets that cannot accept address-only sessions are unsupported in this slice; do not add signing methods to improve compatibility. Phantom support has not been established.

After approval, the policy rejects unexpected namespaces/chains, malformed accounts and all nonempty signing-method grants. The session and pairing are closed before addresses are shown for the existing public Hyperliquid lookup. No request/sign/send API is exposed. Cancel/timeout invalidates late completions. Relay storage is in memory and SDK telemetry is disabled; the relay still receives connection metadata/IP as part of its service. Do not call this anonymous or offline pairing.

The QR is a short-lived pairing secret: never log it or put it in screenshots, docs, analytics or a database. Public project ID is session input, not a wallet key. User wallet seeds/private keys never enter TradeSync.

Community License attribution and the installed package's full licence are included at `services/cockpit-ui/public/walletconnect-license.txt`. No provider account, paid plan, real pairing, signature, order, wallet key, canonical-vault mutation or runtime environment modification occurred.

## Verification

`node --test tests/pairing-policy.test.mjs`: 8 passed (empty methods, account parsing/deduplication, unexpected signing grant, unsupported chain, Solana namespace, empty session, malformed address and isolated memory storage).

These are policy/unit checks, NOT a live wallet compatibility or lifecycle acceptance test. Required future tests include rejection, expiry, cancel during initialization/approval, app close/reopen, cleanup failure, multiple accounts and the desktop webview's relay access. The user must approve their own test pairing; do not automate real wallet approvals.

TypeScript check passed. The production build was stopped by this task before completion after free physical memory fell to approximately 1.6 GB. No Docker rebuild or running-dashboard replacement was performed. The last repeated policy run passed all eight tests. Complete a production build and visual QA under adequate memory before exposing pairing in the running app.

Dependency install reported 18 audit findings across the tree. Production-only audit identifies React Router advisories and high-severity picomatch findings. These require triage before calling this wallet-ready. No forced broad dependency upgrade was applied. Production build/readback status belongs in the task closeout; do not infer deployment from this file.

Follow-up: targeted `npm update picomatch --ignore-scripts --no-audit --no-fund` completed; installed version verified as 2.3.2, outside the audit's affected `<=2.3.1` range. Two packages changed. The full audit was not rerun afterward; other React Router/build-tool findings remain unresolved. Whitespace check passed. No claim of a clean dependency audit.

## Setup and next gate

1. Operator creates a project at https://dashboard.reown.com after reviewing current free-tier terms and allowed origins. No borrowed ID, paid trial or auto-upgrade.
2. Resolve dependency-security findings and verify final build.
3. Supply only the public project ID in the panel. Pair a compatible EVM wallet using QR; approve address sharing only. If a wallet requests signing, cancel.
4. Confirm address inspection and session closure with a real operator-led test. Public-address lookup remains the independent fallback.

QR removes dependence on an injected extension; a packaged desktop shell still needs its own network/CSP and lifecycle acceptance. This change does not create or certify a native desktop release.

Sources: https://github.com/WalletConnect/walletconnect-monorepo/tree/v2.0/packages/sign-client and https://github.com/WalletConnect/walletconnect-specs/blob/main/docs/specs/clients/sign/namespaces.md .
