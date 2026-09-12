# Handover to Codex: Pine ingress via Cloudflare Tunnel (slice 7)

Date: 2026-09-12
Branch: `codex/2026-09-01-dashboard-overhaul` (pushed with this document)
Operator decision (2026-09-12): the public route for TradingView / Strike Zone
Pine alerts is a **Cloudflare Tunnel**, implemented by Codex through its
wrangler connection to the operator's Cloudflare account. Claude does not
hold and must not handle Cloudflare credentials, tunnel credentials, or the
webhook secret value.

**The tunnel is now the only blocker for the first Pine alert to land.**
Everything on the receiving side is built, tested and deployed. This document
says exactly what exists, exactly what remains, and how to prove it worked.

---

## 1. What is already built (do not rebuild)

| Piece | Where | State |
|---|---|---|
| Receiver `POST /webhook/tradingview` | `services/state-api/app/main.py` (~line 2126) | Deployed. Refuses with 503 while `TRADINGVIEW_WEBHOOK_SECRET` is unset. Authenticates the secret in the JSON body, checks the four TradingView source IPs, bounds the body at 16 KB, dedups by content digest, writes to `quarantine_intake` as **untrusted material**. Never a signal. |
| Alert contract | `libs/tradesync_core/tradesync_core/tradingview_webhook.py` | `tradingview_alert_v1`. Required JSON fields: `secret`, `indicator`, `ticker`. TradingView cannot send headers, so the secret travels in the body. Plain-text alerts are refused as unauthenticatable. |
| Pine → paper candidate adapter | `libs/tradesync_core/tradesync_core/strike_zone.py` | Turns an authenticated receipt into `trade_candidate_v1`. Every authority field is a constant written by the adapter; a receipt that tries to set one is refused. |
| Quarantine review surface | Cockpit `/intake`, `GET /state/quarantine` | Deployed. |
| Tunnel config template | `ops/ingress/cloudflared.config.template.yml` | Exposes exactly one path (`^/webhook/tradingview$`) to `http://state-api:8000`; everything else 404 at the edge. 3 s connect timeout to match TradingView's abandon time. |
| Tunnel compose file | `ops/compose.ingress.yml` | Separate file on purpose: bringing it up is an explicit act. Mounts `ops/ingress` read-only; publishes no ports; outbound only. |
| WAF rule text | `ops/ingress/waf-allowlist.md` | One Custom Rule: block unless `ip.src` in the four TradingView egress IPs. Same list the receiver checks; `tests/test_tradingview_webhook.py` pins the pair. |
| Security analysis | `docs/architecture/WEBHOOK_INGRESS_SECURITY.md` | Read it before exposing anything. The threat is evidence poisoning, not theft. |
| Secrets hygiene | `ops/ingress/.gitignore` | Excludes `cloudflared.config.yml` and `*.json` (tunnel credentials). |
| Measurement that will judge Pine | slices 5 and 6 | Once Pine indicators are catalogued as context-only features, their entry readings are recorded and scored on the evidence cards; the thesis shows what each earned. Nothing scores until it earns a weight and the operator admits it. |

---

## 2. What Codex does (in order)

Wrangler authenticates the account; the tunnel itself is a `cloudflared`
object. Either the `cloudflared` CLI logged into the same account or the
Cloudflare API (`/accounts/{id}/cfd_tunnel`) creates it.

1. **Create the tunnel** on the operator's account, named `tradesync-webhook`.
   Keep the credentials JSON; it goes in `ops/ingress/<tunnel-id>.json` on the
   workstation only (gitignored).
2. **Route a hostname** to it (a CNAME on a zone the operator owns, e.g.
   `hooks.<zone>`). One hostname, one path.
3. **Add the WAF Custom Rule** from `ops/ingress/waf-allowlist.md`, on that
   zone, ordered before anything permissive. This is layer 1 and is not
   optional.
4. **Fill the config**: copy `ops/ingress/cloudflared.config.template.yml` to
   `ops/ingress/cloudflared.config.yml`, replace the tunnel id (twice) and the
   hostname (twice). Do not commit the filled copy.
5. **Set the shared secret**: the operator adds
   `TRADINGVIEW_WEBHOOK_SECRET=<long random value>` to
   `E:\Projects\TradeSync\dashboard-runtime\runtime.env`. The receiver stays
   at 503 until it exists. Recreate `state-api` so it reads the new env.
6. **Bring the tunnel up** with the command at the top of
   `ops/compose.ingress.yml` (the bounded profile plus `-f ops\compose.ingress.yml up -d cloudflared`).
7. **Configure one TradingView alert** on a Strike Zone indicator with
   webhook URL `https://<hostname>/webhook/tradingview` and a JSON message:

   ```json
   {"secret": "<the same value>", "indicator": "<indicator name>", "ticker": "{{ticker}}",
    "exchange": "{{exchange}}", "interval": "{{interval}}", "time": "{{timenow}}",
    "close": "{{close}}", "direction": "<long|short|none>", "note": "<what fired>"}
   ```

   Only `secret`, `indicator` and `ticker` are required; the rest is evidence
   that is stored verbatim in quarantine.

---

## 3. Proof it worked (the gate for slice 7)

- `docker logs tradesync-full-cloudflared-1` shows the tunnel registered and
  connected (four edge connections).
- A request from anywhere *not* on the four-IP list is blocked at the edge
  (curl from the workstation should get a Cloudflare block page, not a
  state-api response).
- The first real alert appears at `GET /state/quarantine` with
  `source = 'tradingview'`, and on the Cockpit `/intake` page, with
  provenance and the adapter's constant authority fields. That is the gate:
  "first Pine alert lands in quarantine with provenance."
- `GET /state/health` unchanged; `/state/*` is not reachable through the
  hostname (the edge returns 404 for any other path).

---

## 4. What must not change

- Only `/webhook/tradingview` is exposed. Adding a path is a deliberate edit
  to the ingress list and to the security doc, not a side effect.
- The receiver keeps its own IP check and its own secret check even though
  the edge does both. Neither layer is load-bearing alone.
- Pine alerts are evidence, never signals. No alert can set authority,
  direction weight, or execution state. That is enforced in
  `strike_zone.py` and re-checked in `paper_ledger._validate_candidate`.
- Hermes remains paused (no compute); nothing here involves it.

---

## 5. After the first alert lands (Claude resumes)

Each Strike Zone indicator becomes a catalogued **context-only** feature
(`scoring_eligible: false`) in `config/features/market-feature-catalog-v1.json`
with a bumped version and a change record. Its firings are recorded against
opportunities at entry (`opportunity_entry_features`, slice 5), scored on the
evidence cards in both polarities, and shown on the thesis's confirmation
stack. It earns a scoring weight only through measured skill, and only by
operator decision. Then slice 8: the video edition of the thesis, delivered
to a private Discord channel.

---

## 6. State of the tree at handover

Commits since the last handover (`docs/HANDOVER_2026-09-09_FULL_STATE.md`):

- `4db3286` measurement core (entry regimes, counted independence, three verdicts)
- `75f16c9` slice 3: skill gate wired into the job, API and Regime Lab
- `2105a3f` slice 5: entry readings recorded, evidence cards, earned weights
- `bbd9597` slice 6: the Thesis page
- plus slices 1–2, the ten-symbol universe, GDELT news tone, Binance
  cross-venue, the economic-events strip, and the FRED key wiring
  (`docs/changes/2026-09-12_*.md`)

All test suites green at handover: root 516, state-api 76, market-data 114,
exec-hl-svc 3, signer-svc 10. Bounded Docker profile healthy; ten symbols
LIVE; the entry-feature backlog was draining at 120 opportunities per five
minutes.
