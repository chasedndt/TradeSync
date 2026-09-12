# Pine ingress activation — Codex, 2026-09-12

Reviewed the Pine ingress handover at base commit e3d1a2b. Corrected the
Compose command to read `cloudflared.config.yml`, matching the documented
setup filename inside the read-only ingress directory mount. Previously it
requested `config.yml`, which the setup procedure does not create.

The operator corrected the canonical brand/domain spelling to ChaseInTech.
Cloudflare account authorization completed, the locally managed tunnel
`tradesync-webhook` was created with ID
`15945b2a-e022-4374-886f-e58a22291609`, and the DNS route
`tradesync-pine.chaseintech.com` was created. The earlier nested hostname
`pine.tradesync.chaseintech.com` failed TLS containment testing because free
Universal SSL covers only first-level subdomains in this full zone; it was
replaced rather than requiring a paid certificate.

The replacement DNS route is proxied to the same tunnel. The failed nested DNS
record was deleted by its exact record ID. No other ChaseInTech DNS record or
WAF rule was changed.

The related non-secret resource identity and current gate status are recorded
in `ops/ingress/TRADESYNC_CLOUDFLARE_PROFILE.md` as the **TradeSync Pine
Ingress** profile.

A 64-character random body secret was generated locally and written through
the desktop secret helper without being displayed. It is not active in the
running State API until that service is recreated after the WAF gate passes.

The current signed `cloudflared` client (2026.9.1) and account/tunnel
credentials are stored under the governed E: runtime directory. The temporary
default account certificate created at `C:\Users\chaseos\.cloudflared` was
moved to E:. The tunnel credential is mounted into Compose through the
gitignored ingress directory; neither credential is committed.

Cloudflare created a new zone-level custom ruleset because readback proved no
custom WAF entry-point ruleset previously existed. It contains one enabled
rule, scoped exactly to `tradesync-pine.chaseintech.com`, which blocks every
source except TradingView's four published webhook IPs. State API was recreated
to load the body secret and only the separate tunnel connector was started.

Runtime acceptance passed: `cloudflared` is healthy with four registered QUIC
edge connections; public workstation requests to the webhook, `/state/health`,
and `/` return Cloudflare `403` with Ray IDs; local State API health remains
`200`; and the local ingress matcher sends only the exact webhook path to the
origin. The remaining provider acceptance is one genuine TradingView alert in
quarantine. No live execution is enabled. Claude's Discord ingestion work and
all unrelated ChaseInTech configuration are untouched.

Verification: `git diff --check` passed. Initial pytest collection could not
find the local package; rerunning with `PYTHONPATH=libs/tradesync_core` and
`python -m pytest tests/test_tradingview_webhook.py -q` passed all 17 tests.
These are local contract tests, not public ingress acceptance.
