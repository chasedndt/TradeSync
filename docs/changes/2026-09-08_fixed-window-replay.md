# Fixed-Window Replay

Date: 2026-09-08

Branch: `codex/2026-09-01-dashboard-overhaul`

## Repo-truth delta

An unfinished **Phase 2** roadmap deliverable — "a Regime Lab where the operator
can ... replay a fixed paper window" — is now implemented and has returned its
first result.

Before: weights could be changed but never evaluated, because the market moved
between one configuration and the next. Every tuning decision was
unfalsifiable.

After: champion and challenger are scored on byte-identical recorded evidence,
so any difference is attributable to the configuration alone.

## Design

`libs/tradesync_core/tradesync_core/replay.py`, pure and shared with the live
path. Two rules keep it honest:

- **It reuses the production functions.** `evaluate_blocks` and
  `decide_paper_signal` are the same calls the producer makes. A parallel replay
  implementation would eventually disagree with production, and the replay would
  then be measuring itself.
- **It never re-derives evidence.** Block scores and qualities are read from
  what was recorded at decision time, not recomputed from today's feature
  history. Recomputing would leak information that did not exist when the
  decision was taken.

Two subtleties worth recording:

- **Zero-quality blocks stay absent.** A block that contributed nothing must not
  be resurrected by a challenger that happens to weight it heavily, or replay
  would invent evidence.
- **Freshness is judged against the original evaluation time.** Replaying the
  staleness gate against the current clock would reject every historical case
  and measure the age of the sample rather than the rulebook.

Exposed at `POST /state/regime-lab/replay`. Paper only; replay cannot activate a
rulebook or place an order.

## First result: 124 cases, 0 unreplayable

Window: 24 hours, 60-minute horizon, all three symbols.

| Configuration | Admitted | Skill vs baseline |
|---|---|---|
| **Champion** (pv 0.30 / liq 0.25) | 90 | **-7.3 pts** |
| Heavier on the blocks holding evidence (0.40 / 0.40) | 90 | -7.3 pts — *0 decisions changed* |
| Slightly stricter (0.25 / 0.20) | 75 | **-11.0 pts** |
| Stricter (0.20 / 0.20) | 54 | **-14.1 pts** |
| Weight moved to the three empty blocks | 0 | n/a — system switches itself off |

### Replay validates itself

The champion's replayed skill of **-7.3 pts** closely tracks the independently
measured live figure of **-10.2 pts** at the same horizon. Replay reproducing
the live result from stored evidence is the check that the replay is faithful.

### The finding: selectivity makes it worse, monotonically

As the emit floor bites harder the system admits fewer cases (90 → 75 → 54) and
skill degrades every step (-7.3 → -11.0 → -14.1).

**The cases the system is most confident about are the ones it gets most
wrong.** That is the signature of an anti-predictive signal rather than a merely
noisy one. Pure noise would leave skill roughly flat near zero as selectivity
rose; instead selectivity concentrates the error.

### The consequence: weight tuning cannot fix this

Every configuration tested either changed nothing or made things worse:

- Moving weight *between* the two blocks that hold evidence changed **zero**
  decisions. Admission is insensitive across that range.
- Moving weight *toward* the empty blocks only reduces coverage, making the
  system more selective and therefore worse, until it admits nothing at all.

This follows from the direction/suitability split of 2026-09-07: weights now
govern **admission**, not direction. Direction comes solely from
catalog-directional features. So no rulebook weighting can repair a directional
signal — **the lever is not in the rulebook.**

The lever is more and better directional evidence. Today that is
`hl_return_1h_pct` and `hl_direct_cvd`; `coinbase_premium_bps` is marked
directional and remains unavailable.

## What this does not establish

One window, one regime, 124 cases with heavily overlapping observations. The
result is robust *to configuration* within this window, which is a different and
weaker claim than being robust in general.

Specifically **not** concluded: that the signal should be inverted. Flipping a
sign because it lost money over a single falling afternoon is curve-fitting on a
sample of one regime, and would be the exact error this tool exists to prevent.

Settling it needs a replay across a rising window, which requires the evidence
store to span one.

## Tests

`tests/test_replay.py`: 17 passed, including that a challenger cannot resurrect
a zero-quality block, that direction still comes only from directional evidence
however the weights move, that historical cases are not rejected as stale, and
that identical rulebooks produce a zero delta.

`services/state-api/tests`: 16 passed on the pipeline and regime-lab suites.

## Boundaries

`DRY_RUN=true`, `EXECUTION_ENABLED=false`. No rulebook was activated. Replay is
read-only over recorded evidence and cannot promote a challenger.
