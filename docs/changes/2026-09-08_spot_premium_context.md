# Coinbase Spot Premium

Date: 2026-09-08

Branch: `codex/2026-09-01-dashboard-overhaul`

## Why this feature and not another

Two things were established today rather than assumed:

1. Fixed-window replay showed **weight tuning cannot help** — every rulebook
   configuration either changed nothing or made results worse.
2. The regime-split gate showed the two admitted directional features produce
   calls **indistinguishable from chance** in both rising and falling markets.

So the lever is neither the rulebook nor the thresholds. It is more and better
directional evidence. `coinbase_premium_bps` was the catalog's own named
candidate, and it measures something genuinely different from
`hl_return_1h_pct` and `hl_direct_cvd`, which both derive from Hyperliquid's own
book and tape.

## Shipped context-only first, then promoted

The feature catalog is Hyperliquid-only by construction, and the project
handover gates Coinbase premium behind "separately verified source
availability, timing, provenance and permitted use".

So it landed in catalog **1.4.0** as `provenance: context_only`,
`scoring_eligible: false` — visible in Regime Lab with real values, contributing
nothing. **Admitting a non-Hyperliquid venue to scoring is an operator decision,
not a consequence of the data becoming available.**

The operator then admitted it in **1.5.0**, with live values in hand rather than
a hypothesis. That ordering is the point: the decision was made against observed
alignment quality and real premium magnitudes.

## The timing problem, and how it is handled

A premium computed from two venues sampled at different moments is partly real
and partly sampling noise. `premium_bps` refuses to produce a value when the two
observations are more than 10 seconds apart, rather than reporting the gap as
market structure. Every observation records its actual `alignment_skew_ms` so
the quality of each comparison is inspectable.

Observed skew in practice is far tighter than the bound: 59 ms, 554 ms and
2,854 ms across the three symbols.

Two further choices:

- **Book mid, not last trade.** A single print sits on one side of the spread,
  which would show up as premium that is really just which side traded last.
- **No synthetic pair mapping.** Only symbols with a genuine US spot listing are
  mapped. Inventing a mapping would invent a premium.

## Verified live

```
BTC-PERP  +3.05 bps   (skew 2854 ms)
ETH-PERP  +2.43 bps   (spot 2492.65 vs perp 2492.05, skew 59 ms)
SOL-PERP  +2.89 bps   (spot 103.76 vs perp 103.73, skew 554 ms)
```

At that point Regime Lab reported catalog `1.4.0`, 13 of 17 inputs, and
`coinbase_premium_bps` as `not_normalized` — present, quality 0, contributing
nothing.

## Promoted to scoring by operator decision, catalog 1.5.0

The operator admitted it to the scoring path on 2026-09-08. Catalog **1.5.0**,
digest `c70219370fbc29c8`:

| Field | Was | Now |
|---|---|---|
| `provenance` | `context_only` | `derived` |
| `source_authority` | `context_only` | `external_reference_venue` |
| `score_mode` | `none` | `direct` |
| `scoring_eligible` | false | **true** |
| `normalization` | `none` | `robust_zscore` |
| sampling / lookback / minimum | 0 | 15 s / 120 / 20 |

### The boundary that actually moved

Two whitelists gate scoring, and only the second one matters:

```python
scoring_provenance = {"observed", "derived"}
scoring_authority  = {"authoritative_market", "authoritative_market_derived"}
```

`scoring_authority` is the line between "TradeSync measured it" and "somebody
else said so". Admitting Coinbase required adding a third value, and the value
had to be honest: reusing `authoritative_market_derived` would have described
Coinbase as the venue TradeSync trades on, which it is not and will not be.
`external_reference_venue` says what it is — **a price reference, never a
trading venue.** The catalog's own `venue` field remains `hyperliquid`.

Nothing about this grants an external source approval or execution authority.

### Robust z-score, not ordinary

A premium spikes. An ordinary z-score would let a single dislocation distort the
baseline for a whole session, so the median-based statistic is used instead.

### Two effects, one change

**Directional evidence went from two features to three.** Immediately after
deployment, directional coverage *fell* from 1.0 to 0.667 — the denominator
grows the moment a feature is admitted, while the numerator waits for history.
This is the same shape recorded when CVD was added, and it is worth expecting
rather than debugging.

**The coverage ceiling rose from 0.55 to 0.70.** `spot_premium` is a 0.15-weight
block that had been allocated weight and carried nothing behind it. The rulebook
requires 0.70 for normal paper risk, so the permanent `low_data_coverage` cap
was previously unreachable by construction. It is now reachable — `macro_flows`
is the only block still carrying weight with no admitted feature.

### Tests updated rather than flipped

Two catalog tests asserted the old state. They were rewritten to pin the new
invariant rather than simply inverting a boolean:

- `test_an_external_venue_scores_only_as_a_price_reference` asserts the
  authority is `external_reference_venue` and specifically **not**
  `authoritative_market`, and that the catalog venue is still Hyperliquid.
- `test_an_external_venue_still_cannot_score_on_proxy_provenance` confirms the
  provenance gate still bites for the newly admitted source.
- The proxy exclusion assertion was kept untouched: a proxy may never score,
  whatever else changes.

## Outstanding: Coinbase Market Data Terms

Accessing the Exchange Market Data API binds the user to Coinbase's
[Market Data Terms of Use](https://www.coinbase.com/legal/market_data). Two
clauses bear directly on what was built. This summarises published terms; it is
not legal advice, and the operator should read the full text.

### 1. No redistribution of Market Data *or derived works*

Without prior written consent, Market Data — **or any derived works based on
it** — may not be redistributed, displayed or disseminated to any third party
outside the organisation.

`coinbase_premium_bps` is a derived work: it is computed from a Coinbase quote.

This makes the earlier decision to keep TradeSync **private and single-user**
materially more important than it appeared. That call was made on
signal-distribution and regulatory grounds; it turns out to be a data-licensing
constraint as well. Publishing the premium — or a score derived from it — to a
Discord server or any shared surface would sit squarely inside this clause.

The architecture already enforces the safe posture: no public ingress, no
multi-user surface, no outbound distribution.

### 2. No benchmarks, fair-value prices or valuations, *including internal use*

Market Data and derived works may not be used to create "indexes, fixings or
other benchmarks; generic or fair value prices; or valuations of any investment
product, digital currency... for internal use or otherwise."

This clause needs an operator decision, because it explicitly reaches internal
use. The question is whether a **regime suitability score** taking the premium
as one directional input constitutes a prohibited valuation or benchmark.

Against: the score is not a price, not a fair-value estimate, and not published
as a reference anyone else consumes. It ranks how suitable conditions are.

For caution: the premium feeds a directional score in a system whose purpose is
trading decisions, which is closer to the line than displaying a chart.

### Operator decision, 2026-09-08: keep it scoring

The operator elected to keep the feature in the scoring path. Clause 1 is
satisfied by the private, single-user posture the architecture already enforces.
Clause 2 was accepted on the reading that a suitability score is not a price,
fair-value estimate or published benchmark.

The same question will recur for any future external source, so it should be
settled once rather than per-feature.

### Either posture remains a catalog edit, not a rebuild

1. **Keep it scoring** — catalog 1.5.0, current state.
2. **Revert to display-only** — catalog 1.4.0 behaviour: `provenance` back to
   `context_only`, `scoring_eligible` false. The premium stays visible in Regime
   Lab and contributes to nothing. Costs the 0.70 coverage ceiling and the third
   directional feature, nothing else.

The context-only-first ordering was chosen precisely so this reversal stays
cheap.
## Tests

`services/market-data/tests/test_spot_premium.py`: 11 passed, including that a
crossed book is refused, that misaligned samples produce no premium, and that an
unlisted symbol maps to nothing rather than a guess.

`services/market-data/tests`: 72 passed overall.

## Boundaries

`DRY_RUN=true`, `EXECUTION_ENABLED=false`. Hyperliquid remains the only trading
venue; Coinbase is a read-only price reference, admitted to scoring as
`external_reference_venue` and never as a venue.
