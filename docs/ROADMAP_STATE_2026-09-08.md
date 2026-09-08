# Roadmap state and plan — 8 September 2026

Where TradeSync actually stands, what is outstanding, and the order to do it in.
This supersedes nothing; it records the current picture so the next session does
not have to rediscover it.

Companion: [System map](architecture/SYSTEM_MAP.md) ·
[Failure modes](architecture/FAILURE_MODES.md) ·
[Webhook ingress security](architecture/WEBHOOK_INGRESS_SECURITY.md)

## Decisions taken

| Decision | Date | Consequence |
|---|---|---|
| Stay **private, single operator** | 2026-09-08 | No multi-user auth, no public distribution, no financial-promotion exposure. Discord becomes outbound-only. |
| Wire everything into the **Cockpit**, not Discord | 2026-09-08 | Visualisation, cron jobs and prior systems terminate in TradeSync rather than a chat client. |
| Direction is **separate from suitability** | 2026-09-08 | Catalog 1.2.0. Only `signal_kind: directional` features may set a side. |
| ChaseOS canonical instance is **`chaseos_chaseintech`** | 2026-09-08 | `chaseos_obsidian` is a stub. `CLAUDE.md` corrected. |
| Charts use **TradingView Lightweight Charts** (Apache 2.0) | roadmap Phase 4 | Already implemented for read-only Market Canvas. |

## Done and verified

- Hyperliquid → features → regime → admission → signals → opportunities → Cockpit, end to end.
- `hl_return_1h_pct` derived from venue history; 24h change from `prevDayPx`.
- Direction/suitability split, with hysteresis and duplicate suppression.
- Market Canvas plus a live chart panel on Mission Control.
- **Outcome measurement** — see below. First track record exists.
- Tier A reports a truthful 7/7.
- Redis streams bounded; feature history reads bounded to 250 points.

## The first track record, and why not to trust it yet

| Horizon | Measured | Hit rate | Mean signed return |
|---|---|---|---|
| 15m | 37 | 70.3% | +0.063% |
| 60m | 27 | 11.1% | −0.268% |
| 240m | 0 | pending | pending |

**Do not read this as an edge, or as its absence.** Three reasons:

1. **The observations are not independent.** Most of this sample comes from the
   pre-hysteresis period when the producer minted a fresh opportunity every 60
   seconds for an unchanged market state. Twenty-seven "calls" at 60m may
   represent only two or three genuine market episodes.
2. **The sample spans about two hours of one regime.** BTC was drifting down
   throughout. A short horizon catching bounces while a longer horizon catches
   the trend is exactly what a single downtrend looks like.
3. **The divergence itself is the interesting part**, and it is a hypothesis to
   test, not a finding: if it survives on independent samples across regimes, it
   suggests the signal has a short half-life. That is a claim the fixed-window
   replay is built to settle, and it has not run yet.

The value delivered here is not the number. It is that **the number now exists
and can be argued with.** Every prior tuning decision was unfalsifiable.

## Outstanding, in priority order

### 1. Directional evidence — one feature is not enough

Direction currently rests entirely on `hl_return_1h_pct`. The catalog already
marks two more as directional and both are unavailable:

- `hl_direct_cvd` — taker buy/sell flow. Hyperliquid publishes trades over
  websocket, so this is implementable: subscribe, accumulate signed volume per
  bucket, store as a catalog feature. This is the single highest-value addition
  to signal quality.
- `coinbase_premium_bps` — spot demand confirmation. Needs an admitted Coinbase
  source, and it is the only feature that could ever populate the
  `spot_premium` block, currently structurally empty at weight 0.15.

Until one lands, this system is one indicator wearing a lot of machinery.

### 2. The healthcheck still lies

`/healthz` proves the HTTP server answers, not that data is flowing. This is
exactly what let the system freeze for an hour on 7 September while Docker
reported `Up (healthy)` throughout.

Fix: assert freshness — the newest stored snapshot is younger than N seconds —
and let the container report unhealthy when the job has stopped. Small change,
high operational value, and it closes a failure mode already experienced.

### 3. Fixed-window champion/challenger replay

Still unimplemented, and it is what turns the track record above from an
anecdote into a comparison. Two rulebook versions must be evaluated over the
*same* fixed evidence window, with no look-ahead and no silent retuning.
`tradesync_core` already holds the pure functions this needs.

### 4. Market Canvas maturity

Currently read-only. The roadmap wants:

- Versioned operator drawings stored server-side.
- Alert rules created from the chart.
- Evidence timeline alongside candles (markers exist; the timeline does not).

### 5. Strike Zone Crypto and Pine Script migration

Neither is running on this machine; both are contract-only. Sequencing matters:

1. **Decide what Strike Zone contributes.** Research candidates and performance
   evidence, per the existing contract. It is Tier B: enrichment only, never a
   gate on Tier A, never execution authority.
2. **Stand up the service** at `C:\Users\chaseos\Documents\Projects\strikezone_crypto`
   with a health endpoint, then set `STRIKEZONE_CONNECTOR_URL`. Until a URL is
   configured the inspector correctly reports `contract_only`.
3. **Pine Script arrives by webhook**, which needs ingress — see below.
4. **Quarantine first.** A Pine alert becomes evidence through the catalog with
   provenance and admission gates. It must never write to `signals` directly.

### 6. Webhook ingress (TradingView / Pine)

Analysis is complete in
[Webhook ingress security](architecture/WEBHOOK_INGRESS_SECURITY.md). The
design, in order:

- Cloudflare Tunnel — outbound only, no inbound port, home IP unexposed.
- WAF allowlist of TradingView's four published IPs. This is the strongest
  single control.
- Shared secret **in the JSON body**, because TradingView cannot send custom
  headers.
- Nonce plus timestamp against replay; strict schema; bounded body size.
- Land in a quarantine table with bounded retention.

One endpoint serves every alert: TradingView allows one URL per alert but
unlimited alerts, so each identifies itself in its message body.

### 7. Agent harnesses, ChaseOS gate, Hermes / OpenClaw

All Tier B, none running. `chaseos_chaseintech` contains a `.hermes` directory
and an `06_AGENTS` tree, so the harnesses live there. Same rule as Strike Zone:
they may explain, compare and draft proposals; they may never grant risk,
approval, wallet or execution authority.

### 8. Cron jobs and prior systems into the Cockpit

Recurring jobs currently reporting elsewhere should terminate here. Each needs
a versioned, replay-safe adapter, and none should recreate an existing job or
activate automation merely because a contract exists.

## Known-unresolved carried forward

- `tests/test_core_scorer.py` cannot be collected: a repository-root `main.py`
  shadows the service module.
- Three `test_main.py` failures in `test_preview_action`,
  `test_preview_action_blocked`, `test_execute_action` — pre-existing, unrelated
  to the paper path.
- Every service package is named `app`, so putting two on `PYTHONPATH` at once
  shadows one. Affects test invocation, not runtime.
- `hl_spread_bps` and `hl_buy_impact_5k_bps` are near-constant, so their robust
  z-score is undefined and they never contribute. Honest refusal, but it means
  the liquidity block rests on depth and imbalance alone.
- Coverage ceiling remains 0.55 while three blocks have no admitted feature.

## Boundaries that do not move

`DRY_RUN=true`, `EXECUTION_ENABLED=false`. Hyperliquid is the only venue. No
wallet, no signer, no deployment, no spend without explicit operator approval
and a passed gate. Optional connectors and AI models never grant authority.
