AGENT_INTERFACE.md

Purpose. Contract for every domain agent in TradeSync (tech/structure, funding/OI, sentiment, rotation/macro, future kits). Agents consume normalized Events and emit typed Signals with calibrated confidence and full provenance. This spec also defines streams, APIs, error model, and persistence guarantees.

Version: v0.1
Domains: events, signals, opportunities, decisions, exec_orders, exposures, regimes, calibration_params, vectors
Transports: HTTP(S) + Redis Streams (or Kafka) + Postgres + Qdrant

0) Conventions

Time: ISO-8601 UTC, e.g. 2025-11-05T22:14:03Z.

IDs: uuid4 unless venue mandates otherwise.

Symbols: Uppercase (e.g., BTCUSDT, ETHBTC, SOL-USD-PERP). Venue symbol mapping handled in executors.

Timeframes (canonical): 1m|5m|15m|30m|1h|2h|4h|8h|1d.

Inputs may arrive as aliases (H2, 120, 480, etc.); ingest normalizes to canonical strings above.

Floats: Decimals; no NaN/Inf.

Booleans: true|false.

Enums: Lowercase strings as listed here.

Versioned payloads: Each top-level object has "v":"0.1".

1) Topics & Streams

Default transport: Redis Streams (swap to Kafka with the same topic names).

x:events.raw           # raw TV/yt/metrics before normalization
x:events.norm          # normalized events (single canonical shape)
x:signals.tech         # technical agent signals
x:signals.funding      # funding/OI/liquidity agent signals
x:signals.sentiment    # narrative from YT/TV ideas (RAG)
x:signals.rotation     # cross-asset rotation signals
x:signals.*            # wildcard (fusion consumes all)
x:opps                 # optional mirror of fused opportunities
x:exec.orders          # async exec logs (requests + results)


Delivery: at-least-once. Consumers must be idempotent (see event.hash and agent-side dedupe).

2) Agent Lifecycle

Init – load config, thresholds, and model weights from config/agents/<agent>.yaml.

Subscribe – consume x:events.norm (and/or scheduled ticks).

Process – for each Event or tick, run logic; may emit 0..N Signals.

Publish – push to x:signals.<agent_id>; persist via state-api (internal).

Health – expose heartbeat metric + last processed stream ID.

Identifiers

agent_id (slug): tech, funding, sentiment, rotation, mm-passivbot (future), etc.

agent_version (semver) recorded on each Signal.

3) Data Contracts
3.1 Event (normalized input) — x:events.norm
{
  "v": "0.1",
  "id": "uuid",
  "ts": "2025-10-23T14:05:22.532Z",
  "source": "tv|yt|metrics|discord",
  "kind": "tv|yt_chunk|idea|funding|oi_delta|liqmap",
  "symbol": "BTCUSDT",
  "timeframe": "15m",
  "stance": "bullish|bearish|neutral|null",
  "payload": {
    "name": "unikill_v1|ema_21x55|daily_vwap_close|ethbtc_flip|soleth_spike|funding|oi|liqmap|idea|yt_chunk",
    "fields": { "key": "value" }
  },
  "tags": ["keeper","audited","tier1"],
  "provenance": { "creator": "Chaser.sol/TraderX", "url": "..." },
  "hash": "sha256-string",
  "meta": { "ingest_id": "uuid", "received_at": "…Z" }
}


stance may be null for informational sources (e.g., level-only).

payload.fields must include all items referenced by agents (e.g., ema_cross_dir, funding_8h, oi_z, liq_cluster_dist).

Idempotency hash (recommended):
sha256(source + kind + symbol + timeframe + stableSerialize(payloadCore))

Examples (payloadCore by kind):

tv: { "alert_id":"…", "label":"FVG close", "level":69250.0 }

yt_chunk: { "video_id":"…", "chunk_id":12, "stance":"bear" }

funding: { "funding_8h":-0.021, "window":"24h" }

oi_delta: { "zscore":1.8, "window":"6h" }

liqmap: { "cluster_dist":180.0, "side":"long|short" }

3.2 Signal (agent output) — x:signals.*
{
  "v": "0.1",
  "id": "uuid",
  "ts": "2025-10-23T14:05:23.100Z",
  "agent": "tech|funding|sentiment|rotation",
  "agent_version": "0.1.0",
  "symbol": "BTCUSDT",
  "timeframe": "2h",
  "kind": "trend|pullback|reclaim|exhaustion|breakout|squeeze_risk|unwind|narrative_push|rotation_impulse",
  "dir": "long|short|neutral",
  "confidence": 0.72,
  "value": {
    "score": 0.67,
    "features": { "vwap_state": "above", "ema_slope": 0.35, "oi_z": 1.8 }
  },
  "event_ids": ["uuid", "uuid"],
  "notes": "Unikill V1 + EMA 21x55 alignment; VWAP reclaim; funding tailwind",
  "debug": { "thresholds_applied": true, "regime_fit": "trend" }
}


Guarantees

confidence ∈ [0,1] and calibrated (see §6).

event_ids reference all inputs used.

notes = concise NL summary for UI/copilot.

4) Streams & Routing

Consume: x:events.norm (optionally x:metrics.tick).

Produce: x:signals.<agent_id> (+ mirrored to x:signals.* via consumer group for fusion).

Backpressure: if lag > threshold, agent slows intake (see §12).

5) Required Behaviors by Agent Type
5.1 Tech/Structure (agent_id=tech)

Inputs (audited sources only):
unikill_v1(15m,1h), ema_21x55(15m/30m/1h/2h), btc_daily_vwap_close, ethbtc_rotation, soleth_spike, combo_fvg.
Outputs: kind ∈ {trend, pullback, reclaim, exhaustion, breakout}.
Rules:

Ignore non-audited sources (drop or emit with confidence=0 and debug.error).

Attach features (slopes, distances): ema_dist_bp, vwap_state, structure_break_dir.

If conflicting signals for (symbol,timeframe) within last N minutes, down-weight confidence proportionally.

5.2 Funding/OI (agent_id=funding)

Inputs: metrics provider (single vendor; normalized).
Outputs: kind ∈ {squeeze_risk, leverage_build, unwind}.
Rules: spike detection with z-score on oi_delta; funding regime (pos/neg); liquidation cluster proximity.
Features: {funding_8h, oi_z, liq_heat, basis?}.

5.3 Sentiment/Narrative (agent_id=sentiment)

Inputs: TradingView Ideas + YouTube chunks (RAG).
Outputs: kind ∈ {narrative_push, narrative_fade}.
Rules: weight=elo(source)*recency_decay*author_relevance(symbol); produce stance; summarize 1–2 claims; include provenance links in debug.

5.4 Rotation/Macro (agent_id=rotation)

Inputs: ETHBTC trend flips, SOLETH spikes, DXY/SPX drift.
Outputs: kind ∈ {rotation_in, rotation_out} with optional target baskets (e.g., {alts_high_beta}).

6) Confidence & Calibration

Confidence is the mapped probability of directional correctness conditional on current regime.

Weekly calibration: bin past signals by regime (trend|range|high_vol|low_vol).

Fit isotonic|platt|temperature per agent+regime.

Goal: reliability curve near diagonal (±0.05).

Persist to calibration_params and export per-agent files under config/calibration/<agent>.json.

7) Regime Awareness

Every Signal must carry debug.regime_fit ∈ {trend, range, high_vol, low_vol}.
Fusion down-weights agents whose 30-day Brier worsens in current regime.

8) Idempotency, Cooldowns & Restarts

Keep last processed stream ID; resume from it on restart.

Agent-side dedupe: hash of (symbol, timeframe, kind, window_ts); do not emit duplicates inside cooldown_sec.

Emit at most one identical Signal per (symbol, timeframe, kind) during cooldown.

9) Config Surface (per-agent YAML)
agent_id: tech
agent_version: 0.1.0
cooldown_sec: 60
min_confidence: 0.55
timeframes: [15m, 30m, 1h, 2h]   # agent-specific TFs allowed
regime_weights:
  trend: 1.0
  range: 0.7
  high_vol: 0.8
  low_vol: 0.9
features:
  ema_slope_window: 20
  vwap_lookback: 3
input_filters:
  allow_payload_names:
    - unikill_v1
    - ema_21x55
    - daily_vwap_close

10) Error Handling

Malformed Event: log + push to x:events.dead with reason.

Computation error: set confidence=0, add debug.error; do not publish to fusion stream.

Metrics: increment errors_total; expose last_error_at.

11) Testing Contract

Golden fixtures: tests/fixtures/<agent>/events/*.json.

Determinism: same inputs → same Signals.

Calibration test: reliability slope in [0.9, 1.1] on test set.

Latency budget: P95 process time < 50 ms per Event.

12) Registration & Observability

Registration (on boot)

POST /internal/agents/register
{
  "agent_id": "tech",
  "version": "0.1.0",
  "streams": { "consume": ["x:events.norm"], "produce": ["x:signals.tech"] },
  "capabilities": ["trend","pullback","reclaim","exhaustion","breakout"],
  "timeframes": ["15m","30m","1h","2h","4h","8h"]
}


Metrics (per agent)

signals_emitted_total, confidence_avg, latency_ms, errors_total, cooldown_drops_total, stream_lag.

13) REST APIs

All under State API (state-api) except /ingest/* (Ingest Gateway) and /exec/* (Executors).

13.1 Ingest Gateway (FastAPI)

POST /ingest/tv – TradingView webhook
Headers: X-TS-Source: tv
Body (as TV sends; we normalize):
{"symbol":"BTCUSDT","timeframe":"2h","label":"FVG close","level":69250.0,"alert_id":"abc-123"}
Returns 200 OK (idempotent). Writes events.raw → events.norm with hash.

POST /ingest/yt – YouTube/Idea URLs (batch)
{"urls":["…","…"],"channel":"CryptoByMathieu"} → creates yt_chunk|idea events.

POST /ingest/metrics – Optional push (if not polling)
{"kind":"funding","symbol":"BTCUSDT","timeframe":"8h","payload":{"funding_8h":-0.021,"window":"24h"}}

13.2 Opportunities

GET /opps/latest?symbol=BTCUSDT&tf=2h&limit=20

GET /opps/{id} – includes links.event_ids and resolved events.

13.3 Preview / Execute

POST /actions/preview

{"opportunity_id":"uuid","venue":"drift","size":0.75}


Returns Decision with risk.allowed and {entry,sl,tp} plan.

POST /actions/execute

{"decision_id":"uuid","confirm":true}


Revalidates risk; calls executor; writes exec_orders; updates opportunities.status.

Errors:
400 INVALID_INPUT, 403 RISK_BLOCK, 409 EXPIRED/STALE, 500 VENUE_DOWN.

13.4 Telemetry / Journaling

GET /decisions/{opportunity_id}

GET /exec/{decision_id}

GET /events/{id}

14) Risk Guardian – Policy Model
{
  "v": "0.1",
  "max_per_symbol_notional": 2.0,
  "max_account_leverage": 5.0,
  "min_quality": 0.60,
  "cooldowns": { "symbol_sec": 300, "venue_sec": 120 },
  "hard_blocks": {
    "funding_sign_flip": true,
    "extreme_oi_z": 3.0
  },
  "sl_tp_rules": {
    "default_rr": 1.8,
    "atr_mult": { "sl": 1.2, "tp": 2.2 }
  }
}


Returns e.g.
{"allowed":false,"reason_code":"COOLDOWN","until":"…Z"}

15) Executors – Drift & Hyperliquid

Drift (Python exec-drift-svc)
POST /exec/drift/order
{"symbol":"BTC-PERP","side":"buy|sell","qty":0.75,"type":"market|limit","price":69210.0,"reduceOnly":false,"clientId":"uuid"}

Hyperliquid (Node/TS exec-hl-svc)
POST /exec/hl/order – same shape; WS submit for low latency inside the service.

Both must:

Echo requests + venue responses into x:exec.orders.

Retry idempotently on transient errors (guard on clientId).

16) Calibration Interface

POST /calibration/run (internal/cron)

Pull N-day signals vs realized outcomes.

Fit per agent+regime (isotonic|platt|temp).

Write calibration_params (+ store reliability scores).

17) Error Model (REST)
{
  "error": { "code":"string", "message":"human readable", "details":{ } },
  "trace_id":"uuid"
}

18) Persistence Guarantees

Events: write to events (with UNIQUE(hash)) before publishing to x:events.raw.

Signals: append-only; link back to events.

Opportunities: upsert snapshot per (symbol,timeframe,snapshot_ts).

Decisions/Exec: append-only audit trail; immutable.

19) Example Flows

TV alert → execute on Drift (happy path)
TV → /ingest/tv → events (hash) → x:events.raw → normalize → x:events.norm → agents → x:signals.* → fusion → opportunities(new) → /actions/preview (OK) → /actions/execute → executor → exec_orders → opportunities.status=executed.

Duplicate TV alert (retry)
Same hash found → 200 OK (deduped); no new emissions.

20) Database Mappings (ERD aligned)

events(id, kind, symbol, timeframe, source, payload, ts, hash, UNIQUE(hash))

signals(id, agent, symbol, timeframe, kind, confidence, features, event_ids[], created_at, INDEX(symbol,timeframe,created_at))

opportunities(id, symbol, timeframe, bias, quality, confluence, links, snapshot_ts, expires_at, status)

decisions(id, opportunity_id, plan, allowed, reason, created_at)

exec_orders(id, decision_id, venue, order_json, status, txid, created_at)

exposures(id, venue, symbol, size, notional, avg_entry, updated_at, UNIQUE(venue,symbol))

regimes(id, symbol, timeframe, regime, detected_at)

calibration_params(id, agent, regime, method, params, brier, updated_at)

vector_ideas / vector_youtube (Qdrant collections)

21) Rate Limits & Backpressure

Ingest returns 429 if queue lag > threshold.

Agents use consumer groups; fusion waits for window completeness or times out.

Executors enforce venue TPS limits (config).

22) Observability

Every service: /healthz and /metrics (Prometheus).

Logs propagate trace_id from ingest through execution.

23) Versioning

Breaking changes bump "v" and topic suffixes (e.g., x:events.norm.v0_2).

REST can accept X-TS-Version header.

24) Minimal Examples (copyable)

Normalized funding event (8h)

{"v":"0.1","id":"…","ts":"…Z","source":"metrics","kind":"funding","symbol":"BTCUSDT","timeframe":"8h","payload":{"funding_8h":-0.021,"window":"24h"},"provenance":{},"hash":"…","meta":{"ingest_id":"…","received_at":"…Z"}}


Funding agent signal (2h)

{"v":"0.1","id":"…","agent":"funding","agent_version":"0.1.0","symbol":"BTCUSDT","timeframe":"2h","kind":"squeeze_risk","dir":"short","confidence":0.67,"value":{"score":0.67,"features":{"funding":-0.021,"oi_z":1.8}},"event_ids":["…"],"notes":"neg funding + rising OI","debug":{"regime_fit":"trend"},"created_at":"…Z"}


Fused opportunity (2h)

{"v":"0.1","id":"…","symbol":"BTCUSDT","timeframe":"2h","bias":0.35,"quality":0.71,"confluence":{"funding":0.67,"tech":0.52,"sentiment":0.40,"rotation":0.30},"dir":"short","links":{"event_ids":["…"],"urls":["…"]},"snapshot_ts":"…Z","expires_at":"…Z","status":"new"}


Preview OK

{"v":"0.1","id":"…","opportunity_id":"…","requested":{"venue":"drift","size":0.75,"dir":"short","plan":{"entry":69180,"sl":69400,"tp":68600}},"risk":{"allowed":true,"reason_code":"OK","checks":{"exposure":{"current":1.2,"limit":1.5},"cooldowns":{"symbol":0,"venue":0},"quality":{"min":0.6,"actual":0.71}}},"created_at":"…Z"}


Execute placed

{"v":"0.1","id":"…","decision_id":"…","venue":"drift","request":{"symbol":"BTC-PERP","side":"sell","qty":0.75,"type":"market"},"response":{"status":"placed","order_id":"…","txid":"…"},"created_at":"…Z"}

25) Repo Map (for agents)
docs/
  SYSTEM_DESIGN.md
  AGENT_INTERFACE.md  <-- (this file)
  diagrams/…

services/
  ingest-gateway/
  agents/{tech,funding,sentiment,rotation}/
  fusion-engine/
  risk-guardian/
  state-api/
  exec-drift-svc/
  exec-hl-svc/

  26) Appendices (recommended)

### 26.1 Canonical Enums Registry
- **timeframes:** ["1m","5m","15m","30m","1h","2h","4h","8h","1d"]
- **sources:** ["tv","yt","metrics","discord"]
- **event.kinds:** ["tv","yt_chunk","idea","funding","oi_delta","liqmap"]
- **signal.kinds:** ["trend","pullback","reclaim","exhaustion","breakout","squeeze_risk","unwind","narrative_push","rotation_impulse"]
- **regimes:** ["trend","range","high_vol","low_vol"]
- **venues:** ["drift","hyperliquid"]
- **risk.reason_codes:** ["OK","COOLDOWN","MAX_EXPOSURE","QUALITY_LOW"]

### 26.2 Sample Agent Configs (YAML)
```yaml
# config/agents/tech.yaml
agent_id: tech
agent_version: 0.1.0
timeframes: [15m,30m,1h,2h,4h,8h]
cooldown_sec: 60
min_confidence: 0.55
input_filters:
  allow_payload_names: [unikill_v1, ema_21x55, daily_vwap_close, combo_fvg]
features:
  ema_slope_window: 20
  vwap_lookback: 3
regime_weights: { trend: 1.0, range: 0.7, high_vol: 0.8, low_vol: 0.9 }
26.3 OpenAPI Stub (State API)
File: docs/openapi/state-api.v0_1.yaml

Endpoints to include:
/ingest/tv, /ingest/yt, /ingest/metrics,
/opps/latest, /opps/{id},
/actions/preview, /actions/execute,
/decisions/{opportunity_id}, /exec/{decision_id}, /events/{id},
/internal/agents/register, /healthz, /metrics.

26.4 Error Codes Table
code	http	description
INVALID_INPUT	400	malformed body/params
IDEMPOTENT_DUPLICATE	200	deduped event/order
RISK_BLOCK	403	policy denied (cooldowns/exposure/quality)
EXPIRED	409	opp/decision no longer valid
VENUE_DOWN	500	executor/venue failure
RATE_LIMIT	429	backpressure protection

26.5 Test Fixtures Layout
bash
Copy code
tests/
  fixtures/
    tech/events/*.json
    funding/events/*.json
  golden/
    signals/tech/*.json
    signals/funding/*.json
26.6 Security Notes
HMAC header X-TS-Signature for internal calls (body MAC).

JWT scopes: read:opps, write:actions.

Webhook shared secret for TradingView.

26.7 Observability Fields (log)
trace_id, stream_id, agent_id, symbol, timeframe, kind, confidence, regime_fit, latency_ms.

pgsql
Copy code
