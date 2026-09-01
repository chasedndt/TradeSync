# Regime Lab API Contract

## Purpose

The private Regime Lab is an operator-learning and paper-research surface. It
connects the same Python calculations used by replay code to visible controls
without giving the browser activation, approval, wallet, or execution authority.

## Read model

`GET /state/regime-lab/overview?venue=hyperliquid&symbol=BTC-PERP`

Returns the immutable baseline and catalog identities, current source status,
all 17 feature gates, backend-normalized values, backend-aggregated blocks,
baseline evaluation, and current learning questions.

An unavailable market-data service does not create fixture values. The endpoint
still returns configuration and 17 explicit unavailable records so the learning
surface can operate honestly in degraded development mode.

## Stateless evaluation

`POST /state/regime-lab/evaluate`

The operator supplies an experiment name, challenger version, testable
hypothesis, evaluation window, expected effect, all five weights, the weight-sum
answer, and a written coverage explanation. The API fetches market evidence
itself; browser-supplied block scores and quality are not accepted.

Deterministic gates:

- weights sum to `1.0` within `1e-9`;
- one block cannot exceed `0.40`;
- the arithmetic answer is `1.0`;
- the reflection has at least 20 non-whitespace characters.

The service records only that reflection exists. It does not claim free text is
mathematically correct without human review.

## Draft persistence

`POST /state/regime-lab/experiments` repeats evaluation server-side and saves
only when both learning gates pass. Configurations are immutable by digest, and
the experiment is stored as `draft`. PostgreSQL failure returns `503`; there is
no browser-storage, Redis, or untracked-file fallback.

`GET /state/regime-lab/experiments` lists recent drafts. There is deliberately
no activation endpoint.

## Market-data inputs

- `GET /features/{venue}/{symbol}` returns current admitted measurements.
- `GET /feature-history/{venue}/{symbol}/{feature_id}?window=7d` returns
  cadence-governed history.

One latest observation is retained per sampling bucket. The browser never
samples or normalizes features.

## Degraded development mode

`STATE_API_DEGRADED_START=true` permits configuration, learning, and stateless
evaluation when PostgreSQL is unavailable. This is not Tier A readiness.
Database-dependent endpoints remain blocked, and Compose does not enable it by
default.
