# Port and tunnel consumers — 15 September 2026

Who reaches TradeSync's published ports and its Cloudflare tunnel. Checked read-only on
15 September 2026, to decide whether every port could be bound to 127.0.0.1. Findings: H1
and M3 in [the review](2026-09-15_local-access-review.md). Line numbers refer to `db27305`.

## Published ports

| Consumer | Address | Evidence |
|---|---|---|
| Scheduled tasks: fleet, output and StrikeZone quant bridges, edition renderer (pythonw, from the main checkout) | `localhost:8000` by default, now `127.0.0.1:8000` | `tools/hermes_fleet_bridge.py:52`, `hermes_output_bridge.py:54`, `strikezone_quant_bridge.py:56`, `thesis_video.py:43`. The task actions set no URL, and `STATE_API_URL` is unset at user and machine scope |
| Desktop shortcut, browser QA scripts | `127.0.0.1:3000` | `tools/create-desktop-shortcut.ps1:38`, `tools/qa_*.cjs` |
| Cockpit nginx, discord-reader, core-scorer, cloudflared | `state-api:8000` on the compose network | `services/cockpit-ui/nginx.conf:17`, `ops/compose.market-command.yml:225`, `services/core-scorer/app/claims_harness.py:29` |
| state-api's edition briefing and timeframe readings | `localhost:8000` inside its own container | `services/state-api/app/editions.py:43`, `horizon_reading.py:28` |
| Hermes in WSL (mirrored networking) | no TradeSync port or host address in `hermes-home/scripts` (the 29 matching files matched on path names only) | search of 15 September |
| state-api to Hermes | `host.docker.internal:8642`, outbound | unaffected |

No consumer on another interface was found, so no port kept a wider binding.

**Why the bridges moved from `localhost` to `127.0.0.1`.** Windows resolves `localhost` to
`::1` first. Against an IPv4-only listener, every new connection waited about two seconds:
2,058 to 2,107 ms, against 66 to 87 ms for `127.0.0.1`.

**Why source addresses prove nothing.** Docker NATs published ports, so state-api's access
log cannot tell a local caller from a forwarded one:
- the host bridges arrive from the compose gateway, 172.18.0.1, as anything forwarded would;
- discord-reader arrives from 172.18.0.2, core-scorer from .6, Cockpit nginx from .11.

The access guard therefore ignores addresses.

## Cloudflare tunnel

- **Filled config** (`ops/ingress/cloudflared.config.yml`, gitignored; structural keys only):
  - one rule: hostname `tradesync-pine.chaseintech.com`, path `^/webhook/tradingview$`,
    service `http://state-api:8000`, with `connectTimeout 3s`, `keepAliveConnections 0`,
    `noTLSVerify false` and `httpHostHeader`;
  - then `service: http_status:404`;
  - no other keys, no `warp-routing`.
- **Container.**
  - Runs `cloudflared --no-autoupdate tunnel --config /etc/cloudflared/cloudflared.config.yml run`.
  - No port bindings; `ops/ingress` mounted read-only; environment names only `PATH` and
    `SSL_CERT_FILE`.
  - Four QUIC edge connections were registered at 17:35 UTC on 14 September.
  - Its metrics server listens on `[::]:20241` inside the container.
- **Edge WAF** (`ops/ingress/TRADESYNC_CLOUDFLARE_PROFILE.md:30-47`,
  `docs/changes/2026-09-12_pine-ingress-preflight.md:35-45`):
  - Rule "TradeSync Pine - block non-TradingView sources": Block when
    `http.host eq "tradesync-pine.chaseintech.com"` and `ip.src` is not in
    `{52.89.214.238 34.212.75.30 54.218.53.128 52.32.178.7}`.
  - Readback on 12 September: workstation requests to the webhook, `/state/health` and `/`
    returned Cloudflare 403.
- **Git history.** Neither the tunnel credential nor the filled config was ever committed
  (`git log --all` on both paths).
- **This branch.** The webhook path is exempt from the new guard and otherwise unchanged. The
  connector still shares the compose network with every service (M3).
