# Regime-Backed Paper Signal Path

Date: 2026-09-07

Branch: `codex/2026-09-01-dashboard-overhaul`

Worktree: `E:\Projects\TradeSync\dashboard-overhaul-2026-09-01`

## Repo-truth delta

Before this slice the market feature path and the opportunity path did not
meet. `market-data` produced live catalog observations and the Regime Lab
evaluated them at read time, but the only producer that could reach the
`opportunities` table was `core-scorer`'s funding/open-interest heuristic
reading the legacy `events` table. Regime evidence could be inspected; it could
not become a paper opportunity.

Separately, the rulebook's only generically-admitted price/volatility input,
`hl_return_1h_pct`, was marked `availability: "planned"` and never extracted,
so the 0.30-weight `price_volatility` block was permanently empty.

After this slice the one-hour return is derived and admitted, and regime
evidence has a single, evidence-preserving route to a persisted paper
opportunity. Refusals are recorded with their reasoning rather than discarded.

## The coverage ceiling, stated plainly

`aggregate_feature_evidence` admits a feature into a generic block score only
when its `score_mode` is `direct` or `inverse`. Funding, open interest, volume
and oracle premium are `playbook_specific` by deliberate design: they remain
visible evidence but cannot manufacture direction on their own.

The consequence is structural and should not be mistaken for a defect:

| Block | Weight | Generically-admitted features |
|---|---|---|
| price_volatility | 0.30 | `hl_return_1h_pct` |
| liquidity | 0.25 | spread, depth, buy impact, orderbook imbalance |
| positioning | 0.20 | none |
| spot_premium | 0.15 | none |
| macro_flows | 0.10 | none |

Maximum attainable `data_coverage` today is therefore **0.55**, below the
rulebook's `minimum_coverage_for_normal_paper_risk` of 0.70. The
`low_data_coverage` flag will fire on every evaluation and cap paper risk at
0.5 until `positioning`, `spot_premium` or `macro_flows` gain an admitted
direct or inverse feature. That cap is correct behaviour, not a bug to remove.

## Implemented

- Added `derive_return_1h_pct` and `select_return_anchor` to
  `services/market-data/app/feature_extractor.py`. The comparator selects the
  newest stored mark price at or before `t - 1h`, never a later point, and
  refuses when the nearest admissible anchor lags the one-hour target by more
  than `RETURN_1H_ANCHOR_TOLERANCE_MS` (default five minutes).
- Added `attach_derived_features` and `resolve_derived_features`, so the
  polling loop derives the return once and writes it onto the snapshot under
  `derived.return_1h_pct` before storage. `GET /features/{venue}/{symbol}` then
  reads it as an ordinary snapshot field and stays a stateless lookup.
- Promoted `hl_return_1h_pct` to `availability: "implemented"` and bumped the
  feature catalog from `1.0.0` to `1.1.0`. New catalog digest:
  `709f9c088e00df58...`.
- Added `libs/tradesync_core/tradesync_core/paper_signal.py`: a pure admission
  decision turning rulebook block evidence into an admitted paper signal or an
  explained refusal. Live and replay share this one implementation.
- Added `services/core-scorer/app/regime_source.py`, which reads the baseline
  evaluation and per-feature evidence from `GET /state/regime-lab/overview`
  rather than recomputing the mathematics, so a live signal and a Regime Lab
  comparison cannot disagree about the same window.
- Added `services/core-scorer/app/paper_producer.py`, which persists every
  verdict to `signals` and publishes only admitted ones to `x:signals.funding`.
- Added `run_regime_paper_cycle` to `services/core-scorer/app/main.py`, active
  by default via `REGIME_PAPER_ENABLED`. The legacy events-table scorer remains
  importable for replay of historical rows but no longer drives the loop.
- Added a `paper_signal_v1` pass-through to
  `services/fusion-engine/app/worker.py`. A regime envelope is traced by its
  evidence digest instead of legacy `event_ids`, and the `EnhancedScorer` is
  deliberately skipped: re-scoring would apply microstructure twice, because
  the regime `liquidity` block already weighs depth and orderbook imbalance.

## A regression this slice introduced and fixed

The first implementation derived the return inside
`GET /features/{venue}/{symbol}`, reading 66 minutes of mark-price history from
Redis on every request. That looked harmless at roughly 0.2 s in isolation, but
the regime engine fans out one history request per normalized feature in
parallel, and the derived feature added an eighth. Under that fan-out the extra
round trip on the first hop pushed `collect_live_feature_results` past its five
second timeout: the Regime Lab overview reported `source_status: unavailable`
with an empty reason (an `httpx.ReadTimeout` stringifies to nothing) and
coverage fell to zero on roughly two of every three reads, while `market-data`
itself answered normally.

Deriving once in the polling path and storing the value on the snapshot removed
the extra read. Measured after the fix: `/features` at 0.22-0.26 s and five
consecutive overview reads all `live` with eleven observations.

The lesson is worth keeping: a read-path cost that is invisible in isolation is
multiplied by every consumer that fans out across features.

## A second regression: per-feature history fan-out

With the derived return admitted, a regime evaluation needed eight history
requests plus one features request — nine HTTP round trips to `market-data` per
symbol. The producer evaluates three symbols a minute, so `market-data`, a
single-worker service also serving the Cockpit, took twenty-seven requests a
minute. Individual `/feature-history` calls then exceeded the five second inner
timeout in `collect_live_feature_results`, and roughly 35% of producer cycles
were skipped with `regime_read_failed` or "market observations are
unavailable".

Raising the timeout would have hidden it. The cost was structural: every new
normalized feature added one more request per symbol per cycle.

`GET /feature-histories/{venue}/{symbol}?feature_ids=a,b,c` now returns all
requested series in one response, and `collect_live_feature_results` makes one
batched call. Round trips per symbol dropped from nine to two, and the cost no
longer grows with the catalog.

Measured after the change: three concurrent overview reads at 1.9-2.6 s, down
from 2.6-4.5 s; twelve consecutive reads all `live`.

## End-to-end result

The objective is met. On 2026-09-07 at 23:54:22 UTC the producer admitted its
first paper signal, and the opportunity builder created the corresponding
opportunity two seconds later.

| Field | Signal | Opportunity |
|---|---|---|
| id | `463b9168-381b-4c17-ac3c-8bdc6e4721a8` | `63b54f58-8c07-4d60-ae14-b53acb725778` |
| symbol / direction | BTC-PERP LONG | BTC-PERP LONG |
| score | `weighted_score` 0.225839277071 | `bias` 0.225839277071 |
| coverage | `confidence` 0.3054 | `quality` 30.5357 |

`bias` equals `weighted_score` exactly, which is the check that matters: the
pass-through preserved the rulebook score instead of letting `EnhancedScorer`
recompute it. `links` carries the evidence digest
`d7365b05...` with `event_ids` empty, as designed for a regime-backed signal.

The arithmetic reconciles against the stored evidence:

```
liquidity:        0.25 x 0.5000 x (-0.17284) = -0.021605
price_volatility: 0.30 x 0.6012 x   0.50215  = +0.090567
                                   numerator = +0.068962
coverage = 0.25 x 0.5 + 0.30 x 0.6012        =  0.305357
score    = 0.068962 / 0.305357               =  0.225839
```

Note that the liquidity block was *negative* (orderbook imbalance -0.39555)
and the net direction was still LONG, because the price/volatility block — the
one this slice unlocked — outweighed it. Before `hl_return_1h_pct` existed that
block was empty and this opportunity could not have been produced at all.

`paper_risk_multiplier` remained 0.5 under the `low_data_coverage` cap, and
`execution_authority` false throughout.

## Two further defects this surfaced

### `status=all` was matched literally

`Overview.tsx` calls `useOpportunities('all', 50)`, but the endpoint applied
`WHERE status = $2` unconditionally. No row stores the status "all", so the
query returned nothing and Mission Control rendered "no scored opportunities
available" — while `status=new` returned seven. The panel could never have
displayed an opportunity.

This had been latent since the panel was written and was invisible until now,
because nothing had ever produced an opportunity to display. The filter is now
built conditionally: "all", or an absent status, applies no status predicate.

### `MOCK_OPP` was missing `confluence`

`test_get_opportunities` was one of the four pre-existing `test_main.py`
failures. Phase 3C added `confluence` to the query and the response builder but
not to the fixture, so the handler raised `KeyError` and the endpoint answered
500. Fixed, and three tests were added covering the wildcard, a named status,
and symbol combined with the wildcard. Three unrelated failures remain in
`test_preview_action`, `test_preview_action_blocked` and `test_execute_action`.

## Admission gates

Every gate below produces a recorded reason code, never a silent zero.

| Code | Meaning |
|---|---|
| `no_admitted_evidence` | No feature was allowed to score |
| `coverage_below_emit_floor` | `data_coverage` under the policy floor (default 0.30), listing the missing blocks |
| `score_inside_deadband` | Score within ±0.05 of zero, treated as no direction rather than a weak one |
| `evidence_stale` | A reading older than the admission bound (default 120,000 ms) |
| `evidence_timestamped_in_future` | A reading ahead of the evaluation time |
| `inadmissible_provenance` | A `proxy`, `context_only` or `unavailable` input tried to score |
| `paper_risk_fully_capped` | The rulebook resolved the paper risk cap to zero |

The emit floor, deadband and staleness bound are **policy choices, not measured
facts**. They are recorded on every decision and bound into the evidence
digest, so a stored signal can be re-read against the policy that produced it.

## Replay and idempotency

Each decision carries a SHA-256 `evidence_digest` over the catalog digest, the
rulebook digest, the admission policy, and each contributing feature's id,
observation time, score and quality. Identical evidence yields an identical
digest; feature ordering does not affect it. `opportunities.signal_id` carries
a UNIQUE constraint and the insert uses `ON CONFLICT DO NOTHING`, so a
redelivered stream message cannot create a second opportunity.

## Mathematics in plain English

- `weighted_score` is `sum(weight x quality x score) / sum(weight x quality)`,
  between -1 and +1. It ranks how well conditions suit a playbook. It is not a
  probability that a trade wins.
- `data_coverage` is `sum(weight x quality)`: how much of the rulebook's total
  block weight had admissible evidence behind it. It describes evidence
  availability only.
- `paper_risk_multiplier` is a policy cap on paper position size. A reduction
  is a rule we chose, not a prediction.
- The `deadband` is a band around zero inside which a score counts as no
  direction, so noise near zero cannot manufacture a long or short.
- `hl_return_1h_pct` is `(mark_now - mark_anchor) / mark_anchor x 100`, a
  percent change. The anchor is the most recent stored mark price at or before
  one hour ago.

## When the first admitted opportunity can occur

Coverage today is `0.30 x q_return + 0.125`. The second term is the liquidity
block: two of its four admitted features are ready, so `0.25 x 0.5`. The first
term is price/volatility, whose only generically-admitted feature is the
one-hour return, so the block's quality equals that feature's quality:
`min(history_count / 168, 1) x freshness`.

Crossing the 0.30 emit floor therefore needs `q_return >= 0.583`, which is 98
history points. At 60-second sampling that is 98 minutes of accumulated return
history — not the 30 points that merely allow it to normalize.

This is worth writing down because it is easy to misread an hour of refusals as
a broken pipeline. It is the emit floor doing its job while evidence
accumulates.

## Tests

Run from the checkout root with `PYTHONPATH` set per service.

- `tests/test_paper_signal.py`: 19 passed (plus 3 subtests).
- `tests/test_regime_paper_pipeline.py`: 13 passed.
- `services/market-data/tests`: 35 passed.
- `tests/test_market_features.py`, `test_regime_weights.py`,
  `test_regime_lab.py`, `test_contract_compat.py`: 33 passed.
- `services/state-api/tests/test_integration_pipeline.py`,
  `test_regime_lab.py`: 8 passed.
- `services/state-api/tests/test_main.py`: 20 passed, 3 failed.

`services/state-api/tests/test_main.py` has four failures in
`test_get_opportunities`, `test_preview_action`, `test_preview_action_blocked`
and `test_execute_action`. These were confirmed pre-existing by stashing this
slice's only state-api change and re-running: the same four fail either way.

`test_planned_feature_is_unavailable_even_with_values` was retargeted from
`hl_return_1h_pct` to `verified_external_event_risk`, which is still `planned`.
A companion test now asserts the return feature is admitted, so a future
regression that re-gates it fails loudly.

The Windows wall-clock assertion recorded as intermittently failing on
2026-09-02 passed in this run. It remains timing-dependent.

## The outage that interrupted this, and what it taught

Partway through, the pipeline stopped producing for about an hour while every
component reported healthy. Redis reached its 160 MB ceiling under a
`noeviction` policy, so every market-data write was rejected; polling continued
to succeed, the healthcheck kept returning 200, and Docker kept reporting
`Up (healthy)`.

The cause was `x:market.norm`, an unbounded stream holding 181,683 entries and
173 MB — and its consumer group had `last-delivered-id 0-0`, meaning nothing had
ever read a single entry. `read_norm_stream` and `ack_norm` exist and are called
from nowhere; the snapshotter builds snapshots in-process. It was pure
write-only exhaust.

Fixed by adding `maxlen` bounds to all three stream writes (20,000 raw and
normalized, 5,000 alerts, all environment-configurable) and trimming the live
stream to 20,002 entries, which took memory from 160.02 MB to 28.93 MB. Polling
resumed within seconds.

Three points worth carrying forward:

- **A healthcheck must assert the job, not the port.** This one asked whether
  the HTTP server answered. It did, throughout. The service's actual job — keep
  fresh observations flowing — had stopped an hour earlier. A freshness
  assertion would have caught it immediately.
- **Correct local behaviour does not compose into visible global behaviour.**
  Redis refused writes rather than losing data, the poller caught its error
  rather than crashing, normalization refused to score stale readings, and the
  admission gate refused to emit on zero coverage. Every decision was right, and
  the sum was a system that looked fine and did nothing.
- **A refusal must name its cause.** The stored reason codes did distinguish the
  two situations — 288 refusals fired all four gates at once, the signature of a
  dead pipeline, versus 169 firing only `coverage_below_emit_floor`, the healthy
  accumulating case. But that required reading a *combination* rather than a
  name. A dedicated `source_unavailable` reason would say it outright, and is
  the recommended next refinement to this module.

The outage also carved a 62-minute hole in the mark-price history, which landed
on the one-hour return's anchor point. The feature correctly refused rather than
widening its comparator across the gap and reporting a "one-hour return" that
actually spanned two hours. An outage costs not only its own duration but every
derived value whose look-back window still overlaps the hole.

## Known-unresolved, carried forward

- `tests/test_core_scorer.py` cannot be collected: a repository-root `main.py`
  shadows the service module. Pre-existing and untouched by this slice.
- `hl_spread_bps` and `hl_buy_impact_5k_bps` report `unavailable` because their
  values are near-constant, so the median absolute deviation is zero and the
  robust z-score is undefined. This is honest refusal, not a defect, but it
  means the `liquidity` block usually rests on depth and imbalance alone.
- Refusal rows are unbounded. One verdict per symbol per 60 s cycle is roughly
  4,300 rows a day across three symbols, each carrying a full evidence blob.
  That audit trail is deliberate, but it needs either retention or
  digest-based deduplication before it runs for long. Deduplicating was left
  out of this slice on purpose: collapsing repeated refusals would also erase
  the record that the system checked at a given time, which is a semantic
  decision rather than a cleanup.
- `core-scorer` and `fusion-engine` were started for this verification, but
  their inspector probes were not configured. `PIPELINE_CORE_SCORER_URL`,
  `PIPELINE_FUSION_ENGINE_URL` and `PIPELINE_INGEST_GATEWAY_URL` remain empty
  by default, so the Integration Pipeline page still reports both as not
  configured even though they are running. Wiring those probes is a separate
  deliberate step.

## Boundaries observed

`DRY_RUN` and `EXECUTION_ENABLED` were not changed. `exec-hl-svc` was not
started. No wallet was connected, no order was submitted, no credential was
read or written, and the canonical ChaseOS vault was not touched. No push,
merge or deployment occurred. Hyperliquid remains the only venue.
