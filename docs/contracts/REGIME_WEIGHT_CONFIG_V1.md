# Regime Weight Configuration v1

## Contract identity

- schema: `regime_rulebook_v1`
- environment: `paper` only
- canonical seed: `config/regime/regime-rulebook-v1.json`
- calculation library: `tradesync_core.regime_weights`

## Required configuration

| Field | Type | Rule |
|---|---|---|
| `rulebook_id` | string | stable family identity |
| `version` | string | unique version; create a new value for every change |
| `status` | string | lifecycle label, initially `draft` |
| `environment` | string | exactly `paper` in v1 |
| `horizon` | string | decision timeframe family |
| `normalization.compression_k` | number | finite and greater than zero |
| `blocks.*.weight` | number | `0..max_single_block_weight` |
| all block weights | number | sum to configured `weight_sum` within tolerance |
| `paper_risk.caps.*` | number | within configured minimum/maximum |
| `config_digest` | derived string | SHA-256 of canonical JSON |

## Score-input contract

```json
{
  "block_scores": {"price_volatility": 0.8},
  "data_quality": {"price_volatility": 1.0},
  "risk_flags": ["external_risk_high"]
}
```

- block scores must be in `[-1, 1]`;
- quality must be in `[0, 1]`;
- omitted blocks have quality zero and appear in `missing_blocks`;
- unknown block names are rejected;
- unknown risk flags cap paper risk at the fail-closed default.

## Output contract

```json
{
  "rulebook_id": "tradesync-intraday-regime",
  "rulebook_version": "1.0.0",
  "config_digest": "sha256...",
  "weighted_score": 0.22,
  "data_coverage": 1.0,
  "paper_risk_multiplier": 0.45,
  "contributions": {},
  "missing_blocks": [],
  "risk_caps_applied": []
}
```

Every persisted output must also include symbol, timeframe, observation time, source event IDs, and playbook-permission results.

## Compatibility and change rules

- changing only values creates a new semantic version within this schema;
- adding/removing required fields or changing calculation semantics requires a new schema version;
- never reuse a version string with a different digest;
- activation is a separate record and does not alter configuration;
- v1 has no live-execution compatibility.
