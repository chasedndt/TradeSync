# Measurement hardening, part 1: the library core

Date: 2026-09-11
Scope: `libs/tradesync_core/tradesync_core/{entry_regime,independence,edge_evidence}.py`
and their tests. Slice 3 of the delivery sequence in
[the 2026-09-09 review](../REVIEW_20260909_USABILITY_AND_WALLETS.md).

Pure library code. Nothing is wired into a service yet, no endpoint changed, no
gate moved. **The live `/state/outcomes/by-regime` endpoint still uses the
methods criticised below until part 2 lands.**

## What was wrong

Codex's review of 2026-09-09 found three flaws in the skill measurement built
on 2026-09-08. All three are real.

1. **The regime label used hindsight.** Each hour was labelled rising or falling
   from the average forward return of that hour's own outcomes — the returns
   then being scored. Nobody could have known that label when a signal fired,
   and it puts the outcome inside the grouping meant to explain it. The regime
   split in the 2026-09-09 handover is descriptive, not a prospective result.
2. **Independence was estimated, not measured.** Effective sample size was
   elapsed span ÷ horizon × symbols. That counts windows across collection gaps
   that were never observed, and treats BTC, ETH and SOL as independent when
   they move together.
3. **"Significant" meant either sign.** The flag cleared at |skill| > 2 SE, so a
   strongly *negative* result also read as significant. Nothing was net of
   costs, nothing was held out, and six cells were tested at once with no
   allowance for that.

The handover also overstated its conclusions. "Indistinguishable from chance"
and "a real edge does the opposite" are too strong: failing to find an edge does
not show there is none, and a real but noisy effect can shrink as data grows.
The fixed runtime estimates were rough uncertainty widths, not a power
calculation. **The defensible conclusion is unchanged and narrower: no
demonstrated edge.**

## What replaces it

### `entry_regime.py` — a regime knowable at entry

The trailing one-hour return, from candles that had **fully closed** before the
signal. A candle that opened before the signal but closed after it holds a
post-decision price and is excluded. Both the covered span and the candle count
must be at least 90% complete, because the span alone accepts two candles an
hour apart with nothing between them. Gaps are `unknown`, never interpolated.

The signal's own directional features include a trailing return, so the
rising/falling split and the call are related by construction. That is fine for
this purpose — skill is measured against the base rate of a guesser with the
same bias — but it means the split answers "does the signal add anything beyond
the trend it fired into", not "is the regime predictive".

### `independence.py` — counted, not estimated

- `non_overlapping` selects the largest set of observations whose windows do
  not overlap. With equal-length windows, taking the earliest each time is
  optimal, so the count is not understated by the method.
- `independent_counts` reports it per symbol (generous) and with all symbols in
  one stream (conservative). The pooled count sets the error.
- `block_bootstrap_skill_se` resamples whole time blocks one horizon long with
  every symbol kept together inside a block, so both window overlap and
  cross-symbol correlation are carried into the error. Seeded; `None` with fewer
  than two blocks, because resampling one block has no variation to measure.

### `edge_evidence.py` — three verdicts, never one

| Verdict | Means | Does not mean |
|---|---|---|
| `detectable` | \|z\| ≥ 2, either sign | that anything is good |
| `positive_skill` | skill > 0 at one-sided 2.5%, Holm-adjusted across every cell assessed together, and z ≥ 2 | that it pays |
| `economic_edge` | positive skill and a positive mean return after stated costs | trading readiness |

`economic_edge` is `None` — not `False` — when no costs are supplied: an uncosted
edge cannot be declared either way. `CostAssumptions` has no defaults and
requires a `source`, so a cost figure can never appear unexplained. The standard
error used is the larger of the pooled-binomial and block-bootstrap errors. A
chronological holdout (the latest 30%, never shuffled) is reported beside the
in-sample skill, with a note when they disagree in sign.

Every result carries `"readiness": "descriptive evidence only; not trading readiness"`.

## Verification

29 tests across `tests/test_entry_regime.py`, `test_independence.py` and
`test_edge_evidence.py`, all passing. Among them:

- **The 2026-09-09 false positive, reproduced.** Forty verdicts from three
  symbols inside about five hours at a 240-minute horizon: skill −0.22, which
  the old independence assumption scores beyond −2 SE. Corrected, it is two
  pooled independent windows and not detectable.
- A candle still open at entry is shown to flip the label if used, and is not.
- A ten-minute sample, an outage, and ten more minutes counts as two windows,
  not the seventeen the span estimate would claim.
- A strongly negative skill is `detectable` and never `positive_skill`.
- p = 0.02 passes alone but fails among six cells; a strong p = 0.0001 still
  passes.
- A signal right nine times in ten on moves too small to cover costs has
  positive skill and **no** economic edge.

Each key rule was then broken on purpose to confirm its test catches it. 6 of 7
were caught. The seventh (letting `abs(z)` stand in for `z`) cannot be caught
because negative skill is independently blocked by its one-sided p-value near 1
— the behaviour is identical either way. A further test pins the rule that line
does enforce: a cell at z = 1.98 is neither detectable nor positive, and that
test fails when the rule is removed.

## Not done yet — part 2

Blocked on free memory and on Codex finishing its uncommitted work in
`services/state-api/app/main.py`:

1. Migration: persist the entry regime per opportunity.
2. The outcome job computes it once, from the candles it already fetches.
3. `/state/outcomes/by-regime` moves to entry regimes and `assess_cells`, and
   stops reporting the old `significant` flag.
4. A sourced cost file (Hyperliquid's published fee schedule, dated) and
   per-observation funding from the recorded funding history.
5. Cockpit shows the three verdicts separately.

Until then, treat every regime-split skill figure published before 2026-09-11
as a hindsight description.
