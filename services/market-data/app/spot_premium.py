"""Spot-versus-perpetual premium, from an external reference venue.

The premium compares a US spot price against the Hyperliquid perpetual mark. It
is a genuinely different measurement from everything else admitted so far, both
of which derive from Hyperliquid's own book and tape — which is exactly why it
is interesting, and exactly why it needs care.

**Introduced as context only.** The feature catalog is Hyperliquid-only by
construction, and the project handover gates Coinbase premium behind
"separately verified source availability, timing, provenance and permitted
use". Producing the number is not the same as admitting it to scoring, so this
lands visible and non-scoring until the operator decides otherwise.

The timing problem is the substantive one. Two venues sampled at different
moments produce a premium that is partly real and partly sampling noise. This
module refuses to compute one when the two observations are too far apart,
rather than reporting the gap as market structure.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

logger = logging.getLogger(__name__)

COINBASE_TICKER_URL = "https://api.exchange.coinbase.com/products/{product}/ticker"

# Hyperliquid coin -> Coinbase product. Only pairs with a genuine US spot
# listing belong here; a synthetic mapping would invent a premium.
COINBASE_PRODUCTS = {
    "BTC-PERP": "BTC-USD",
    "ETH-PERP": "ETH-USD",
    "SOL-PERP": "SOL-USD",
}

# Two venues sampled further apart than this cannot be compared: the difference
# would be dominated by when each was read, not by spot demand.
#
# Set to the catalog's own `fresh_after_ms` for coinbase_premium_bps. An earlier
# 10s bound was stricter than the catalog's declared freshness for the same
# feature, so the two disagreed about what "fresh" meant and the premium
# vanished from roughly a third of snapshots while still accumulating history.
# One standard, declared in the catalog, graded by the normalizer's freshness
# factor — not a second cutoff duplicated here.
MAX_ALIGNMENT_SKEW_MS = 15_000


def coinbase_product_for(symbol: str) -> str | None:
    return COINBASE_PRODUCTS.get(symbol)


def spot_mid(ticker: Mapping[str, Any]) -> float | None:
    """Mid of the Coinbase book. None when the payload is unusable.

    The mid is used rather than the last trade: a single print can sit at
    either side of the spread, which would show up as premium that is really
    just which side traded last.
    """
    try:
        bid = float(ticker["bid"])
        ask = float(ticker["ask"])
    except (KeyError, TypeError, ValueError):
        return None
    if bid <= 0 or ask <= 0 or ask < bid:
        return None
    return (bid + ask) / 2.0


def premium_bps(
    spot_price: float,
    perp_mark: float,
    spot_observed_ms: int,
    perp_observed_ms: int,
    max_skew_ms: int = MAX_ALIGNMENT_SKEW_MS,
) -> dict[str, Any] | None:
    """Spot premium over the perpetual mark, in basis points.

    Positive means US spot is trading above the perpetual — the conventional
    reading is spot-side demand. Returns None when the inputs cannot support
    the comparison, so a missing premium is absent rather than zero.
    """

    if spot_price <= 0 or perp_mark <= 0:
        return None
    skew = abs(spot_observed_ms - perp_observed_ms)
    if skew > max_skew_ms:
        # Reporting this as a premium would present sampling lag as market
        # structure.
        return None

    value = (spot_price - perp_mark) / perp_mark * 10_000
    return {
        "value_bps": round(value, 6),
        "spot_price": spot_price,
        "perp_mark": perp_mark,
        "alignment_skew_ms": skew,
        "reference_venue": "coinbase",
        # Restated on every observation: this is not the trading venue, and the
        # value is context until the operator admits it to scoring.
        "authority": "context_only",
    }
