"""The readings declared before any outcome was read (docs/research/2026-09-15_positioning-candidates.md).

A reading turns one candidate's value at entry into a signed number whose sign is the call.
The z parameters are not restated here: the catalog is the one source for each feature's
normalization, lookback and minimum history, and the declaration only fills the two gaps it
names (a method where the catalog has none, and one unusable minimum).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

RAW = "raw"
Z = "z"
CHANGE_4H = "change_4h"
WITH_PRICE = "with_price"
CHANGE_4H_WITH_PRICE = "change_4h_with_price"

# Candidate -> its declared readings, in declaration order.
CANDIDATES: dict[str, tuple[str, ...]] = {
    "hl_funding_hourly_rate": (RAW, Z),
    "hl_funding_apr_24h": (RAW, Z),
    "funding_spread_vs_binance_bps": (RAW, Z),
    "binance_funding_rate_8h": (RAW, Z),
    "hl_open_interest_4h_pct": (RAW, Z, WITH_PRICE),
    "binance_open_interest_usd": (CHANGE_4H, CHANGE_4H_WITH_PRICE, Z),
    "liq_map_skew_3pct": (RAW, Z),
    "cex_liquidations_net_1h_usd": (RAW, Z),
    "hl_oracle_premium_bps": (RAW, Z),
}

# Written once at entry by the outcome job; every other entry value is rebuilt from the store.
RECORDED_AT_ENTRY = frozenset({"binance_funding_rate_8h", "funding_spread_vs_binance_bps", "liq_map_skew_3pct"})
PRICE_FEATURE = "hl_return_1h_pct"

Z_METHOD_WHEN_UNNORMALIZED = "robust_zscore"
Z_MINIMUM_OVERRIDES = {"hl_funding_apr_24h": 12}

# What each economic story predicts. Reported beside the results; never an input to the test.
EXPECTED_BY_FEATURE = {
    "hl_funding_hourly_rate": "inverted",
    "hl_funding_apr_24h": "inverted",
    "funding_spread_vs_binance_bps": "inverted",
    "binance_funding_rate_8h": "inverted",
    "liq_map_skew_3pct": "as_read",
    "cex_liquidations_net_1h_usd": "as_read",
    "hl_oracle_premium_bps": "inverted",
}
EXPECTED_BY_READING = {
    "hl_open_interest_4h_pct:with_price": "as_read",
    "binance_open_interest_usd:change_4h_with_price": "as_read",
}


@dataclass(frozen=True)
class Reading:
    reading_id: str
    feature_id: str
    kind: str
    z_method: str | None = None
    z_lookback: int | None = None
    z_minimum: int | None = None

    @property
    def admissible(self) -> bool:
        """Only a z reading is what the scorer computes for an admitted feature (direct or inverse)."""
        return self.kind == Z


def declared_readings(catalog_features: Mapping[str, Mapping[str, Any]]) -> list[Reading]:
    readings: list[Reading] = []
    for feature_id, kinds in CANDIDATES.items():
        spec = catalog_features[feature_id]
        for kind in kinds:
            if kind != Z:
                readings.append(Reading(f"{feature_id}:{kind}", feature_id, kind))
                continue
            method = spec["normalization"]
            if method not in ("ordinary_zscore", "robust_zscore"):
                method = Z_METHOD_WHEN_UNNORMALIZED
            minimum = Z_MINIMUM_OVERRIDES.get(feature_id, int(spec["minimum_history_points"]))
            readings.append(Reading(f"{feature_id}:{Z}", feature_id, Z, method, int(spec["lookback_points"]), minimum))
    return readings


def expected_polarity(reading: Reading) -> str:
    return EXPECTED_BY_READING.get(reading.reading_id) or EXPECTED_BY_FEATURE.get(reading.feature_id, "none")
