# Local access hardening — 15 September 2026

Branch `claude/security-review`, from `db27305`. This is source and tests only.
- Nothing was deployed, and no container or tunnel was changed.
- No secret was opened.
- Paper mode, `DRY_RUN`, `EXECUTION_ENABLED`, the signer and wallets are untouched.

Findings, severities and evidence are in [the review](../security/2026-09-15_local-access-review.md),
with [the mutating routes](../security/2026-09-15_state-api-mutating-routes.md) and
[the port and tunnel consumers](../security/2026-09-15_local-port-and-tunnel-consumers.md).

## Commits

| Commit | Change | Review |
|---|---|---|
| `79573fb` | Every published host port in `ops/compose.full.yml`, `ops/compose.infra.yml` and `docker-compose.yml` bound to `127.0.0.1` | H1 |
| `eff00e0` | `tradesync_core.state_api_access`: the token variable, its header, minimum length, and where callers find it | H3 |
| `e455e14` | Fleet, output and StrikeZone quant bridges and the edition renderer address `127.0.0.1:8000` and send the token when configured | H1, H3 |
| `6983590` | core-scorer's harness asks, discord-reader's submissions and state-api's own harness calls send the token when configured | H3 |
| `1a5ba55` | state-api access guard (`app/access_guard.py`, served as `app.asgi:app`); compose passes the new variables | H2, H3 |
| `b723731` | Cockpit credential helpers moved out of `api/client.ts`, unchanged | M2 |
| `f19e29b` | Cockpit credentials kept for the browser session, no build-time key, base URL limited to this site or loopback, Operator access panel | M2 |
| `076c19f` | Both Hermes bridges redact job output, errors and prompts before posting | M1 |

## What changes at deploy with no new configuration

- Published ports answer on 127.0.0.1 only.
- A POST, PUT, PATCH or DELETE sent from a web page other than the Cockpit
  (`http://127.0.0.1:3000`, `http://localhost:3000`) or state-api's `/docs` gets 403.
  - Requests without an `Origin` header pass as before: bridges, containers, curl.
  - `POST /webhook/tradingview` is exempt.
  - Routes added on other branches are covered too. `PUT /state/market/horizons/reading-schedule`
    goes through the Cockpit's `apiPut` and passes, like every other Cockpit change.
- The operator token is **not** required. `STATE_API_OPERATOR_TOKEN` is empty unless
  runtime.env sets it.
- Cockpit credentials last for the browser session. A mobile control key left in
  localStorage moves into the session on first use.
- Secret-shaped text in Hermes output, run errors, usage errors and prompt excerpts is posted
  as `[redacted]`. Nothing in the 200 newest stored `chaseos` payloads, 85 job descriptions
  or 7 job errors would have changed.
- Unchanged: whether and how often core-scorer's claim reading, the Discord reader, the
  StrikeZone bridge and every scheduled task run, and what they post. The only additions are
  a header when a token exists and the bridges' default address moving from `localhost` to
  `127.0.0.1`.

## Verification

Python suites use the project venv via `tools/run_tests.py`.

| Suite | `db27305` | This branch (`076c19f`) |
|---|---|---|
| state-api | 284 passed | 306 passed |
| root | 803 passed, 17 deselected, 49 subtests | 833 passed, 17 deselected, 2 warnings, 49 subtests |
| market-data | not run | 141 passed |
| exec-hl-svc | not run | 3 passed |
| signer-svc | not run | 10 passed |
| Cockpit `npm test` | 61 pass | 68 pass, 0 fail |
| Cockpit `npm run build` | not run | passed (`tsc`, then `vite build` in 24.3 s; Vite warns about chunks over 500 kB) |

Merged with `codex/2026-09-01-dashboard-overhaul` at `2a0d748`:
- The `git merge-tree` result (tree `c175491`) was extracted to a scratch copy with its own
  git index. It passes root 933 (1 skipped, 17 deselected, 2 warnings, 49 subtests),
  state-api 336, market-data 160, exec-hl-svc 3 and signer-svc 10.
- Without an index, the three root tests that call `git ls-files` cannot run.
- The merged Cockpit was not rebuilt. No Cockpit file this branch changes is changed there,
  and nothing there uses the exports this branch removed.

Bundle scan (counts only):
- **This branch's `dist/`** (5 files, 1,539,471 bytes): 0 matches for `VITE_API_KEY`,
  `import.meta.env`, `sk-` keys, Slack, GitHub and AWS keys, PEM private keys, Discord tokens
  and webhooks, JWTs, Bearer values, labelled key literals, and an `apiKey` fallback.
  - The 15 `0x` + 64-hex matches are `BigInt("0x…")` elliptic-curve parameters in the wallet
    chunk `index-CNvZpKWw.js`.
- **The served bundle** (`/assets/index-Bftnbqao.js`): 0 on every pattern. Its key fallback
  had compiled to `void 0`.

## Deploy steps

1. Merge into `codex/2026-09-01-dashboard-overhaul`. Against `2a0d748`, which already carries
   ops-refinements, `git merge-tree` reports no conflicts. The only file both branches change
   is `libs/tradesync_core/tradesync_core/job_errors.py`, and the change is identical.
2. Update the main checkout, `E:\Projects\TradeSync\dashboard-overhaul-2026-09-01`. The
   scheduled tasks run the bridges and the edition renderer from there.
3. Recreate the infrastructure so its ports rebind:

   ```powershell
   docker compose `
     --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml `
     up -d postgres redis
   ```

   - Postgres keeps the `tradesync-full_pgdata` volume.
   - Redis keeps its anonymous `/data` volume, which compose carries across a recreate.
   - Never add `-V`, `--renew-anon-volumes` or `down -v`.
4. Rebuild and recreate the changed services, and recreate the rest for their ports:

   ```powershell
   docker compose `
     --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml `
     up -d --build state-api core-scorer discord-reader cockpit-ui
   docker compose `
     --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml `
     up -d market-data fusion-engine
   ```

   Rebuild `cockpit-ui` by whichever path produced the running image: `--build` uses
   `services/cockpit-ui/Dockerfile`; the low-memory path is `npm run build`, then
   `ops/cockpit-prebuilt.Dockerfile`.
5. Leave `cloudflared` and `signer-svc` running. Neither publishes a port, and `cloudflared`
   dials `state-api` by name for each request.

## Post-deploy checks

Run them in order. If check 1 or 2 fails, roll back the ports before anything else.

1. **Loopback only.** `docker port tradesync-full-state-api-1` shows `8000/tcp -> 127.0.0.1:8000`
   and nothing on `0.0.0.0` or `[::]`. Check the same for `cockpit-ui` (3000),
   `core-scorer` (8001), `fusion-engine` (8002), `market-data` (8005), `redis` (6379) and
   `postgres` (5432).
2. **Reachable here.** No container on this engine has published on 127.0.0.1 before, so this
   is the first proof that mirrored WSL networking carries it.
   - `curl.exe -s http://127.0.0.1:8000/healthz` returns `{"ok":true}`.
   - `curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:3000/` returns `200`.
   - `curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:3000/api/state/health` returns `200`.
3. **Policy.** `Invoke-RestMethod http://127.0.0.1:8000/state/access-policy` shows
   `operator_token : disabled` and `origin_check : enforced`.
4. **Guard, without side effects.** `/state/access-probe` has no route, so nothing runs.
   - With a foreign page's origin, the guard answers `403`:

     ```powershell
     curl.exe -s -o NUL -w "%{http_code}\n" -X POST -H "Origin: https://example.invalid" http://127.0.0.1:3000/api/state/access-probe
     ```

   - With the Cockpit's origin through nginx, the request reaches routing: `404`.

     ```powershell
     curl.exe -s -o NUL -w "%{http_code}\n" -X POST -H "Origin: http://127.0.0.1:3000" http://127.0.0.1:3000/api/state/access-probe
     ```

   - With no origin, as the bridges send, it also reaches routing: `404`.

     ```powershell
     curl.exe -s -o NUL -w "%{http_code}\n" -X POST http://127.0.0.1:8000/state/access-probe
     ```

5. **Pine path exempt.** The route answers for itself with `401` and `"accepted":false`,
   before any database write. The guard would have sent 403.

   ```powershell
   curl.exe -s -X POST -H "Origin: https://example.invalid" -H "Content-Type: application/json" -d "{}" http://127.0.0.1:8000/webhook/tradingview
   ```

6. **Cockpit actions through nginx.**
   - Settings → Operator access reads "state-api does not require an operator token" and
     "Changes sent from other web pages are refused".
   - Draw a line on a chart canvas, then delete it. Both succeed.
   - This shows only the probe from check 4:

     ```powershell
     docker logs --since 15m tradesync-full-state-api-1 2>&1 | Select-String "change refused"
     ```

7. **Fleet bridge.** Within five minutes, the snapshot time is later than the deploy, and
   `E:\Projects\TradeSync\dashboard-runtime\logs\hermes_fleet_bridge.log` ends with
   `[FleetBridge] snapshot:`.

   ```powershell
   (Invoke-RestMethod http://127.0.0.1:8000/state/fleet/jobs).snapshot_at
   ```

8. **Other host tools.** `hermes_output_bridge.log`, `strikezone_quant_bridge.log` and
   `thesis_video.log` in the same folder show passes with no HTTP error. New `chaseos` items
   keep reaching Intake as jobs run.
9. **Containers.** Neither command shows lines newer than the deploy.

   ```powershell
   docker logs --since 30m tradesync-full-core-scorer-1 2>&1 | Select-String "ask HTTP"
   docker logs --since 30m tradesync-full-discord-reader-1 2>&1 | Select-String "submit failed"
   ```

10. **Tunnel.**
    - This shows nothing:

      ```powershell
      docker logs --since 30m tradesync-full-cloudflared-1 2>&1 | Select-String "Unable to reach the origin"
      ```

    - A workstation request to `https://tradesync-pine.chaseintech.com/webhook/tradingview`
      still returns Cloudflare 403.
    - The next genuine TradingView alert appears in Intake: in
      `GET /state/quarantine?source=tradingview&limit=1` the newest item is later.

### Rollback

| What to undo | How |
|---|---|
| Ports | Revert `79573fb` in the main checkout, then repeat deploy steps 3 and 4 |
| Origin check only | Add `STATE_API_ALLOWED_ORIGINS=*` to runtime.env and `up -d state-api`. The policy then reports `origin_check : disabled` |
| Whole guard | Revert `1a5ba55`, which restores `app.main:app`, and rebuild state-api |

## Switching on the operator token

Off by default. Every caller in this repository already sends it once it exists. No Hermes
script calls state-api (checked 15 September); one added later must send `X-Operator-Token`.
Never put the token on a command line or in a URL.

1. Generate it and store it without displaying it (Windows PowerShell 5.1). The result is 48
   URL-safe characters.

   ```powershell
   $bytes = New-Object byte[] 36
   [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
   Set-Clipboard -Value ([Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_'))
   powershell -ExecutionPolicy Bypass -File tools\set-runtime-secret.ps1 -Name STATE_API_OPERATOR_TOKEN
   Set-Clipboard -Value ' '
   ```

   Paste into the prompt that opens before the last line runs.
2. Recreate the three containers that read it. No rebuild is needed.

   ```powershell
   docker compose `
     --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml `
     up -d state-api core-scorer discord-reader
   ```

3. **Host tools** need nothing. On their next run they read the same line from runtime.env.
   `TRADESYNC_RUNTIME_ENV` overrides the file path.
4. **Cockpit**, once per browser session:
   - open Settings → Operator access;
   - run `tools\copy-runtime-secret.ps1 -Name STATE_API_OPERATOR_TOKEN`;
   - paste the token and choose Keep;
   - clear the clipboard.
5. **Check.**
   - `/state/access-policy` shows `operator_token : required`.
   - A POST to `/state/access-probe` with no token returns `401`.
   - A Cockpit change succeeds once the token is kept.
   - The next fleet snapshot time advances.
   - Apart from your probe, the state-api log has no `change refused` lines.
6. **Switch off** by removing the line from runtime.env, or leaving it empty, and repeating
   step 2.

A token shorter than 32 characters is treated as a mistake: state-api refuses every change
and says why.

## Still open

In order of what to do next (details in the review):
1. Switch the operator token on (H3).
2. Give `cloudflared` a network shared only with state-api (M3).
3. Give the signer a caller secret and its own network before any key is loaded (M4).
4. Host allowlist against DNS rebinding (L1).
5. Wire the receiver's own TradingView IP check (L2).
6. Edge rate limit (L3).
7. One sanitising 500 handler (L4).
8. Body limits (L5).
9. exec-hl-svc caller authentication (L6).
10. Redact Discord messages at ingest (L7).
11. `trust_env=False` for the harness client (L8).
12. Point the development commands at `app.asgi:app`. `run_dev.py:18` and
    `docs/RUNBOOKS.md:79` still start `app.main:app`, which has no guard; the container is
    unaffected.

`docs/README.md` is not updated here, to avoid colliding with the parallel branches; add the
index line at merge.
