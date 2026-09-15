# Local access security review — 15 September 2026

Branch `claude/security-review`, from `codex/2026-09-01-dashboard-overhaul` at `db27305`.
Line numbers refer to `db27305` unless marked otherwise.

Related documents:
- [State-api mutating routes](2026-09-15_state-api-mutating-routes.md): every route that changes state.
- [Port and tunnel consumers](2026-09-15_local-port-and-tunnel-consumers.md): who uses each port, and the tunnel as checked.
- [The change record](../changes/2026-09-15_local-access-hardening.md): commits, tests, deploy steps, and how to switch on the operator token.

## The two questions

**Can the Cockpit or the API be reached from beyond this Windows machine?** Before this
branch every compose file asked Docker to publish its ports on all interfaces (`0.0.0.0`
and `[::]`). Whether another device could connect then rested on firewall layers TradeSync
does not control (H1). Every published port is now bound to `127.0.0.1`. Remote access, if
it is ever wanted, needs its own authenticated path; widening a binding is not that path.

**Does the Cloudflare tunnel publish the dashboard?** No. It routes one host and path,
`tradesync-pine.chaseintech.com` + `^/webhook/tradingview$`, to `state-api:8000`. Every other
request gets a 404 from `cloudflared`, behind an edge WAF that blocks every source except
TradingView's four IPs. Nothing reaches `cockpit-ui` or any other state-api route. The
connector does share the compose network with every service (M3).

## Method

Read-only: source and compose files; `docker inspect`, `docker port` and `docker network
inspect` with selected fields; GET requests to 127.0.0.1:8000 and :3000; scheduled tasks,
listeners and firewall state; `.wslconfig`; the Hermes scripts directory. Nothing was
deployed. Secrets were checked for presence only: no `.env`, `runtime.env`, credential JSON
or token was opened. Logs, stored payloads and bundles were scanned for secret-shaped
strings, printing counts only.

## Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| H1 | High | Every published port listened on all interfaces | Fixed |
| H2 | High | Any web page open on this machine could change state through 127.0.0.1 | Fixed |
| H3 | High | State-changing routes authorise nothing | Mitigated; open until the operator token is on |
| M1 | Medium | Hermes job output, run errors and prompts stored unredacted | Fixed |
| M2 | Medium | Cockpit credentials in localStorage, with a build-time key fallback | Fixed |
| M3 | Medium | The tunnel connector shares a network with every service | Open |
| M4 | Medium | The signer accepts any caller on that network | Open |
| L1 | Low | No Host check: a DNS-rebinding page can read the API | Open |
| L2 | Low | The receiver's own TradingView IP check is not wired | Open |
| L3 | Low | No edge rate limit on the webhook host | Open |
| L4 | Low | Raw exception text in error responses | Open |
| L5 | Low | No request body limits outside the webhook | Open |
| L6 | Low | exec-hl-svc's order route is unauthenticated | Exposure fixed; authentication open |
| L7 | Low | Discord messages stored unredacted | Open |
| L8 | Low | The harness client honours proxy variables | Open |
| I1 | Info | Execution mode and kill switches are browser preferences | Accepted |
| I2 | Info | Operator names are self-asserted | Accepted |
| I3 | Info | Wallet pairing is address-only and in memory | No change needed |
| I4 | Info | The 12 September FRED log fix holds; nothing prints environment values | Verified |

### H1 — every published port listened on all interfaces (fixed)

- **Compose files.** `ops/compose.full.yml:25,40,51,101,117,125,155,182,196,227` publishes
  postgres, redis, qdrant, state-api, core-scorer, exec-hl-svc, ingest-gateway,
  fusion-engine, cockpit-ui and market-data. `ops/compose.infra.yml:12,26,37` and
  `docker-compose.yml:13,27,38,80,100` did the same.
- **Live bindings** (`docker port`, 15 September): 8000, 3000, 8001, 8002, 8005, 6379 and
  5432 were each bound on `0.0.0.0` and `[::]`.
- **What those ports expose.** Redis runs without a password
  (`ops/compose.market-command.yml:22-31`); state-api accepts changes unauthenticated (H3);
  nginx proxies the whole of state-api under `/api/` (`services/cockpit-ui/nginx.conf:16-27`).
- **What stood between them and the Wi-Fi network** (category Public):
  - No Windows process listens on these ports (`netstat`, `Get-NetTCPConnection`), so traffic
    reaches Docker through WSL mirrored networking (`networkingMode=mirrored`).
  - The WSL VM's Hyper-V firewall defaults inbound traffic to Block.
  - An enabled Windows Firewall rule, `Docker Desktop Backend`, allows any TCP or UDP port on
    the Public profile.
  - Connecting from this host to its own Wi-Fi address failed on 8000, 3000, 6379 and 5432.
    Mirrored mode without `hostAddressLoopback` refuses that anyway, so the test decides
    nothing.
- **Fix.** Every published port in the three files is now `127.0.0.1:…`.
  `tests/test_local_port_bindings.py` fails for any wider binding and checks that the tunnel
  and the signer publish nothing. No consumer needs another interface (consumers document).
  The host bridges now default to `127.0.0.1` rather than `localhost`.
- **Deploy risk.** No container on this engine publishes on 127.0.0.1 yet, so a
  loopback-only port through mirrored networking is first exercised at deploy. The first
  post-deploy check covers it.

### H2 — cross-site changes through 127.0.0.1 (fixed)

- **Why a page could do this.**
  - state-api has no CORS middleware (`services/state-api/app/main.py:403-410`). That stops a
    page reading responses, not sending changes.
  - FastAPI 0.115.2 parses a body with no Content-Type as JSON. Measured 15 September: a
    model-validated POST answered 200 with no Content-Type, and 422 with `text/plain` or
    form encoding.
  - `fetch(url, {method: 'POST', mode: 'no-cors', body: new Blob([json])})` sends exactly
    that, with no preflight.
- **What a page could send.**
  - `POST /state/paper-control` with `entries_paused: false` (`managed_paper.py:84`).
  - A fleet directive `run_now`, `set_deliver` or `set_workdir` (`fleet.py:182`).
  - A learning adoption with `confirm: true` (`learning_actions.py:50`).
  - Loopback binding does not help, because the page runs on this machine. Chromium's
    local-network prompt helps only where it has shipped.
- **Fix: `services/state-api/app/access_guard.py`**, served as `app.asgi:app`.
  - A POST, PUT, PATCH or DELETE whose `Origin` is not `http://127.0.0.1:3000`,
    `http://localhost:3000` or state-api's own `/docs` origin is refused with 403 before routing.
  - Requests with no `Origin` (bridges, containers, curl) pass.
  - `STATE_API_ALLOWED_ORIGINS` adds origins; `*` switches the check off as a rollback lever.
  - `/webhook/tradingview` is exempt.
  - Tests: `services/state-api/tests/test_access_guard.py`.
- **No CORS middleware was added.** The Cockpit reaches state-api same-origin through nginx
  and needs none, and adding one could only widen access. Reads stay same-origin, and
  changes are held to the Cockpit's origins.

### H3 — state-changing routes authorise nothing (mitigated, open)

- **Before this branch** only two things were authorised:
  - the mobile controls, through `X-API-Key` against `MOBILE_ALERTS_CONTROL_KEY`
    (`mobile_alerts.py:29-33`; unset on 15 September);
  - the webhook, through its body secret (`tradingview_webhook.py:138-146`).
- **Everything else was open to any caller that reached the port.** All routes are in the
  routes document. The most consequential:
  - resume paper entries (`managed_paper.py:84`);
  - change the paper scorer's weights (`learning_actions.py:50,68,86`);
  - pause, run, re-schedule or redirect Hermes jobs, applied at once through the gateway
    (`fleet.py:182,196-198`);
  - rewrite a job's working directory, free text the bridge writes into `jobs.json`
    (`fleet_rules.py:58-61`, `tools/hermes_fleet_bridge.py:173-176`);
  - spend Hermes model time (`main.py:2524`);
  - write and promote quarantine evidence (`main.py:1299,1896`).
- **This branch.**
  - Every mutating route passes the origin check (H2).
  - With `STATE_API_OPERATOR_TOKEN` set, every change must also carry `X-Operator-Token`,
    compared in constant time. A token set shorter than 32 characters refuses all changes.
  - The guard wraps the whole application, so routes other branches add are covered too.
  - Every in-repo caller already sends the token when one is configured.
  - The token is off by default so nothing breaks at deploy. Until the operator switches it
    on, any process on this machine can still make these changes.

### M1 — Hermes output stored unredacted (fixed)

- **Before.** Knowledge Intake renders stored payloads, and these went as read:
  - each output file's content (`tools/hermes_output_bridge.py:147`);
  - the prompt excerpt, run errors and usage errors (`tools/hermes_fleet_bridge.py:74`,
    `:121`, `:142`).
  Only `last_error` and `last_delivery_error` were redacted (`:94`).
- **Live data, 15 September.** None of the 200 newest `chaseos` quarantine payloads, 85 job
  descriptions or 7 job errors matched a `redact` pattern.
- **Fix.** Both bridges call `tradesync_core.job_errors.redact` before posting.
  - Output content and usage errors are kept whole (`limit=None`).
  - Run errors are cut at 500 and descriptions at 400, as before.
  - The `limit` parameter matches `claude/ops-refinements` byte for byte.
  - Test: `tests/test_hermes_bridges_redaction.py` runs both bridges on a temporary Hermes
    tree and shows token-, key- and webhook-shaped strings never reach the request, while
    the text around them survives.
- **Known cost.** `redact` also replaces a word of eight or more characters after `token`,
  `secret`, `password` or `bearer` in prose: "token distribution" becomes "token [redacted]".
  None of the stored payloads above matched.

### M2 — Cockpit credentials (fixed)

- **Before.**
  - The base URL (`services/cockpit-ui/src/api/client.ts:3-9`) and the key (`:102-108`) lived
    in localStorage.
  - The key fell back to `import.meta.env.VITE_API_KEY` (`:11-13`).
  - Settings read localStorage directly (`src/pages/Settings.tsx:25`) and labelled the key
    "Required for /actions/* endpoints" (`src/components/settings/ApiConfiguration.tsx:58`).
    Nothing checks that.
- **What servers check with that key.**
  - state-api: only the mobile controls (`mobile_alerts.py:32`). `/actions/preview` and
    `/actions/execute` check nothing (`main.py:800,1024`).
  - exec-hl-svc: nothing (`services/exec-hl-svc/app/main.py:148`).
  - signer-svc: never checks its caller (`services/signer-svc/app/main.py:131`).
- **The served bundle.** `/assets/index-Bftnbqao.js` (942,475 bytes) compiled the fallback to
  `localStorage.getItem("apiKey")||void 0||null`, so no key was built in.
  - Neither Cockpit directory has a `.env*` file, and `VITE_API_KEY` is unset in the build
    shell.
  - The Docker build excludes `.env*` (`services/cockpit-ui/.dockerignore`), but the prebuilt
    path packages a local `dist/` (`ops/cockpit-prebuilt.Dockerfile:6`). A local `.env` key
    would have shipped.
  - A stored `apiBaseUrl` could also have sent the key to any host.
- **Fix: `src/api/credentials.ts`.**
  - The operator token and the mobile control key live in sessionStorage.
  - A key left in localStorage moves into the session and is deleted.
  - Nothing is read from a build-time variable.
  - Only a base URL on this site or a loopback address is honoured.
  - Settings gains an Operator access panel showing the server's policy, with a session-only
    token field.
  - Tests: `tests/api-credentials.test.mjs`, including a check that no source reads
    `import.meta.env` beyond Vite's build flags. The build scan is in the change record.
- **Cost.** Credentials are entered again in each new browser session.

### M3 — the tunnel shares a network with every service (open)

`ops/compose.ingress.yml:39-41` places `cloudflared` on `default`. `docker network inspect
tradesync-full_default` shows every service there, including postgres, redis (no password),
signer-svc and cockpit-ui.

The ingress rules limit what the tunnel routes; the consumers document has the rules,
container and WAF as checked. But a compromised connector, or a config later managed from
the Cloudflare dashboard, could reach every one of those services.

Recommendation: an internal network holding only `cloudflared` and `state-api`. This is a
tunnel change and needs a live Pine re-acceptance, so it is not made here.

### M4 — the signer accepts any caller on that network (open)

- `/sign` checks `SIGNING_ENABLED`, key presence, request shape and single use, never who is
  calling (`services/signer-svc/app/main.py:131-192`).
- `ops/compose.signer.yml:41-44` relies on the network for isolation, and that network
  includes the internet-facing `cloudflared` and the Discord reader.
- On 15 September `GET /state/execution/signer-status` reported `key_loaded: false` and
  `signing_enabled: false`.
- Before any key is loaded: a network shared only with state-api, plus a caller secret.
  Signer behaviour is outside this change.

### Low

- **L1 — DNS rebinding reads.**
  - There is no Host check (`main.py:403-410`). A page on a hostname re-resolved to
    127.0.0.1 is same-origin to itself, so it can read every GET: paper positions, job
    descriptions, quarantine payloads, the watched wallet address.
  - Changes stay refused by the origin check.
  - Fix later: `TrustedHostMiddleware` for `127.0.0.1`, `localhost`, `state-api` and
    `tradesync-pine.chaseintech.com`, once every caller's Host header is confirmed (nginx
    forwards `$host`). A wrong list would break the Cockpit or the webhook, so it is not
    switched on here.
- **L2 — receiver IP check unwired.**
  - `tradingview_webhook.py:164-171` defines `is_allowed_source`; the route
    (`main.py:1956-2025`) never calls it.
  - `ops/ingress/waf-allowlist.md:25-29` and
    `docs/HANDOVER_2026-09-12_PINE_INGRESS_FOR_CODEX.md:21,91` describe it as a live second
    layer.
  - Still in force: the edge WAF, the constant-time body secret (`tradingview_webhook.py:141`),
    the 16 KB bound (`:43`) and digest dedupe.
  - Wiring it needs `CF-Connecting-IP` handling and a live Pine re-acceptance.
- **L3 — no edge rate limit.** `docs/architecture/WEBHOOK_INGRESS_SECURITY.md:86` names it as
  layer 2; the Cloudflare profile records only the block rule.
- **L4 — raw exception text.**
  - 33 handlers return `str(e)`, for example:
    - `main.py:1272`, an httpx error that names `http://market-data:8005/…`;
    - `main.py:1345` and `:2023`, database errors;
    - `canvas_drawings.py:105` and `opportunities_routes.py:90`.
  - `agent_connector.py:86` and `hermes_link.py:136` return the harness URL.
  - No secret was seen in any of them. Fix later with one sanitising 500 handler; these
    routes are being edited on other branches.
- **L5 — no body limits.**
  - Only the webhook bounds its body (`tradingview_webhook.py:43,92`).
  - `FleetSnapshot` and `LabIngest` take unbounded lists (`fleet_models.py:57-62`,
    `strikezone_ingest.py:64-67`).
  - After H1 only a local caller can send one.
- **L6 — exec-hl-svc.**
  - `/exec/hl/order` (`services/exec-hl-svc/app/main.py:148`) checks no caller and fails
    closed while `EXECUTION_ENABLED=false` (`:154-166`).
  - It was not running (profile `paper-exec`). Its port 8004 is now loopback-only; caller
    authentication is open.
- **L7 — Discord messages.**
  - discord-reader posts messages as read (`services/discord-reader/app/main.py:109-116`),
    the same class as M1.
  - None of the 200 newest stored Discord payloads matched a `redact` pattern.
  - Not changed here, because core-scorer's claim reading quotes those posts verbatim.
- **L8 — harness proxy variables.**
  - `agent_connector.py:74,118` open httpx clients without `trust_env=False` (unlike
    `hermes_link.py:91`). A proxy variable in the container would carry the Bearer
    `AGENT_HARNESS_KEY`; none is set.
  - The key is read once (`:41`), sent only in the Authorization header (`:44-45`) and never
    logged.
  - Left unchanged at the operator's request that the harness path stay as it is.

### Info

- **I1 — mode and kill switches.**
  - `src/context/ExecutionContext.tsx:22,39-69` keeps them in localStorage, and
    `src/components/PreviewPanel.tsx:18-31` uses them to enable Execute.
  - The server re-checks risk and the execution gate (`main.py:1024-1110`,
    `EXECUTION_ENABLED=false`). These switches stop nothing server-side; the real entry pause
    is `POST /state/paper-control`.
  - Accepted; relabelling them is a UI decision.
- **I2 — operator names.**
  - `src/components/learning/format.ts:55-72` remembers the operator's name.
  - `decided_by`, `reviewed_by` and `requested_by` are free text (`learning_actions.py:21-24`,
    `main.py:1412-1415`, `fleet_models.py:72`). They are attribution, not identity.
  - Accepted.
- **I3 — wallet pairing.**
  - `src/wallets/pairingPolicy.ts:1-30` requests no signing methods, accepts only `eip155:1`
    addresses and keeps relay session data in memory.
  - `src/components/WalletPairing.tsx:17,39` takes the public project ID from the operator,
    with telemetry off.
- **I4 — secrets in logs.**
  - httpx and httpcore log at WARNING (`main.py:80-84`, `event_outlook.py:36-37`), and FRED
    failures are logged by exception type only (`context_feed.py:130,234`).
  - 72 hours of container logs held 0 `api_key=` values, 0 FRED URLs and 0 Bearer tokens.
    Lines scanned: state-api 3,905, market-data 85,241, core-scorer 5,765, discord-reader
    45,618, cloudflared 1,176, cockpit-ui 2,922.
  - No code in `services`, `libs`, `tools` or `ops` prints an environment value.
