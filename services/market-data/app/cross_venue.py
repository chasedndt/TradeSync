"""Cross-venue derivatives context: Binance perpetual funding and open interest.

Third of the sources from the 2026-09-12 open-data research. The interesting
number is not Binance's funding on its own but the *spread* between what
Hyperliquid longs pay and what Binance longs pay for the same coin: when one
venue's crowd is paying much more than the other's, positioning there is more
one-sided than the wider market's. That is a directional candidate — and, like
every new source, it is recorded first and believed only if it earns it.

Binance is an external reference venue, never a trading venue. Its public
futures endpoints are pulled directly: two requests per coin per minute is
tiny against the venue's published budget, and adding a general-purpose
exchange library for two fields would add far more code than it removes.

Absent, never zero, whenever a side is missing or the two venues were sampled
too far apart.
"""

from __future__ import annotations

from typing import Any, Mapping

BINANCE_PREMIUM_INDEX_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
BINANCE_OPEN_INTEREST_URL = "https://fapi.binance.com/fapi/v1/openInterest"
BINANCE_FUNDING_INTERVAL_HOURS = 8
# Funding moves slowly; five minutes of skew between the two venues' readings
# cannot masquerade as a spread. Tighter than this and a single slow poll
# would drop the feature for no reason.
MAX_ALIGNMENT_SKEW_MS = 5 * 60 * 1000


def binance_symbol_for(symbol: str) -> str:
    """``BTC-PERP`` -> ``BTCUSDT``. Coverage is checked by the poller, not here."""
    return symbol.upper().replace("-PERP", "") + "USDT"


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def parse_premium_index(payload: Any) -> dict[str, Any] | None:
    """Binance ``premiumIndex``: last funding rate per 8h interval and mark."""
    if not isinstance(payload, Mapping):
        return None
    rate = _finite(payload.get("lastFundingRate"))
    mark = _finite(payload.get("markPrice"))
    at = payload.get("time")
    if rate is None or mark is None or mark <= 0 or not isinstance(at, int) or at <= 0:
        return None
    return {
        "funding_rate_8h": rate,
        "mark_price_usd": mark,
        "observed_at_ms": at,
        "next_funding_ms": payload.get("nextFundingTime") if isinstance(payload.get("nextFundingTime"), int) else None,
    }


def parse_open_interest(payload: Any, mark_price_usd: float) -> dict[str, Any] | None:
    """Binance ``openInterest`` (contracts) converted to USD at the venue's mark."""
    if not isinstance(payload, Mapping) or mark_price_usd <= 0:
        return None
    contracts = _finite(payload.get("openInterest"))
    at = payload.get("time")
    if contracts is None or contracts < 0 or not isinstance(at, int) or at <= 0:
        return None
    return {"open_interest_usd": contracts * mark_price_usd, "contracts": contracts, "observed_at_ms": at}


def funding_spread_bps(hl_hourly_rate: float, binance_rate_8h: float) -> float:
    """Hyperliquid minus Binance, both expressed per 8 hours, in basis points.

    Positive: Hyperliquid longs are paying more than Binance longs — the
    Hyperliquid crowd is more one-sidedly long than the wider market's.
    """
    return (hl_hourly_rate * BINANCE_FUNDING_INTERVAL_HOURS - binance_rate_8h) * 10_000


def attach_cross_venue(
    payload: dict, reference: Mapping[str, Mapping[str, Any]], stale_after_ms: int
) -> dict:
    """Write Binance funding, OI and the funding spread onto a snapshot.

    Each of the three is attached independently: OI can be present when the
    spread cannot be computed, and neither is ever defaulted.
    """
    symbol = str(payload.get("symbol") or "")
    reading = reference.get(symbol)
    perp_ts = payload.get("ts")
    if not reading or not isinstance(perp_ts, int):
        return payload
    derived = payload.setdefault("derived", {})

    premium = reading.get("premium")
    if premium and perp_ts - int(premium["observed_at_ms"]) <= stale_after_ms:
        derived["binance_funding_rate_8h"] = {
            "value": premium["funding_rate_8h"],
            "observed_at_ms": premium["observed_at_ms"],
            "source": "binance_fapi_premiumIndex",
        }
        hl_rate = _finite(((payload.get("funding") or {}).get("horizons") or {}).get("now"))
        skew = abs(perp_ts - int(premium["observed_at_ms"]))
        if hl_rate is not None and skew <= MAX_ALIGNMENT_SKEW_MS:
            derived["funding_spread_vs_binance_bps"] = {
                "value": funding_spread_bps(hl_rate, premium["funding_rate_8h"]),
                "hl_rate_hourly": hl_rate,
                "binance_rate_8h": premium["funding_rate_8h"],
                "alignment_skew_ms": skew,
                "observed_at_ms": perp_ts,
            }

    oi = reading.get("open_interest")
    if oi and perp_ts - int(oi["observed_at_ms"]) <= stale_after_ms:
        derived["binance_open_interest_usd"] = {
            "value": oi["open_interest_usd"],
            "contracts": oi["contracts"],
            "observed_at_ms": oi["observed_at_ms"],
            "source": "binance_fapi_openInterest",
        }
    if not derived:
        payload.pop("derived", None)
    return payload
