# Market Feature Contract v1

## Purpose

`market_feature_v1` is the gate between raw/derived market measurements and the Regime Rulebook. It prevents a field from becoming “a signal” merely because it exists in a payload.

Every feature definition must state:

1. stable feature ID;
2. source and authority;
3. observed, derived, proxy, context-only, or unavailable provenance;
4. unit;
5. exact comparator;
6. lookback and minimum history;
7. ordinary, robust, or no normalization;
8. direct, inverse, playbook-specific, context-only, or unavailable score mode;
9. freshness and stale thresholds;
10. missing-data behavior, decision role, and caveats.

The canonical paper-shadow catalog is `config/features/market-feature-catalog-v1.json`.

## Current source truth

The catalog contains 17 feature definitions. “Implemented” means the underlying field or transparent derivation exists in the current Hyperliquid adapter/snapshot path. It does not mean it is already persisted to the new feature tables or connected to the active scorer.

| Feature group | Current truth | Scoring authority |
|---|---|---|
| mark, funding, OI, rolling 24h volume | observed from Hyperliquid | eligible only under declared feature semantics |
| spread, depth, impact, imbalance | transparently derived from Hyperliquid L2 | eligible with derived provenance |
| funding APR | display derivation | not separately scored, preventing double-counting |
| Hyperliquid mark/oracle premium | upstream field exists; versioned feature path planned | not active |
| 1h return | durable aligned price history still planned | not active |
| OI-based liquidation estimate | proxy | never scoring eligible |
| direct liquidation flow and direct CVD | unavailable in current adapter | unavailable, never substituted |
| Coinbase premium and ETF net flow | no admitted source | unavailable/context-only |
| verified external event risk | future context registry | risk cap only, never directional score |

CoinGecko, DefiLlama, and FRED remain context-only under the provider matrix. They cannot quietly fill an authoritative market feature.

## Feature-value input

```json
{
  "feature_id": "hl_spread_bps",
  "symbol": "BTC-PERP",
  "timeframe": "snapshot",
  "evaluated_at_ms": 1767297601000,
  "current": {
    "ts": 1767297600000,
    "value": 0.9,
    "source_event_id": "evt-spread-current"
  },
  "history": [
    {"ts": 1767297480000, "value": 0.42}
  ]
}
```

Rules:

- history timestamps are strictly increasing and unique;
- every history timestamp is earlier than the current timestamp;
- the current observation is not included in its own comparison window;
- the evaluator timestamp cannot precede the observation;
- values and statistics must be finite;
- insufficient history, zero dispersion, staleness, planned state, or unavailable state cannot produce a generic score.

These constraints block a basic form of look-ahead bias.

## Sampling cadence

Every catalog feature declares `sampling_interval_ms`. The market-data service
retains at most one latest value inside each sampling bucket, preventing a
five-second poll from masquerading as five independent hourly funding samples.
Normalized feature history is retained for seven days in a dedicated Redis
series. Redis remains a rebuildable operating history; PostgreSQL observation
records remain the intended durable evidence boundary.

## Ordinary normalization

For historical values `x_1 ... x_n`:

```text
historical_mean = sum(history) / n

sample_standard_deviation =
  square_root(sum((x_i - historical_mean)^2) / (n - 1))

z_t = (current_value - historical_mean) / sample_standard_deviation
```

The denominator uses `n - 1`, so this is sample standard deviation. The implementation uses Python's `statistics.stdev`.

## Robust normalization

```text
historical_median = middle historical value
MAD = median(abs(x_i - historical_median))
scaled_MAD = 1.4826 * MAD
robust_z_t = (current_value - historical_median) / scaled_MAD
```

Robust normalization is used initially for spread, depth, impact, volume, imbalance, funding, and premium candidates because occasional extreme observations can pull the ordinary mean and standard deviation sharply.

Both methods then use:

```text
normalized_value = tanh(z_t / 2)
```

The catalog controls the selected method; `compare-methods` exists for education and paper analysis, not silent runtime overrides.

## Score modes

- `direct`: higher normalized value means higher block contribution.
- `inverse`: higher raw/normalized value means worse suitability, so the sign is reversed. Spread and impact use this mode.
- `playbook_specific`: store the normalized observation but do not emit a generic direction score. Funding, OI, and volume use this because their meaning depends on price, side, and other evidence.
- `none`: base/display field only.
- `context_only`: can inform explanations or risk overlays but cannot score.
- `unavailable`: reserved definition with no admitted input.

## Data quality

Book 1 uses two objective components:

```text
sample_factor = min(history_count / lookback_points, 1)
data_quality = sample_factor * freshness_factor
```

Freshness is piecewise:

```text
1                                  when age <= fresh threshold
0                                  when age >= stale threshold
1 - (age - fresh) / (stale-fresh) otherwise
```

This linear decay is a provisional design choice. Data quality is not “probability the trade wins.” It only describes how much of the requested history is present and how old the current observation is.

Provenance remains a gate rather than an arbitrary numerical haircut: proxy/context/unavailable features cannot score at all.

## Funding unit correction

Hyperliquid funding is paid hourly. Therefore, when `h24` is the mean hourly decimal funding rate over the last 24 hours, simple annualization is:

```text
annualized_24h = h24 * 24 hours_per_day * 365 days_per_year
```

For `h24 = 0.00015`:

```text
0.00015 * 24 * 365 = 1.314
```

As a percentage, `1.314` means `131.4%` simple annualized rate. It is not a compounded forecast and does not mean that rate will persist.

The previous `h24 * 365` implementation omitted the 24 hourly periods per day and is corrected by this contract. The old Phase 3C sample value `13.14` was also numerically inconsistent and is corrected to `1.314`.

Official references:

- [Hyperliquid funding](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding)
- [Hyperliquid perpetual info endpoints](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)

## Persistence

Migration `ops/migrations/003_market_features.sql` defines:

- `market_feature_catalogs` for versioned catalog JSON and digest;
- `market_feature_observations` for one durable value with source event lineage;
- `market_feature_normalizations` for history window, method, center, dispersion, z-score, bounded value, quality, status, and reason.

The migration is authored but not automatically applied. PostgreSQL remains durable truth; Redis may publish a committed paper-shadow result but cannot replace it.

## CLI

```powershell
$env:PYTHONPATH = "libs\tradesync_core"

python -m tradesync_core.market_features validate-catalog `
  config\features\market-feature-catalog-v1.json

python -m tradesync_core.market_features normalize `
  config\features\market-feature-catalog-v1.json `
  fixtures\features\spread-robust-normalization.json

python -m tradesync_core.market_features compare-methods `
  config\features\market-feature-catalog-v1.json `
  fixtures\features\spread-robust-normalization.json

python -m tradesync_core.market_features validate-compatibility `
  config\features\market-feature-catalog-v1.json `
  config\regime\regime-rulebook-v1.json
```

## Activation boundary

This contract is paper-shadow infrastructure. It does not alter the legacy regime classifier, opportunities, paper-risk decisions, approvals, or execution.

Canonical diagram: [market-feature-normalization.mmd](../diagrams/market-feature-normalization.mmd)
