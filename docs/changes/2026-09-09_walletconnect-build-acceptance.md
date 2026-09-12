# WalletConnect build and setup-screen acceptance

9 September 2026 — continuation of address-only pairing. Existing dirty work preserved. E: available, approximately 318 GiB free. Host free RAM initially approximately 5.2 GiB; heavy operations run sequentially.

## Dependency delta

Targeted compatible updates brought React Router/DOM to 6.30.6. Picomatch remains patched at 2.3.2. Production-only npm audit now reports zero high/critical and two moderate findings (react-router and react-router-dom, covering redirect and SSR-hydration advisories). This is NOT a clean audit. The full development dependency tree still reports 16 findings, including nine high. No forced major upgrade or broad cleanup ran. Resolve remaining findings before expanding wallet capabilities or exposing the application publicly.

## Verification

`node --test tests/pairing-policy.test.mjs`: 8 passed after targeted updates.

`git diff --check`: passed.

Added `tools/qa-wallet-setup.cjs` for headless Edge setup-screen acceptance without credentials, project IDs or real pairing. Screenshots are restricted to the unconfigured screen; no pairing QR is generated or captured. The check covers missing/invalid project ID, invalid address, no horizontal mobile overflow, no JavaScript page errors, and no WalletConnect/Reown requests before consent. Final build and browser outcomes are recorded in the task closeout and appended here after completion.

## Authority

No project ID exists; external pairing cannot be accepted as live. No wallet/private key was entered, no real approval automated, no transaction signed, and no execution or provider configuration changed. Docker action is restricted to cockpit-ui with `--no-deps`; databases, producers, signer and their volumes remain untouched.
