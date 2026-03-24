# Risk Limits Contract

## 1. Overview
This document defines the risk limits and thresholds enforced by the `RiskGuardian` in `state-api`.

## 2. Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_spread_bps` | 50 | Maximum allowable bid-ask spread in basis points. |
| `min_depth_25bp_usd` | 5000 | Minimum depth within 25bps of mid-price (USD). |
| `max_impact_bps_5k` | 100 | Maximum price impact for a $5,000 order in basis points. |
| `min_liquidity_score` | 0.3 | Minimum acceptable liquidity score (0..1). |
| `margin_stress_threshold` | 0.8 | Max margin usage before blocking new trades. |
| `max_leverage` | 5.0 | Max leverage allowed for a single position. |
| `min_quality` | 60.0 | Minimum opportunity quality score to allow execution. |

## 3. Block Reason Codes

- `SPREAD_TOO_WIDE`: Bid-ask spread exceeds `max_spread_bps`.
- `SLIPPAGE_TOO_HIGH`: Estimated slippage exceeds threshold.
- `DEPTH_TOO_THIN`: Liquidity at top levels is insufficient.
- `LIQUIDITY_TOO_LOW`: Composite liquidity score is below `min_liquidity_score`.
- `MARGIN_STRESS`: Current margin usage exceeds `margin_stress_threshold`.
- `EXPOSURE_TOO_HIGH`: Symbol or total exposure exceeds limits.
