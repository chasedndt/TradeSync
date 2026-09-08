# State Ageing and Quarantine Intake

Date: 2026-09-08

Branch: `codex/2026-09-01-dashboard-overhaul`

Two slots delivered: health-state ageing (Slot 2) and the quarantine intake
path (Slot 3.1), which is the shared precondition for every Tier B connector.

## 1. Health states with ageing

### The problem

A stage was reported as `live`, `partial`, `contract_only` or `offline` with no
notion of how long it had been that way. "Scorer offline" read identically
whether it dropped out ten seconds ago or had been down since yesterday, and
those call for completely different responses. **A state without a duration is
half a fact.**

### Delivered

- `libs/tradesync_core/tradesync_core/state_history.py` — pure transition
  detection, coarse duration phrasing, and flap counting.
- Migration `005_node_state_history.sql`.
- Transition recording on every pipeline read, and
  `GET /state/integration-pipeline/history`.
- Every node now carries `state_age`, `state_duration_seconds`,
  `recent_transitions` and `flapping`.
- The Cockpit shows each stage as "LIVE **for 8m**" and flags an oscillating
  stage as `unstable`.

Two deliberate choices:

- **A first sighting is a transition from `None`.** History starts when
  observation starts, rather than pretending a stage has always been in its
  current state.
- **Duration phrasing is coarse.** "Offline for about 3 hours" is what an
  operator acts on; second precision on a multi-hour outage is noise.

### Why flap detection now, before alerting exists

A stage oscillating between two states every poll would generate one
notification per transition once Slot 4 lands. The counter has to exist before
the alerting does, or the first thing alerting does is spam.

### Verified against a real transition

Stopping `fusion-engine` and restarting it produced:

```
14:47:12  None -> live      (first sighting)
14:47:40  live -> partial   (Tier A dropped to 6/7)
14:48:07  partial -> live   (recovered)
```

Ageing reset on each change, and the flap counter incremented.

## 2. Quarantine intake

### Why this had to come before any connector

Every Tier B connector — Strike Zone, agent harnesses, ChaseOS snapshots,
TradingView alerts — sends material TradeSync did not measure. Without a
boundary, that material lands directly in the evidence the system later uses to
judge itself.

The system had already made the same class of mistake twice in one day: a
healthcheck that only proved the port was open reported an hour-long outage as
healthy, and a hit rate without a base rate reported a falling market as skill.
Both were cases of accepting a signal without checking what it actually
asserted. An unauthenticated external writer is that failure with a motivated
adversary attached.

### The path

**quarantine -> extraction -> proposed delta -> approved promotion.** Nothing
skips a step, and promotion is an operator act.

### Delivered

- `libs/tradesync_core/tradesync_core/quarantine.py` — pure admission control.
- Migration `006_quarantine_intake.sql`, with bounded retention indexes and a
  `unique (source, content_digest)` constraint so a resubmission is recognised.
- `POST /state/quarantine` and `GET /state/quarantine`.

Rules enforced:

| Rule | Refusal code |
|---|---|
| Only registered connectors may submit | `unknown_source` |
| A payload may not set its own trust or authority | `payload_claims_authority` |
| Bounded payload size | `payload_too_large` |
| Identical content is a resubmission, not new evidence | `duplicate_submission` |
| Readings must be recent | `submission_stale` |
| ...and not from the future, beyond tolerated skew | `timestamped_in_future` |

The forbidden-field list is the important one: `admitted`, `approved`,
`authority`, `execution_authority`, `scoring_allowed`, `signal_kind`,
`provenance`, `trust`, `tier`. **A payload is data, never instruction.**
Privilege escalation by assertion is the obvious attack against a webhook
endpoint, and it is refused by name.

### Verified live

```
legitimate TradingView alert  -> accepted: True,  authority: none
payload claiming authority    -> refused: payload_claims_authority
                                 (names admitted, execution_authority, scoring_allowed)
unregistered source           -> refused: unknown_source
replay of the first alert     -> refused: duplicate_submission
```

**Refusals are stored too.** "What did that connector try to send?" is exactly
the question an operator needs answered later, and discarding rejected
submissions would throw away the evidence of an attack.

### Operator surface

`/intake` in the Cockpit replaces the Sources shell for connector material. It
shows every submission, accepted or refused, with the reason codes, the exact
payload that arrived, and the review controls. The provenance selector labels
`context_only` and `proxy` as "(cannot score)" so the constraint is visible
before the choice is made rather than only in the refusal afterwards.

`POST /state/quarantine/{id}/review` records the operator decision and reports
what blocked a promotion. Verified live:

```
promote as context_only -> promoted: False, blocked: provenance_not_scoreable
promote a refused item  -> promoted: False, blocked: never_accepted
promote as observed     -> promoted: True,  blockers: []  (authority: none)
```

Note the last line: even a successful promotion returns `authority: none`.
Promotion marks material as admitted *context*; it never confers scoring,
approval or execution authority.

### What this unblocks

Slot 3.2–3.5 — Strike Zone, agent harnesses, ChaseOS Gate, TradingView/Pine —
now have their shared precondition. Each still needs its own service running and
its own adapter, but none of them will write directly into evidence.

Promotion itself is deliberately not automated: `promotion_blockers` reports
readiness and refuses to grant it. An item with no operator review is blocked
by `operator_review_required`, and a `proxy`/`context_only`/`unavailable`
provenance can never reach a directional score.

## 3. TradingView / Strike Zone webhook receiver

### A correction worth recording

The plan carried Strike Zone Crypto as a *service* to start and probe, with a
`STRIKEZONE_CONNECTOR_URL`. Inspecting
`C:\Users\chaseos\Documents\Projects\strikezone_crypto` showed that is wrong:
there is no compose file, no package manifest and no entrypoint. It is a **Pine
Script indicator repository** — Bias Flip, EMA cross, FVG Engine, Market
Structure Analyzer V2, Risk Regime, EQH/EQL Sweep Detector, Killzones, Unikill
V2.

Strike Zone therefore reaches TradeSync exactly as any Pine indicator does: as a
TradingView alert. Slots 3.2 and 3.5 collapse into one path, and the pipeline
inspector's model of `strike_zone` as a probeable service should be reframed as
a submission source.

### Delivered

`libs/tradesync_core/tradesync_core/tradingview_webhook.py` plus
`POST /webhook/tradingview`.

The shaping constraint, verified from the venue's documentation: **TradingView
cannot send custom HTTP headers.** There is no `Authorization` header to check,
so the shared secret must travel inside the alert body. Consequences:

- The secret is compared with `hmac.compare_digest`. A timing oracle on a public
  endpoint would let an attacker recover it byte by byte.
- **The secret is scrubbed before storage.** Verified: the quarantined payload
  contains no `secret` field.
- Plain-text alerts are refused. They cannot carry a secret, so they cannot be
  authenticated.
- An unauthenticated alert is refused **before touching the database**, so a
  flood of bad secrets cannot fill the intake table.

**Disabled unless `TRADINGVIEW_WEBHOOK_SECRET` is set.** An unauthenticated
public endpoint into a trading system is not an acceptable default, so the
endpoint answers 503 until a secret is configured.

Also recorded in code: the four published TradingView source addresses, for the
Cloudflare WAF allowlist that remains the strongest single control. That
allowlist belongs at the edge — by the time a request reaches this process it
has already consumed resources.

### Verified live

```
no secret configured    -> 503  "webhook disabled: set TRADINGVIEW_WEBHOOK_SECRET"
valid Strike Zone alert -> 200  accepted, authority: none, tier: B
wrong secret            -> 401  bad_secret
plain text body         -> 401  body_not_json
stored payload          -> secret absent
```

One bug found and fixed during verification: `JSONResponse` was not imported in
`state-api`, so the refusal path returned 500 instead of 401. The happy path had
passed, which is exactly why the refusal paths were exercised too.

The test secret was cleared afterwards and the endpoint confirmed disabled
again.

### Still required before this can receive real traffic

Ingress. TradeSync is on localhost; TradingView needs a public URL on port
80/443. That is the Cloudflare Tunnel decision in
[the security analysis](../architecture/WEBHOOK_INGRESS_SECURITY.md), and it is
deliberately not taken here.

## Tests

- `tests/test_state_history.py`: 16 passed.
- `tests/test_quarantine.py`: 19 passed plus 7 subtests, including that each
  forbidden field is refused by name.
- `tests/test_replay.py`: 17 passed.
- `tests/test_tradingview_webhook.py`: 16 passed, including that a wrong
  secret is refused rather than raised, that the secret never reaches
  storage, and that an alert cannot smuggle authority through quarantine.
- `services/state-api/tests`: pipeline and regime-lab suites passing.

## Boundaries

`DRY_RUN=true`, `EXECUTION_ENABLED=false`. No connector was enabled; no
`STRIKEZONE_CONNECTOR_URL`, `AGENT_HARNESS_URL` or `CHASEOS_CONNECTOR_URL` was
set. Quarantined material carries `authority: none` on every response.
