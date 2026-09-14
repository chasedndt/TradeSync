"""The thesis's derivatives and context read, from current feature results.

The Morning Thesis SOP's second and fourth steps are a derivatives check
(funding, open interest, CVD) and narrative context. Those already exist as
catalogued features with current values and observation times; this module
picks them out and renders them, without scoring anything. A feature that
has no current value is listed as absent, not omitted, so the reader can see
what the thesis could not consult.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

# Catalog order matters: this is the order the SOP reads them in.
CONTEXT_FEATURES: tuple[tuple[str, str], ...] = (
    ("hl_funding_hourly_rate", "funding (hourly)"),
    ("hl_funding_apr_24h", "funding APR 24h"),
    ("hl_open_interest_4h_pct", "open interest 4h"),
    ("hl_direct_cvd", "CVD"),
    ("binance_funding_rate_8h", "Binance funding 8h"),
    ("funding_spread_vs_binance_bps", "funding spread vs Binance"),
    ("coinbase_premium_bps", "Coinbase premium"),
    ("gdelt_news_tone", "news tone"),
    ("hl_resting_liquidity_imbalance", "resting liquidity balance"),
    ("cex_liquidations_net_1h_usd", "liquidations net 1h (Bybit, Binance)"),
    ("liq_map_skew_3pct", "estimated liquidation levels skew"),
)


def derivatives_read(
    feature_results: Sequence[Mapping[str, Any]], now_ms: int
) -> list[dict[str, Any]]:
    """Current value, unit and age for each context feature, absent ones included."""
    by_id = {str(f.get("feature_id")): f for f in feature_results}
    out = []
    for feature_id, label in CONTEXT_FEATURES:
        f = by_id.get(feature_id)
        value = f.get("current_value") if f else None
        observed = f.get("observed_at_ms") if f else None
        present = isinstance(value, (int, float)) and not isinstance(value, bool)
        out.append(
            {
                "feature_id": feature_id,
                "label": label,
                "value": float(value) if present else None,
                "unit": (f or {}).get("unit"),
                "observed_at_ms": int(observed) if isinstance(observed, (int, float)) and not isinstance(observed, bool) else None,
                "age_ms": now_ms - int(observed) if isinstance(observed, (int, float)) and not isinstance(observed, bool) else None,
                "status": (f or {}).get("status", "absent") if present else "absent",
                "scoring_allowed": bool((f or {}).get("scoring_allowed", False)),
            }
        )
    return out


def _fmt(item: Mapping[str, Any]) -> str:
    v = item["value"]
    if v is None:
        return f"{item['label']} absent"
    unit = item.get("unit") or ""
    if unit == "basis_points":
        return f"{item['label']} {v:+.1f} bps"
    if unit == "percent" or unit == "percent_change":
        return f"{item['label']} {v:+.2f}%"
    if unit.startswith("decimal_rate") or unit.startswith("rate_per"):
        return f"{item['label']} {v * 100:+.4f}%"
    if unit.startswith("decimal_APR"):
        return f"{item['label']} {v * 100:+.1f}%"
    if unit == "tone_score":
        return f"{item['label']} {v:+.2f}"
    if unit == "USD_delta":
        return f"{item['label']} {v:+,.0f} USD"
    return f"{item['label']} {v:+.4g}"


def derivatives_line(items: Sequence[Mapping[str, Any]]) -> str:
    """One sentence for the thesis text."""
    return "Derivatives and context: " + "; ".join(_fmt(i) for i in items) + "."
