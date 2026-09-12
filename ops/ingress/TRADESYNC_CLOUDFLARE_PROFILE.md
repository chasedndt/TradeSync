# TradeSync Cloudflare profile

This is the canonical, non-secret identity for the private TradeSync Pine
ingress. Cloudflare does not have a separate "project profile" object; this
profile names the related tunnel, DNS route, WAF rule, and local connector as
one governed unit.

| Field | Value |
|---|---|
| Profile name | TradeSync Pine Ingress |
| Cloudflare zone | `chaseintech.com` |
| Public hostname | `tradesync-pine.chaseintech.com` |
| Tunnel name | `tradesync-webhook` |
| Tunnel ID | `15945b2a-e022-4374-886f-e58a22291609` |
| Public path | `POST /webhook/tradingview` only |
| Internal origin | `http://state-api:8000` |
| Source trust | TradingView evidence, quarantine-only, no execution authority |
| WAF rule name | TradeSync Pine - block non-TradingView sources |

## Current activation state

- Tunnel object: created.
- DNS CNAME: created.
- Local ingress rules: configured and validated.
- Tunnel connector: running and healthy with four registered edge connections.
- WAF allowlist: enabled and read back from Cloudflare.
- `TRADINGVIEW_WEBHOOK_SECRET`: configured and loaded by the healthy State API.
- First genuine TradingView receipt: accepted and rendered in Knowledge Intake.

## Mandatory WAF rule

In Cloudflare, select `chaseintech.com`, then **Security > WAF > Custom
rules**. Create the first rule in the custom ruleset:

- Name: `TradeSync Pine - block non-TradingView sources`
- Action: **Block**
- Expression:

```text
(http.host eq "tradesync-pine.chaseintech.com"
 and not ip.src in {52.89.214.238 34.212.75.30 54.218.53.128 52.32.178.7})
```

The rule is enabled. The Free plan supports zone-level custom rules, so a paid
Cloudflare upgrade was not required. State API and the separate `cloudflared`
connector were then recreated without restarting unrelated application
services.

## Acceptance boundary

Completion requires all of the following: four registered edge connections,
a workstation request blocked by Cloudflare, all non-webhook paths unavailable,
and one real TradingView alert stored in quarantine and visible in Intake.
Neither DNS creation nor a healthy container alone proves acceptance.

## Verified readback — 2026-09-12

- Cloudflare returned the enabled exact-host WAF rule after creation/update.
- The tunnel registered four QUIC connections at London edge locations.
- Public workstation requests to the webhook, `/state/health`, and `/` each
  returned Cloudflare `403` with a Ray ID.
- Local `http://127.0.0.1:8000/state/health` remained `200`.
- The State API container loaded a non-empty 64-character webhook secret.
- `cloudflared` ingress validation passed; only the webhook path matches the
  origin rule and other paths match the terminal `http_status:404` rule.

End-to-end acceptance completed with receipt
`3f010cb5-7c27-4587-a860-f7f38f6d27f3` at
`2026-09-12T21:54:29.09368+01:00`. TradingView generated it from the licensed
`StrikeZone — Universal EMA 21/55 Cross Alerts (v6)` indicator on BTCUSD 15m.
The one-time acceptance condition was `EMA Fast > 0`; its submitted content
rendered in Knowledge Intake as source `tradingview`, schema
`tradingview_alert_v1`, awaiting review. The secret was absent from the stored
and rendered payload.

For future provider alerts, use
`tools/copy-runtime-secret.ps1 -Name TRADINGVIEW_WEBHOOK_SECRET` to copy the
secret without displaying it, then clear the clipboard after pasting.
