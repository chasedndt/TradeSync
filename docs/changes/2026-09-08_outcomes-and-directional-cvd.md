# Outcome Measurement and Directional CVD

Date: 2026-09-08

Branch: `codex/2026-09-01-dashboard-overhaul`

## Repo-truth delta

Two gaps closed, both identified as the top obstacles in
[the roadmap state](../ROADMAP_STATE_2026-09-08.md).

Before: the system produced paper opportunities with no way to tell whether any
of them were any good, and direction rested on a single feature.

After: every opportunity is measured against what the market subsequently did,
and a second genuinely directional feature is admitted.

## 1. Outcome measurement

`libs/tradesync_core/tradesync_core/outcomes.py` measures forward returns at
15, 60 and 240 minutes for each recorded opportunity, with maximum favourable
and adverse excursion.

Deliberately conservative:

- A horizon that has not closed is `pending`, never scored early on a partial
  window.
- A gap in candle coverage is reported as `insufficient_candles`, never
  interpolated across.
- The entry is the first candle *at or after* the opportunity timestamp, so a
  measurement can never use a price that existed before the decision.
- `signed_return_pct` flips sign for SHORT, so a short that fell reads positive.
  That is the "was the call right" column.

Storage is migration `004_opportunity_outcomes.sql`, unique per
`(opportunity_id, horizon_minutes)` so re-measuring updates in place and a
restart mid-pass loses nothing. The job runs in `core-scorer` on its own
five-minute cadence, kept separate from the producer so a slow measurement can
never delay or influence a live verdict. Exposed at
`GET /state/outcomes/summary`.

### First track record, and why not to trust it

| Horizon | Measured | Hit rate | Mean signed return |
|---|---|---|---|
| 15m | 37 | 70.3% | +0.063% |
| 60m | 27 | 11.1% | -0.268% |

This is **not** evidence of an edge, and the divergence is not a finding:

1. The observations are not independent. Most of the sample predates duplicate
   suppression, when a fresh opportunity was minted every 60 seconds for an
   unchanged market state.
2. It covers roughly two hours of a single declining regime. A short horizon
   catching bounces while a longer one catches the trend is exactly what one
   downtrend looks like.
3. Settling it requires fixed-window replay across regimes, which does not exist
   yet.

The delivered value is that the number now exists and can be argued with. Every
earlier tuning decision was unfalsifiable.

## 1b. The track record was misleading until it had a baseline

As the sample grew from 37 to 115 measurements the headline numbers moved
sharply — 15m from 70.3% to 53.9%, 60m from 11.1% to 32.7% — which was the first
sign the early figures were small-sample artefacts.

Breaking them down by direction showed something worse:

| Direction | Horizon | n | Hit rate | Market's own move |
|---|---|---|---|---|
| LONG | 60m | 66 | 10.6% | -0.233% |
| SHORT | 60m | 42 | 66.7% | -0.178% |

The market fell in nearly every window measured. LONG calls lost because price
fell; SHORT calls "won" because price fell. **A hit rate is not interpretable
without the base rate the market itself set.** As published, the endpoint was
reporting a sustained downtrend as though it were ability.

`summarise` and `GET /state/outcomes/summary` now report, alongside the hit
rate:

- `market_up_rate` — how often price actually rose over exactly these windows.
- `long_share` — the direction mix of the calls.
- `expected_hit_rate` — `long_share x up + (1 - long_share) x (1 - up)`, what a
  caller with this bias and no skill whatever would score.
- `skill_vs_baseline` — the difference, and the only figure here that gestures
  at ability.

Measured on 2026-09-08:

| Horizon | n | Hit | Market up | Long share | Expected | Skill |
|---|---|---|---|---|---|---|
| 15m | 115 | 53.9% | 49.6% | 61.7% | 49.9% | **+4.0 pts** |
| 60m | 110 | 32.7% | 20.0% | 61.8% | 42.9% | **-10.2 pts** |

Read carefully:

- **+4.0 points at 15m is not an edge.** With n=115 the standard error of a
  proportion is 4.7 points even assuming independence, so this is 0.9 SE — noise.
- **-10.2 points at 60m is 2.1 SE** and therefore suggestive, but the
  observations overlap heavily, so the effective sample is far smaller than 110
  and the true standard error far larger. It is a hypothesis worth testing, not
  a finding.
- The system was 61.8% LONG while the market rose 20% of the time. Even after
  crediting it for that bias it did worse than chance at the longer horizon.

Nothing here is conclusive from one regime. What changed is that the numbers can
now be wrong in a visible way instead of flattering the system.

## 2. Directional CVD

`hl_direct_cvd` is promoted from `unavailable` to `implemented` in catalog
**1.3.0**, digest `74b858cf96e4e696`. There are now **two** admitted directional
features rather than one.

### The sign convention was measured, not assumed

Hyperliquid's websocket documentation defines a `side` field for trades but
never says what its values mean. Getting it backwards would invert every
direction the system produces, so it was determined against the live order book:

```
side "B" -> 137 trades at/above the ask,   4 at/below the bid
side "A" ->  29 trades at/above the ask, 137 at/below the bid
```

`B` is an aggressive buy, `A` an aggressive sell. An earlier attempt to infer
this by correlating signed flow against price movement over ten-second buckets
returned 56% agreement — a coin flip — and was correctly discarded as too noisy
to conclude from. The book comparison is recorded in the module docstring and
the catalog caveats so it is not re-litigated from memory.

### Implementation

- `services/market-data/app/trade_flow.py` — pure windowed accumulation. CVD is
  signed taker notional over a rolling five-minute window, not a running total
  since startup: a cumulative figure drifts without bound and is not comparable
  across restarts, which would make its z-score meaningless.
- `services/market-data/app/trade_stream.py` — websocket transport with
  exponential backoff, kept separate so the mathematics stays testable.
- The value is attached to the snapshot as `derived.cvd_window_usd` and read by
  the stateless extractor, matching how the one-hour return is handled.

**Absent, not zero, until trades are observed.** Zero is a real reading meaning
balanced flow; "nothing seen yet" is a different claim and must not be
presented as balance.

Verified live: BTC-PERP -$83,665 over five minutes on 38 trades, ETH-PERP
+$542,095 on 39, SOL-PERP +$5,692 on 33.

### A side effect worth knowing

Admitting a second directional feature **halved directional coverage to 0.50**
while CVD collects its first 30 history points, which sits exactly on
`minimum_directional_coverage`. Signals continue, but the margin is a knife
edge for roughly thirty minutes after any restart that clears the CVD window.
Once CVD normalizes, coverage returns to 1.0 and the floor is comfortable.

This is the general shape of adding a directional feature: coverage dips before
it improves, because the denominator grows immediately and the numerator only
grows once history accumulates.

## Tests

- `tests/test_outcomes.py`: 17 passed, including that a SHORT which fell reads
  positive, that pending windows are never scored early, and that prices from
  before the decision can never become the entry.
- `services/market-data/tests/test_trade_flow.py`: 13 passed, asserting the sign
  convention explicitly and that an unobserved symbol reads None rather than 0.
- `services/market-data/tests`: 61 passed overall.
- Shared suites: 72 passed.

`tests/test_migrations.py` asserted a hard-coded migration roster
`["001","002","003"]` and failed on any addition. It now asserts the invariants:
contiguous numbering from 001, no duplicates, ordered, every file with a
parseable UP section. Same brittleness class as the `__all__` count test fixed
on 2026-09-07.

A robustness bug was caught by its own test: a non-dict entry in a trade batch
raised `AttributeError` and discarded the rest of the batch. The stream is
external input, so one malformed entry is now skipped instead.

## Boundaries observed

`DRY_RUN=true`, `EXECUTION_ENABLED=false` unchanged. No wallet, no order, no
credential, no deployment, no public exposure. Outcome rows are measurements of
market movement after a recorded observation; no position ever existed.
