# Regime Lab API Contract

## Purpose

The private Regime Lab is a paper-research surface. It shows the live feature
evidence behind the baseline rulebook and judges challenger weights by
replaying the paper scorer's stored decisions. The browser has no activation,
approval, wallet, or execution authority, and there is no activation endpoint.

## Read model

`GET /state/regime-lab/overview?venue=hyperliquid&symbol=BTC-PERP`

Returns the immutable baseline and catalog identities, market-data source
status, one result per catalog feature with its backend normalization,
backend-aggregated blocks, the baseline evaluation, and `health`.

Each feature result carries, besides its value, normalization and score:

- `feed`: where its reading comes from (Hyperliquid order book, Hyperliquid
  market context, Hyperliquid trades, Coinbase, Binance, GDELT, or no live
  adapter);
- `age_ms`, `fresh_after_ms`, `stale_after_ms` and `freshness` (`fresh`,
  `stale`, `missing`), judged against the feature's own catalog limits;
- `coverage_reason`, exactly one of `usable` (a fresh reading with a
  z-score), `stale`, `flat`, `collecting_history`, `display_only`,
  `unavailable`. "Fresh" always means a reading within its stale limit, so a
  fresh reading can still be flat, display only or collecting history.

`normalization.method` is the method actually used. A tick-valued feature whose
median absolute deviation is zero falls back to the ordinary z-score and records
`requested_method` and `fallback`. A window of identical values stays
unavailable with the reason `flat: every recent value identical`. Which
features may score is decided by the catalog alone.

`health` reports market-data status, counts the coverage reasons, counts the
fresh readings (the only ones called live), and gives each feed its newest
reading's age against the tightest stale limit among its features.

An unavailable market-data service does not create fixture values: every
feature is returned as unavailable with its reason.

## Judging a challenger by replay

`POST /state/regime-lab/replay`

```json
{
  "hours": 168,
  "horizon_minutes": 60,
  "symbol": null,
  "challenger_weights": {
    "price_volatility": 0.35, "liquidity": 0.20, "positioning": 0.20,
    "spot_premium": 0.15, "macro_flows": 0.10
  },
  "challenger_version": "1.0.0-c1"
}
```

- `hours` is 24, 168 or 720; `horizon_minutes` is 15, 60 or 240; a null
  `symbol` replays every market.
- Weights must name all five blocks, sum to `1.0` within `1e-9`, and no block
  may exceed `0.40`. A violation is `422` with the reason.

The scorer's recorded decisions in the window, admitted and refused, are
re-decided under the baseline and the challenger with the live decision code.
Weights change admission, not direction. The response counts:

- `decisions`: replayed, changed, admissions gained, admissions lost, direction
  flips;
- `outcomes`: over decisions with a measured outcome at the horizon (those that
  opened a paper opportunity), each rulebook's admitted set with its sample
  count, hit rate, the hit rate its long/short mix would score by luck, skill,
  and mean signed return;
- `window`: decisions in the window, the sampling bucket for the decision
  counts (one decision per market per 1, 10 or 30 minutes; every decision with
  an outcome is kept), from when refused decisions are still available (they
  are kept in full for seven days) and how many rows could not be replayed.

Only the evidence a replay needs is read. Queries carry a 45-second timeout
that answers `504` with a reason, and the replay runs in a worker thread.

## Draft experiments

`POST /state/regime-lab/experiments` takes `name`, `version`, `hypothesis` (at
least 20 characters), `weights`, `hours`, `horizon_minutes` and `symbol`. It
runs the same replay on the server and stores the hypothesis, the challenger
configuration and the replay judgement as an immutable `draft`. Configurations
are stored once by digest; a version already saved with another configuration
answers `409`. PostgreSQL failure returns `503`; nothing is kept in browser
storage, Redis or files.

`GET /state/regime-lab/experiments?limit=8` lists recent drafts with their
hypothesis, weights, window and replay counts. Drafts saved before replay
judging list without a judgement.

There is no learning gate and no single-snapshot evaluation endpoint.

## Slow statistics

`GET /state/outcomes/skill-gate` and `GET /state/outcomes/evidence-cards` are
served from a measured cache:

- `200` with `status: ready`, `computed_at` and `cache` (age, a 10-minute TTL,
  whether it is stale, whether it is being refreshed, the last error);
- `202` with `status: computing` while a market is measured for the first time;
- `503` naming the error when a first measurement failed.

Measurements run one at a time in a worker thread. The background loop
`outcome_statistics_refresh` re-measures every market requested in the last 30
minutes shortly before its entry expires.

## Market-data inputs

- `GET /features/{venue}/{symbol}` returns current admitted measurements.
- `GET /feature-histories/{venue}/{symbol}?window=7d` returns cadence-governed
  histories for several features in one request.

One latest observation is retained per sampling bucket. The browser never
samples or normalizes features.

The current adapter also exposes Hyperliquid mark price and mark/oracle premium
from `metaAndAssetCtxs`, and seeds the funding window from the available
seven-day venue history at startup. No liquidation proxy is substituted for a
direct liquidation feed.

## Degraded development mode

`STATE_API_DEGRADED_START=true` permits configuration and the overview when
PostgreSQL is unavailable. Replay, experiments and the slow statistics need
PostgreSQL and answer `503` without it. This is not Tier A readiness, and
Compose does not enable it by default.

## Local runtime verification

On 2026-09-02 the bounded Docker stack verified live market-data and State API
health, Cockpit access through `/api/`, Redis feature-history continuity,
transactional PostgreSQL migrations, and draft experiment persistence. The
Cockpit reverse proxy uses Docker's resolver so replacing only the State API
container does not leave it pinned to an obsolete container address. This is
paper-shadow verification only: `execution_authority` remained `false`, and no
wallet, signer, approval, or execution service was started.
