# Implementation Sequence

Last updated: 2026-09-08

This document exists because "we'll do it later" was said too many times without
a date attached. Every outstanding item is listed with a **slot**, a
**precondition**, and the **reason it sits where it sits**. Nothing is dropped;
some things are deliberately not next.

Ordering rule used throughout: **correctness before reach.** A capability that
makes the system say more must not land before the capability that makes it say
true things. Everything below follows from that one rule.

---

## Slot 0 — Complete

### 0.1 Freshness healthcheck ✅ deployed and verified 2026-09-08

`/healthz` proved only that the port was open. On 2026-09-07 the pollers stopped
for an hour while Docker reported `healthy`. `/readyz` now asserts that fresh
observations are actually being stored, the container healthcheck points at it,
and the pipeline inspector reports snapshot ages per symbol.

**Why first:** every measurement below is worthless if data collection can stop
silently mid-sample.

Verified by reproducing the original failure: with Redis rejecting writes,
`/healthz` answered 200 while `/readyz` returned 503 naming all three stale
symbols and their ages. Recovered automatically when Redis was restored.

---

## Slot 1 — Complete. Gate resolved: no demonstrated skill.

### 1.1 Fixed-window replay / champion-challenger ✅ delivered 2026-09-08

Implemented in `libs/tradesync_core/tradesync_core/replay.py`, exposed at
`POST /state/regime-lab/replay`. First run: 124 cases, champion skill
**-7.3 pts**, closely tracking the independently measured live **-10.2 pts**,
which is the check that replay is faithful.

**It answered its question decisively: weight tuning cannot fix the signal.**
Moving weight between the blocks that hold evidence changed zero decisions;
moving it toward empty blocks only made the system stricter and worse
(-7.3 -> -11.0 -> -14.1 as admissions fell 90 -> 75 -> 54). Since the
direction/suitability split, weights govern admission, not direction. The
lever is more directional evidence, not a better weighting.

See [the change record](changes/2026-09-08_fixed-window-replay.md).

It closed an unfinished **Phase 2** roadmap deliverable:

> "Add a Regime Lab where the operator can ... **replay a fixed paper window**"

### 1.2 Skill across two regimes ✅ resolved 2026-09-08 — **gate returns NEGATIVE**

Both regimes are now present in the stored window. Result:

| Horizon | Regime | n | Skill | Significance |
|---|---|---|---|---|
| 15m | falling | 68 | +11.4 pts | 1.9 SE |
| 15m | rising | 76 | -4.0 pts | -0.7 SE |
| 60m | falling | 84 | -2.9 pts | -0.5 SE |
| 60m | rising | 50 | -5.0 pts | -0.7 SE |

Nothing crosses two standard errors. **Skill is not demonstrated, so Slot 4
stays closed.**

This also corrected an earlier error. The pooled 60m figure of -10.2 pts
(-2.4 SE) looked significant and was an artefact of pooling regimes with
different base rates — Simpson's paradox. The system is indistinguishable from
chance, not anti-predictive.

`GET /state/outcomes/by-regime` now reports per-regime skill with its standard
error, so the pooled number cannot mislead again. See
[the change record](changes/2026-09-08_regime-split-skill-gate.md).

---

## Slot 2 — Health states and ageing ✅ delivered 2026-09-08

### 2.1 Per-connector health states with ageing ✅

Right now a connector is `live`, `partial`, `contract_only` or `offline` with no
notion of *how long* it has been that way. An operator cannot distinguish
"degraded for ten seconds" from "degraded since yesterday."

Delivered: `state_history.py` (pure), migration `005_node_state_history.sql`,
transition recording on every pipeline read, and
`GET /state/integration-pipeline/history`. Every stage now reports
`state_age`, `recent_transitions` and `flapping`.

Verified against a real transition: stopping fusion-engine recorded
`live -> partial` and dropped Tier A to 6/7; restarting recorded
`partial -> live`. Ageing resets on change, and the flap counter feeds
Slot 4 so an oscillating connector cannot generate a notification storm.

**Why here and not earlier:** ageing is only meaningful once readiness is
truthful (Slot 0). Building it on a healthcheck that lies produces confident
history of a fiction.

### 2.2 Stale-evidence surfacing in the Cockpit ✅

The Integration Pipeline page shows each stage as "LIVE for 8m" and flags an
oscillating stage as `unstable`. Snapshot freshness per symbol appears in the
market-data node evidence.

Outstanding: the same ageing on Mission Control's summary cards.

---

## Slot 3 — Federation connectors

All four are **Tier B: enrichment only.** None may gate Tier A, and none can
grant approval or execution authority. They are grouped because they share one
precondition and one architectural pattern.

**Shared precondition (now met):** the quarantine → extraction → proposed
delta → approved promotion path exists as of 2026-09-08. Without it a connector writes directly
into evidence the system later uses to judge itself, which is the same class of
error as the healthcheck that only checked the port.

### 3.1 Quarantine intake path ✅ delivered 2026-09-08

`quarantine.py` (pure), migration `006_quarantine_intake.sql`,
`POST`/`GET /state/quarantine`. Refuses unregistered sources, oversized
payloads, replays, stale and future-dated submissions, and — most importantly —
any payload that tries to set its own `admitted`, `authority`,
`execution_authority`, `scoring_allowed`, `provenance` or `trust`.

Verified live: a legitimate TradingView-shaped alert accepted with
`authority: none`; a payload claiming authority refused by name; an
unregistered source refused; a replay refused as duplicate. Refusals are stored
too, because "what did that connector try to send" is what an operator needs
later.

Promotion is not automated. `promotion_blockers` reports readiness and refuses
to grant it: no operator review means blocked, and a proxy/context-only
provenance can never reach a directional score.

See [the change record](changes/2026-09-08_state-ageing-and-quarantine.md).

The Knowledge Graph intake UI is delivered at `/intake`: every submission with
its verdict, reason codes, payload and review controls. The provenance selector
marks non-scoreable options before the choice is made. A successful promotion
still returns `authority: none`.

The legacy `/sources` page remains in place and should be retired once nothing
references it.

### 3.2 Strike Zone Crypto — **corrected 2026-09-08: this is not a service**

Inspected `C:\Users\chaseos\Documents\Projects\strikezone_crypto` directly. It
contains no compose file, no package manifest and no entrypoint. It is a
**Pine Script indicator repository**: Bias Flip, EMA cross, FVG Engine, Market
Structure Analyzer V2, Risk Regime, EQH/EQL Sweep Detector, Trading Sessions +
Killzones, and Unikill V2.

So there is nothing to start and no `STRIKEZONE_CONNECTOR_URL` to set. Strike
Zone reaches TradeSync the same way any Pine indicator does — **as a TradingView
alert through the webhook path in 3.5.** This sub-slot collapses into that one.

The pipeline inspector still models `strike_zone` as a separately probeable
connector. That model is wrong and should be reframed as a *submission source*
rather than a service with a health endpoint.

Candidates remain **paper research**. A Strike Zone alert is quarantined
evidence, never a signal and never an approval.

### 3.3 Agent harnesses ✅ delivered 2026-09-08

Harnesses may explain, compare, and draft proposals. They may not score, gate,
approve or execute. That boundary is now **enforced in code**, which was the
stated precondition for setting `AGENT_HARNESS_URL` at all.

`agent_harness.py` makes it structural four ways: the intent vocabulary has no
word for deciding; a response carrying `approved`, `score`, `direction`, `side`,
`order` or any of eighteen such fields is refused **by name** rather than
stripped; nested claims and claims embedded in the answer's own JSON content are
caught too; and every accepted answer is filed in quarantine, never in evidence.

Proven against a live `qwen3:4b` that was successfully prompted past its
instructions into emitting `{"approved": true, "side": "LONG", "score": 0.99}` —
refused with all three fields named, and the attempt recorded as a quarantine
refusal so the escalation is visible rather than discarded.

Fixed on the way: the transport error reported `unreachable: ` with nothing
after it, because `httpx.ReadTimeout` stringifies to an empty string.

**Not blocked on a runtime.** A runtime being absent blocked live verification,
not the enforcement. `AGENT_HARNESS_URL` is unset by default and the status
endpoint answers `not_configured`.

See [the change record](changes/2026-09-08_harness-boundary-pine-candidates-and-gate.md).

### 3.4 ChaseOS knowledge + Gate ✅ delivered 2026-09-08

Canonical instance is `C:\Users\chaseos\Documents\chaseos_chaseintech`
(00_HOME .. 99_ARCHIVE, 27k+ notes) — corrected 2026-09-08. **Read-only.** No
model or connector may write canonical knowledge or consume approval authority.

**Delivered:** `graph_snapshot.py` validates a ChaseOS `GraphSnapshot` against
its own contract (`chaseos-core/runtime/graph/artifact.py`, read not
reinvented); migration `009` holds the adjacency projection;
`graph_projection.py` and `/state/knowledge/graph/{status,ingest,nodes,neighbours}`
read and serve it.

The three boundaries are structural, not documentary. There is no write path to
the vault and the mount is `:ro` — proven by a refused `touch` inside the
container. A node or edge claiming `execution_authority`, `approved`,
`scoring_allowed`, `tier` or `trust` is refused **by name** rather than stripped.
An edge to an absent node is refused, and the database carries matching
composite foreign keys.

Verified with a 2,800-node / 9,600-edge fixture built using ChaseOS's own
dataclasses: ingested in 2.7s, depth-3 adjacency in 16ms through a cyclic graph.
With `CHASEOS_GRAPH_DIR` unset the status endpoint answers `not_configured` and
every other surface still answers 200 — the phase exit gate.

**The Gate, delivered 2026-09-08.** `control_envelope.py` already bound one
authenticated ChaseOS decision to one immutable candidate with a closed authority
ceiling, and was wired into nothing. It is now
`POST /state/knowledge/gate/authorize-paper-evaluation`.

The candidate is **re-extracted**, never accepted from the caller, so an approval
cannot be attached to a candidate edited after the operator saw it. "Once" is
enforced where history lives: `approval_id` is unique in `control_envelopes`, so
a replay collides with the constraint rather than passing a check that could
race. Verified: authorise 200, replay 409, ceiling denies live execution.

Verified against **real knowledge**, not only a fixture: ChaseOS's own
`runtime/graph/builder.py` was run against the canonical vault, producing 7,314
nodes and 10,123 edges, written to a TradeSync-side directory and ingested in
6.3s. Adjacency on a degree-1520 hub answers in 41ms at depth 3.

`.chaseos/graph/` inside the vault stays empty: writing there is ChaseOS's to
do, and TradeSync's boundary is that it does not write canonical knowledge.

See [the change record](changes/2026-09-08_chaseos-graph-projection.md).

### 3.5 TradingView + Pine Script — receipt validation ✅ delivered 2026-09-08; ingress still open

`strike_zone.py` turns an authenticated Pine receipt into a `trade_candidate_v1`,
wired as `POST /state/quarantine/{id}/extract-candidate` — the extraction step of
quarantine → extraction → proposed delta → promotion.

One rule decides the design: **authority fields are written by the adapter, never
copied from the receipt.** A Pine script is a text file on a third party's server
that anyone holding the alert URL can aim here; if it could set
`live_execution_allowed` this would be a remote execution primitive with a
webhook for an interface. A receipt that tries is refused by name.

The acceptance criterion is `paper_ledger._validate_candidate`, which re-checks
the same invariants without trusting who built the candidate — and a test proves
that second lock bites.

**Precondition still outstanding: the ingress decision.** Cloudflare Tunnel plus
the four-IP WAF allowlist is infrastructure, and none of the above needs it.

Constraints already verified: ports 80/443 only, **no custom headers** so the
shared secret must travel in the JSON body, four fixed source IPs (the strongest
available control), and a 3-second timeout. One webhook URL per alert, but many
alerts may target one endpoint and self-identify in the body.

Requires Cloudflare Tunnel plus a four-IP WAF allowlist. Full analysis in
[Webhook ingress security](architecture/WEBHOOK_INGRESS_SECURITY.md).

**The risk is evidence poisoning, not theft.** A Pine alert becomes quarantined
evidence, never a signal.

---

## Slot 4 — Governed alerts (Phase 3) — **CLOSED by gate 1.2**

**Precondition: gate 1.2 returns a positive result. As of 2026-09-08 it
returned negative**, so this slot is closed rather than merely not-next.

This is the one hard gate in this document. Alerting on a signal with no
demonstrated skill trains the operator to act on noise under time pressure. The
roadmap invariant "no alert action can place an order" protects the account; it
does not protect judgment.

1.2 showed no skill, so the work moves to improving the signal first. Reopening
this slot requires a re-run of 1.2 returning a result beyond two standard
errors.

**The lever is directional evidence**, established by replay: weight tuning
changed nothing or made things worse, and the two admitted directional features
produce calls indistinguishable from chance. Next candidate is
`coinbase_premium_bps`, already marked `signal_kind: directional` in the catalog
and currently `unavailable`.

Scope when it opens: Rust `alert-router-rs`, PostgreSQL outbox, dedup, priority,
expiry, quiet hours, delivery receipts, PWA/ntfy.

---

## Slot 3.6 — Directional evidence (new, promoted by the Slot 1.2 result)

Added 2026-09-08 because the gate identified this as the only remaining lever.

### 3.6.1 Coinbase spot premium ✅ delivered as context-only

Catalog **1.4.0**. Live at +2.4 to +3.1 bps across the three symbols, with
alignment skew recorded per observation (59 ms to 2.9 s against a 10 s bound).

**Deliberately not scoring.** Admitting a non-Hyperliquid venue to the scoring
path is an operator decision. See
[the change record](changes/2026-09-08_spot_premium_context.md) for what
promotion would require — including that the `source_authority` enum has no
honest value for an external reference venue, so promotion needs a schema
addition rather than a convenient relabel.

Promoting it would also lift the suitability coverage ceiling from 0.55 toward
0.70, potentially removing the permanent `low_data_coverage` cap.

**Measured after promotion, 2026-09-08.** Over the last hour of live verdicts,
`data_coverage` ranged 0.2528 to **0.6375**, mean 0.5621. The 0.55 ceiling no
longer binds — it was a consequence of which features were admitted, not a
structural limit, and admitting `coinbase_premium_bps` moved it as predicted.
The carried defect entry is retired as stale rather than fixed: no code changed,
the catalog did.

### 3.6.2 Further directional candidates — open

`hl_direct_liquidation_flow` remains `unavailable`: Hyperliquid does not publish
liquidation events on an admitted feed, and the OI proxy is explicitly barred
from standing in for it.

Beyond that, adding directional evidence means adding *sources*, each of which
repeats the governance question this slot just raised.

---

## Slot 5 — Market Canvas maturity (Phase 4) — complete

Read-only canvas shipped 2026-09-08: candles, volume, evidence markers,
symbol/interval controls, reachable from Mission Control and the sidebar.

### 5.1 Versioned operator drawings ✅ delivered 2026-09-08

`canvas_drawings.py`, migration `007_canvas_drawings.sql`, and the
`/state/canvas/drawings` endpoints. An edit **supersedes rather than
overwrites**, so "what did I think at the time" survives; a level revised twice
reads as `v3` on the chart. Deleting keeps history too.

Verified: create → v1, edit → v2 with v1 retained and superseded, malformed
trendline rejected with HTTP 400, delete removes it from the chart while history
still returns it.

See [the change record](changes/2026-09-08_canvas_drawings.md).

### 5.2 Trendlines and ranges ✅ delivered 2026-09-08

SVG overlay projected through the chart's own `timeToCoordinate` /
`priceToCoordinate`, so shapes stay pinned through pan and zoom. Off-scale
anchors are not drawn rather than interpolated. Two-click placement with an
explicit "First point… / Second point…" state.

### 5.3 Evidence timeline ✅ delivered 2026-09-08

`GET /state/evidence/timeline` plus a panel below the chart. Reconstructs each
call from the evidence that produced it, through the exact configuration
digests it was taken under, to what the market did at each horizon.

**This is the Phase 4 exit gate.**

### 5.4 Funding, open interest and depth ✅ delivered 2026-09-08

`context_series.py` and `depth.py` in market-data, `GET /state/market/context`
and `GET /state/market/depth`, and three new surfaces on the canvas: funding and
open-interest panes synced to the price chart's time scale, and an order-book
panel whose resting walls are drawn on the price axis.

The three constraints that shaped it:

- **Open interest has no venue history.** Hyperliquid publishes only the current
  value, so the only series that can exist is our own rolling 24 hours. On a
  12-day chart it covers 8% of the window; the pane states that rather than
  letting the line stop unexplained.
- **A gap is not a flat line.** Buckets with no sample are omitted and rendered
  as whitespace. A collection outage and a market that did not move look
  identical once a line is drawn through the hole.
- **Depth is not a series.** The book is replaced wholesale each poll, so it sits
  beside the chart, not across candles it was never present for. Walls are
  dotted where operator annotations are dashed.

Fixed on the way: all three market proxies returned HTTP 500 for an unsupported
venue instead of passing market-data's 404 through.

See [the change record](changes/2026-09-08_canvas-funding-oi-depth-overlays.md).

### 5.5 Closed, not deferred

- Chart-native alert-rule creation. Downstream of Slot 4, which gate 1.2 closed:
  an alert rule on a signal with no demonstrated skill is the same trap as
  governed alerting. This does not reopen until a measurement does.

---

## Slot 6 — Execution foundation (Phase 5+) — split

Treating this as one indivisible slot was wrong. The authority constraint names
**capabilities** — "no key, signer, wallet, deployment, spend, or live
execution" — not a slot number, and the slot contains both the machinery that
would *enable* execution and the machinery that would *refuse* it. The second
half makes the system safer whether or not the first is ever built.

### 6a Refusal-side ✅ delivered 2026-09-08

- **Single-use approval** — the ChaseOS Gate (3.4). An approval binds to one
  candidate and authorises one paper evaluation; `approval_id` is unique so a
  replay collides with a constraint rather than a check that could race.
- **Risk policy** — `RiskGuardian` was already comprehensive and fails closed on
  `EXECUTION_ENABLED` before any per-symbol rule.
- **Reconciliation** — `reconciliation.py` and
  `GET /state/execution/reconciliation`. Reads recorded decisions against
  recorded orders and reports three divergence classes. An orphan decision does
  **not** guess whether execution never happened or happened unrecorded: those
  have opposite remedies. Proven against the live database with a planted clean,
  mismatched and orphaned decision.
- **Preflight** — `GET /state/execution/preflight`. Everything that would have
  to be true before an order could be placed, with the current value of each.
  It opens nothing and has no counterpart that does; "why can I not trade" had
  its answer spread across an environment variable, a service that may not be
  running, a roadmap gate and a risk policy.

### 6b Enabling-side — closed, and not by omission

Wallet preview and the isolated signer are **not built and will not be** on the
current evidence. Both are named capabilities in the authority constraint, and
gate 1.2 returned NEGATIVE: no demonstrated skill in any regime at any horizon.

**Nothing in the current measurements argues for moving toward execution.**
`DRY_RUN=true` and `EXECUTION_ENABLED=false` remain unchanged. Opening this
requires explicit operator approval and a passing skill gate, in that order.

---

## Carried defects

Tracked so they are not rediscovered:

| Item | Status | Slot |
|---|---|---|
| `tests/test_core_scorer.py` cannot collect — root `main.py` shadows it | **resolved 2026-09-08** | — |
| Every service package named `app` — see below | **resolved 2026-09-08** | — |
| `test_main.py` preview/execute — 3 failures | **resolved 2026-09-08** | — |
| Refusal rows unbounded — ~4,300/day | **resolved 2026-09-08** | — |
| Suitability blocks cannot exceed 0.55 coverage | **stale 2026-09-08** — see below | — |
| No hysteresis on direction band | **resolved 2026-09-08** | — |


## The `app` package collision, precisely

Every service package is named `app`, so only one can own that name per Python
process. Diagnosed 2026-09-08:

- `tests/test_market_data_math.py:9` inserts `services/market-data`, claiming
  `app` for market-data.
- `tests/test_phase3d.py:24` inserts `services/backtest-runner` and then imports
  `app.replay`, which no longer resolves.

Alphabetical collection order decides the winner, so `test_phase3d.py` passes
**32/32 in isolation** and fails 4 when the directory runs together. The failure
is about import order, not about the code under test.

`tests/test_regime_paper_pipeline.py` showed the fix: load the service under a
private package name (`fusion_engine_app`) with an explicit `__path__`, so its
relative imports still resolve without claiming the global `app`.

**Resolved 2026-09-08.** `tests/_service_import.py` generalises that loader and
the five affected root test files use it. Chasing the collision surfaced four
defects in shipped code, not tests: `ingest-gateway` had both an `app/models.py`
and an `app/models/`, which made `app/ingest.py` and `app/collectors/` dead code
inside the container; `ingest-gateway` also depended on two global names that
only resolved because the Dockerfile laid two trees side by side;
`backtest-runner` imported itself absolutely; and `state-api` reported
`execution_enabled=True` from three rejection paths while the gate was closed.

The service suites under `services/*/tests` stay written against `app`, because
that is how each service imports itself in its container, so they cannot share a
process. `tools/run_tests.py` gives each its own; `pytest.ini` points a bare
root `pytest` at the cross-service suite. 388 tests, all green.

Full account: `docs/changes/2026-09-08_test-suite-repair-and-app-package-collision.md`.
