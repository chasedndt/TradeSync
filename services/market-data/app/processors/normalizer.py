"""
Market data normalizer.

Transforms raw provider data into normalized events with:
- Canonical symbol format
- Metric status flags (REAL/PROXY/UNAVAILABLE)
- Data age computation
- Source metadata
"""

import time
import uuid
import logging
from typing import Dict, List, Any, Optional

from ..models import (
    MetricStatus,
    NormalizedMarketEvent,
    SourceMetadata,
)

logger = logging.getLogger(__name__)


class MarketNormalizer:
    """Normalizes raw market data into standard format."""

    def __init__(self):
        # Staleness thresholds (ms)
        self.stale_thresholds = {
            "funding": 60000,
            "oi": 30000,
            "volume": 30000,
            "orderbook": 5000,
            "liquidations": 60000,
        }

    def normalize_context(
        self,
        venue: str,
        raw_data: Dict[str, Any]
    ) -> List[NormalizedMarketEvent]:
        """
        Normalize context data (funding, OI, volume) from a provider.

        Args:
            venue: Provider name
            raw_data: Dict keyed by symbol with context data

        Returns:
            List of normalized events
        """
        events = []
        now = int(time.time() * 1000)

        for symbol, data in raw_data.items():
            poll_ts = data.get("poll_ts", now)
            data_age = now - poll_ts

            # Normalize funding
            if "funding" in data:
                funding = data["funding"]
                events.append(NormalizedMarketEvent(
                    id=str(uuid.uuid4()),
                    venue=venue,
                    symbol=symbol,
                    metric_type="funding",
                    ts=poll_ts,
                    data_age_ms=data_age,
                    status=self._get_status("funding", data_age),
                    source=SourceMetadata(
                        provider=venue,
                        endpoint=funding.get("source", "unknown"),
                        fetched_at=poll_ts,
                        metrics_provided=["funding"]
                    ),
                    value={
                        "rate": funding.get("rate", 0),
                        "raw": funding
                    }
                ))

            # Normalize OI
            if "oi" in data:
                oi = data["oi"]
                oi_value = oi.get("value", 0)
                oi_unit = oi.get("unit", "asset")

                # Convert to USD if in asset units
                if oi_unit == "asset" and "price" in data:
                    mark_price = data["price"].get("mark", 0)
                    oi_usd = oi_value * mark_price
                else:
                    oi_usd = oi_value

                events.append(NormalizedMarketEvent(
                    id=str(uuid.uuid4()),
                    venue=venue,
                    symbol=symbol,
                    metric_type="oi",
                    ts=poll_ts,
                    data_age_ms=data_age,
                    status=self._get_status("oi", data_age),
                    source=SourceMetadata(
                        provider=venue,
                        endpoint=oi.get("source", "unknown"),
                        fetched_at=poll_ts,
                        metrics_provided=["oi"]
                    ),
                    value={
                        "value_usd": oi_usd,
                        "value_raw": oi_value,
                        "unit": oi_unit,
                        "raw": oi
                    }
                ))

            # Normalize volume
            if "volume" in data:
                vol = data["volume"]
                events.append(NormalizedMarketEvent(
                    id=str(uuid.uuid4()),
                    venue=venue,
                    symbol=symbol,
                    metric_type="volume",
                    ts=poll_ts,
                    data_age_ms=data_age,
                    status=self._get_status("volume", data_age),
                    source=SourceMetadata(
                        provider=venue,
                        endpoint=vol.get("source", "unknown"),
                        fetched_at=poll_ts,
                        metrics_provided=["volume"]
                    ),
                    value={
                        "value_24h": vol.get("value_24h", 0),
                        "raw": vol
                    }
                ))

            # Normalize price (for reference)
            if "price" in data:
                price = data["price"]
                events.append(NormalizedMarketEvent(
                    id=str(uuid.uuid4()),
                    venue=venue,
                    symbol=symbol,
                    metric_type="price",
                    ts=poll_ts,
                    data_age_ms=data_age,
                    status=self._get_status("orderbook", data_age),  # Use orderbook threshold
                    source=SourceMetadata(
                        provider=venue,
                        endpoint="context",
                        fetched_at=poll_ts,
                        metrics_provided=["price"]
                    ),
                    value={
                        "mark": price.get("mark", 0),
                        "oracle": price.get("oracle", price.get("index", 0)),
                        "raw": price
                    }
                ))

        return events

    def normalize_orderbook(
        self,
        venue: str,
        orderbook_data: Dict[str, Any]
    ) -> Optional[NormalizedMarketEvent]:
        """
        Normalize orderbook data.

        Args:
            venue: Provider name
            orderbook_data: Parsed orderbook with bids, asks, spread, depth

        Returns:
            Normalized orderbook event
        """
        if not orderbook_data:
            return None

        now = int(time.time() * 1000)
        poll_ts = orderbook_data.get("poll_ts", now)
        data_age = now - poll_ts

        return NormalizedMarketEvent(
            id=str(uuid.uuid4()),
            venue=venue,
            symbol=orderbook_data["symbol"],
            metric_type="orderbook",
            ts=poll_ts,
            data_age_ms=data_age,
            status=self._get_status("orderbook", data_age),
            source=SourceMetadata(
                provider=venue,
                endpoint=orderbook_data.get("source", "unknown"),
                fetched_at=poll_ts,
                metrics_provided=["orderbook"]
            ),
            value={
                "best_bid": orderbook_data.get("best_bid", 0),
                "best_ask": orderbook_data.get("best_ask", 0),
                "mid_price": orderbook_data.get("mid_price", 0),
                "spread_bps": orderbook_data.get("spread_bps", 0),
                "spread_usd": orderbook_data.get("spread_usd", 0),
                "depth": orderbook_data.get("depth", {}),
                "imbalance_1pct": orderbook_data.get("imbalance_1pct", 0),
                # Phase 3C: Include more levels for microstructure derivation
                "bids": orderbook_data.get("bids", [])[:50],  # Top 50 for heatmap
                "asks": orderbook_data.get("asks", [])[:50],
            }
        )

    def normalize_funding_history(
        self,
        venue: str,
        symbol: str,
        history: List[Dict[str, Any]]
    ) -> List[NormalizedMarketEvent]:
        """
        Normalize historical funding rate data.
        """
        events = []
        now = int(time.time() * 1000)

        for entry in history:
            ts = entry.get("ts", now)
            data_age = now - ts

            events.append(NormalizedMarketEvent(
                id=str(uuid.uuid4()),
                venue=venue,
                symbol=symbol,
                metric_type="funding_history",
                ts=ts,
                data_age_ms=data_age,
                status=MetricStatus.REAL,  # Historical data is always REAL
                source=SourceMetadata(
                    provider=venue,
                    endpoint=entry.get("source", "fundingHistory"),
                    fetched_at=now,
                    metrics_provided=["funding_history"]
                ),
                value={
                    "rate": entry.get("rate", 0),
                    "premium": entry.get("premium", 0),
                    "raw": entry
                }
            ))

        return events

    def create_proxy_liquidations(
        self,
        venue: str,
        symbol: str,
        oi_current: float,
        oi_previous: float,
        volume: float,
        ts: int
    ) -> Optional[NormalizedMarketEvent]:
        """
        Create proxy liquidation estimate from OI delta.

        When OI drops without corresponding volume, it suggests liquidations.
        """
        oi_delta = oi_current - oi_previous

        if oi_delta >= 0:
            # OI increased or flat, no liquidations to estimate
            return None

        # Rough heuristic: OI drop without matching volume = liqs
        # This is a PROXY, not real data
        estimated_liqs = abs(oi_delta) * 0.5  # Conservative

        now = int(time.time() * 1000)
        data_age = now - ts

        return NormalizedMarketEvent(
            id=str(uuid.uuid4()),
            venue=venue,
            symbol=symbol,
            metric_type="liquidations",
            ts=ts,
            data_age_ms=data_age,
            status=MetricStatus.PROXY,
            source=SourceMetadata(
                provider=venue,
                endpoint="oi_delta_proxy",
                fetched_at=now,
                metrics_provided=["liquidations"]
            ),
            value={
                "estimated_total_usd": estimated_liqs,
                "oi_delta": oi_delta,
                "method": "oi_delta_proxy",
                "confidence": "low",
                "note": "Estimated from OI changes. Real liquidation feed unavailable."
            }
        )

    def _get_status(self, metric_type: str, data_age_ms: int) -> MetricStatus:
        """Determine metric status based on age."""
        threshold = self.stale_thresholds.get(metric_type, 30000)

        if data_age_ms > threshold:
            return MetricStatus.STALE
        return MetricStatus.REAL
