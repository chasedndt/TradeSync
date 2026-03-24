"""
Market data snapshotter.

Aggregates normalized events into MarketSnapshot with:
- Multi-horizon windows
- Regime classifications
- Alert generation on regime changes
"""

import time
import uuid
import logging
from typing import Dict, List, Any, Optional
from collections import defaultdict

from ..models import (
    MarketSnapshot,
    MetricAvailability,
    MetricStatus,
    FundingData,
    FundingHorizons,
    FundingSource,
    FundingRegime,
    OpenInterestData,
    HorizonValue,
    OIRegime,
    VolumeData,
    VolumeRegime,
    OrderbookData,
    OrderbookDepth,
    LiquidationData,
    LiquidationWindow,
    RegimeSummary,
    TrendRegime,
    MarketCondition,
    SourceMetadata,
    MarketAlert,
    NormalizedMarketEvent,
    # Phase 3C additions
    MicrostructureData,
    BookHeatmapLevel,
)
from .microstructure import MicrostructureDeriver

logger = logging.getLogger(__name__)


class MarketSnapshotter:
    """Builds MarketSnapshot from normalized events."""

    def __init__(self):
        # Rolling window storage: {venue: {symbol: {metric: [values]}}}
        self._windows: Dict[str, Dict[str, Dict[str, List]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )

        # Previous regimes for alert detection
        self._prev_regimes: Dict[str, Dict[str, RegimeSummary]] = defaultdict(dict)

        # Phase 3C: Microstructure deriver
        self._microstructure_deriver = MicrostructureDeriver()

        # Window sizes in ms
        self.windows = {
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
            "24h": 24 * 60 * 60 * 1000,
            "7d": 7 * 24 * 60 * 60 * 1000,
        }

        # Funding specific windows
        self.funding_windows = {
            "8h": 8 * 60 * 60 * 1000,
            "24h": 24 * 60 * 60 * 1000,
            "3d": 3 * 24 * 60 * 60 * 1000,
            "7d": 7 * 24 * 60 * 60 * 1000,
        }

    def process_event(
        self,
        event: NormalizedMarketEvent
    ) -> Optional[MarketSnapshot]:
        """
        Process a normalized event and update rolling windows.

        Returns updated snapshot if enough data, None otherwise.
        """
        venue = event.venue
        symbol = event.symbol
        metric = event.metric_type

        # Add to rolling window
        self._add_to_window(venue, symbol, metric, {
            "ts": event.ts,
            "value": event.value,
            "status": event.status,
            "source": event.source.model_dump() if event.source else {}
        })

        # Build snapshot from current windows
        return self.build_snapshot(venue, symbol)

    def build_snapshot(
        self,
        venue: str,
        symbol: str
    ) -> MarketSnapshot:
        """
        Build a complete MarketSnapshot from current window data.
        """
        now = int(time.time() * 1000)
        windows = self._windows[venue][symbol]

        # Track available metrics and max data age
        available_metrics = []
        max_data_age = 0
        sources = []

        # Build funding data
        funding_data = None
        if "funding" in windows and windows["funding"]:
            funding_data, funding_metrics, funding_age = self._build_funding(windows["funding"], now)
            available_metrics.extend(funding_metrics)
            max_data_age = max(max_data_age, funding_age)

        # Build OI data
        oi_data = None
        if "oi" in windows and windows["oi"]:
            oi_data, oi_metrics, oi_age = self._build_oi(windows["oi"], now)
            available_metrics.extend(oi_metrics)
            max_data_age = max(max_data_age, oi_age)

        # Build volume data
        volume_data = None
        if "volume" in windows and windows["volume"]:
            volume_data, vol_metrics, vol_age = self._build_volume(windows["volume"], now)
            available_metrics.extend(vol_metrics)
            max_data_age = max(max_data_age, vol_age)

        # Build orderbook data
        orderbook_data = None
        microstructure_data = None
        if "orderbook" in windows and windows["orderbook"]:
            orderbook_data, ob_metrics, ob_age = self._build_orderbook(windows["orderbook"], now)
            available_metrics.extend(ob_metrics)
            max_data_age = max(max_data_age, ob_age)

            # Phase 3C: Derive microstructure from orderbook
            microstructure_data, micro_metrics = self._build_microstructure(
                windows["orderbook"], orderbook_data
            )
            available_metrics.extend(micro_metrics)

        # Build liquidation data (proxy)
        liq_data = None
        if "liquidations" in windows and windows["liquidations"]:
            liq_data, liq_metrics, liq_age = self._build_liquidations(windows["liquidations"], now)
            available_metrics.extend(liq_metrics)
            max_data_age = max(max_data_age, liq_age)

        # Compute regimes
        regimes = self._compute_regimes(funding_data, oi_data, volume_data, available_metrics)

        # Collect sources
        for metric_data in [windows.get(m, []) for m in ["funding", "oi", "volume", "orderbook"]]:
            if metric_data:
                latest = metric_data[-1]
                if "source" in latest:
                    sources.append(SourceMetadata(**latest["source"]))

        # Dedupe sources
        seen = set()
        unique_sources = []
        for s in sources:
            key = (s.provider, s.endpoint)
            if key not in seen:
                seen.add(key)
                unique_sources.append(s)

        snapshot = MarketSnapshot(
            venue=venue,
            symbol=symbol,
            ts=now,
            data_age_ms=max_data_age,
            available_metrics=available_metrics,
            funding=funding_data,
            oi=oi_data,
            volume=volume_data,
            orderbook=orderbook_data,
            microstructure=microstructure_data,  # Phase 3C
            liquidations=liq_data,
            regimes=regimes,
            sources=unique_sources
        )

        return snapshot

    def check_regime_change(
        self,
        venue: str,
        symbol: str,
        new_regimes: RegimeSummary
    ) -> List[MarketAlert]:
        """Check if any regimes changed and generate alerts."""
        alerts = []
        key = f"{venue}:{symbol}"

        if key not in self._prev_regimes:
            self._prev_regimes[key] = new_regimes
            return alerts

        prev = self._prev_regimes[key]
        now = int(time.time() * 1000)

        # Check each regime type
        regime_checks = [
            ("funding", prev.funding, new_regimes.funding),
            ("oi", prev.oi, new_regimes.oi),
            ("volume", prev.volume, new_regimes.volume),
            ("trend", prev.trend, new_regimes.trend),
        ]

        for metric, prev_val, new_val in regime_checks:
            if prev_val != new_val:
                alerts.append(MarketAlert(
                    id=str(uuid.uuid4()),
                    venue=venue,
                    symbol=symbol,
                    ts=now,
                    alert_type="regime_change",
                    metric=metric,
                    previous_value=prev_val.value if hasattr(prev_val, 'value') else str(prev_val),
                    new_value=new_val.value if hasattr(new_val, 'value') else str(new_val),
                    context={
                        "message": f"{metric.upper()} regime changed: {prev_val} -> {new_val}"
                    }
                ))

        self._prev_regimes[key] = new_regimes
        return alerts

    def _add_to_window(
        self,
        venue: str,
        symbol: str,
        metric: str,
        data: Dict[str, Any]
    ):
        """Add data point to rolling window."""
        window = self._windows[venue][symbol][metric]
        window.append(data)

        # Prune old entries (keep last 7 days)
        now = int(time.time() * 1000)
        cutoff = now - self.windows["7d"]
        self._windows[venue][symbol][metric] = [
            d for d in window if d.get("ts", 0) > cutoff
        ]

    def _build_funding(
        self,
        data: List[Dict],
        now: int
    ) -> tuple[FundingData, List[MetricAvailability], int]:
        """Build funding data with multi-horizon averages."""
        latest = data[-1]
        latest_value = latest["value"]
        current_rate = latest_value.get("rate", 0)
        data_age = now - latest.get("ts", now)

        # Calculate horizon averages
        horizons = FundingHorizons(now=current_rate)

        for window_name, window_ms in self.funding_windows.items():
            cutoff = now - window_ms
            window_data = [d for d in data if d.get("ts", 0) > cutoff]

            if window_data:
                avg = sum(d["value"].get("rate", 0) for d in window_data) / len(window_data)
                if window_name == "8h":
                    horizons.h8 = avg
                elif window_name == "24h":
                    horizons.h24 = avg
                elif window_name == "3d":
                    horizons.d3 = avg
                elif window_name == "7d":
                    horizons.d7 = avg

        # Compute annualized rate
        annualized = horizons.h24 * 365

        # Determine regime
        regime = self._classify_funding_regime(annualized)

        funding_data = FundingData(
            horizons=horizons,
            annualized_24h=annualized,
            regime=regime,
            source=FundingSource(
                provider=latest.get("source", {}).get("provider", "unknown"),
                endpoint=latest.get("source", {}).get("endpoint", "unknown"),
                raw_rate=current_rate
            )
        )

        status = MetricStatus(latest.get("status", "REAL"))
        metrics = [MetricAvailability(
            metric="funding",
            status=status,
            source=latest.get("source", {}).get("provider"),
            last_updated=latest.get("ts")
        )]

        return funding_data, metrics, data_age

    def _build_oi(
        self,
        data: List[Dict],
        now: int
    ) -> tuple[OpenInterestData, List[MetricAvailability], int]:
        """Build OI data with delta calculations."""
        latest = data[-1]
        current_oi = latest["value"].get("value_usd", 0)
        data_age = now - latest.get("ts", now)

        horizons = {}

        for window_name, window_ms in self.windows.items():
            if window_name in ["5m", "15m", "1h", "4h", "24h"]:
                cutoff = now - window_ms
                window_data = [d for d in data if d.get("ts", 0) > cutoff]

                if window_data and len(window_data) >= 2:
                    first_val = window_data[0]["value"].get("value_usd", current_oi)
                    delta_usd = current_oi - first_val
                    delta_pct = (delta_usd / first_val * 100) if first_val else 0

                    horizons[window_name] = HorizonValue(
                        value=first_val,
                        delta_pct=round(delta_pct, 2),
                        delta_usd=delta_usd
                    )
                else:
                    horizons[window_name] = HorizonValue(value=current_oi)

        # Determine regime
        delta_24h = horizons.get("24h", HorizonValue()).delta_pct
        delta_4h = horizons.get("4h", HorizonValue()).delta_pct
        regime = self._classify_oi_regime(delta_24h, delta_4h)

        oi_data = OpenInterestData(
            horizons=horizons,
            current_usd=current_oi,
            regime=regime
        )

        status = MetricStatus(latest.get("status", "REAL"))
        metrics = [MetricAvailability(
            metric="oi",
            status=status,
            source=latest.get("source", {}).get("provider"),
            last_updated=latest.get("ts")
        )]

        return oi_data, metrics, data_age

    def _build_volume(
        self,
        data: List[Dict],
        now: int
    ) -> tuple[VolumeData, List[MetricAvailability], int]:
        """Build volume data."""
        latest = data[-1]
        vol_24h = latest["value"].get("value_24h", 0)
        data_age = now - latest.get("ts", now)

        # Build horizon dict (for 24h we have the value, others are estimated)
        horizons = {
            "24h": vol_24h,
            "5m": vol_24h / (24 * 12) if vol_24h else 0,  # Rough estimate
            "1h": vol_24h / 24 if vol_24h else 0,
            "4h": vol_24h / 6 if vol_24h else 0,
        }

        # Calculate 7d average (from historical data if available)
        week_cutoff = now - self.windows["7d"]
        week_data = [d for d in data if d.get("ts", 0) > week_cutoff]
        avg_7d = vol_24h  # Default to current
        if len(week_data) >= 7:
            avg_7d = sum(d["value"].get("value_24h", 0) for d in week_data) / len(week_data)

        # Determine regime
        regime = self._classify_volume_regime(vol_24h, avg_7d)

        volume_data = VolumeData(
            horizons=horizons,
            avg_7d_daily=avg_7d,
            regime=regime
        )

        status = MetricStatus(latest.get("status", "REAL"))
        metrics = [MetricAvailability(
            metric="volume",
            status=status,
            source=latest.get("source", {}).get("provider"),
            last_updated=latest.get("ts")
        )]

        return volume_data, metrics, data_age

    def _build_orderbook(
        self,
        data: List[Dict],
        now: int
    ) -> tuple[OrderbookData, List[MetricAvailability], int]:
        """Build orderbook data."""
        latest = data[-1]
        value = latest["value"]
        data_age = now - latest.get("ts", now)

        depth = value.get("depth", {})

        orderbook_data = OrderbookData(
            spread_bps=value.get("spread_bps", 0),
            spread_usd=value.get("spread_usd", 0),
            depth=OrderbookDepth(
                bid_1pct_usd=depth.get("bid_1pct_usd", 0),
                ask_1pct_usd=depth.get("ask_1pct_usd", 0),
                bid_2pct_usd=depth.get("bid_2pct_usd", 0),
                ask_2pct_usd=depth.get("ask_2pct_usd", 0)
            ),
            imbalance_1pct=value.get("imbalance_1pct", 0),
            best_bid=value.get("best_bid", 0),
            best_ask=value.get("best_ask", 0),
            mid_price=value.get("mid_price", 0),
            book_age_ms=data_age
        )

        status = MetricStatus(latest.get("status", "REAL"))
        metrics = [MetricAvailability(
            metric="orderbook",
            status=status,
            source=latest.get("source", {}).get("provider"),
            last_updated=latest.get("ts")
        )]

        return orderbook_data, metrics, data_age

    def _build_microstructure(
        self,
        orderbook_data_list: List[Dict],
        orderbook: Optional[OrderbookData]
    ) -> tuple[Optional[MicrostructureData], List[MetricAvailability]]:
        """
        Build microstructure data from orderbook (Phase 3C).

        Derives:
        - Depth at 10/25/50 bps thresholds
        - Price impact estimates for 1k/5k/10k orders
        - Liquidity score
        - Heatmap visualization data
        """
        if not orderbook_data_list or not orderbook:
            return None, []

        latest = orderbook_data_list[-1]
        value = latest.get("value", {})

        # Get raw bids/asks if available in the window data
        bids = value.get("bids", [])
        asks = value.get("asks", [])

        # Build input for microstructure deriver
        orderbook_input = {
            "best_bid": orderbook.best_bid,
            "best_ask": orderbook.best_ask,
            "mid_price": orderbook.mid_price,
            "spread_bps": orderbook.spread_bps,
            "bids": bids,
            "asks": asks
        }

        # Derive microstructure
        result = self._microstructure_deriver.derive(orderbook_input)

        if not result.available:
            return None, [MetricAvailability(
                metric="microstructure",
                status=MetricStatus.UNAVAILABLE,
                note=result.note or "Microstructure derivation unavailable"
            )]

        # Convert to Pydantic models
        heatmap_levels = [
            BookHeatmapLevel(
                price=level.price,
                side=level.side,
                size_usd=level.size_usd
            )
            for level in result.book_heatmap
        ]

        microstructure = MicrostructureData(
            spread_bps=result.spread_bps,
            mid_price=result.mid_price,
            depth_usd=result.depth_usd,
            impact_est_bps=result.impact_est_bps,
            liquidity_score=result.liquidity_score,
            book_heatmap=heatmap_levels
        )

        metrics = [MetricAvailability(
            metric="microstructure",
            status=MetricStatus.REAL,  # Derived from real orderbook
            source="orderbook_derived",
            note="Derived from orderbook data",
            last_updated=latest.get("ts")
        )]

        return microstructure, metrics

    def _build_liquidations(
        self,
        data: List[Dict],
        now: int
    ) -> tuple[LiquidationData, List[MetricAvailability], int]:
        """Build liquidation data (typically proxy)."""
        latest = data[-1]
        value = latest["value"]
        data_age = now - latest.get("ts", now)

        # Build horizon windows from accumulated data
        horizons = {}
        for window_name in ["5m", "1h", "4h", "24h"]:
            window_ms = self.windows.get(window_name, 0)
            cutoff = now - window_ms
            window_data = [d for d in data if d.get("ts", 0) > cutoff]

            total = sum(d["value"].get("estimated_total_usd", 0) for d in window_data)
            horizons[window_name] = LiquidationWindow(
                longs_usd=total * 0.5,  # Rough split
                shorts_usd=total * 0.5,
                total_usd=total,
                dominant_side="balanced"
            )

        liq_data = LiquidationData(
            horizons=horizons,
            source_note=value.get("note", "PROXY: estimated from OI deltas"),
            method=value.get("method", "oi_delta_proxy")
        )

        metrics = [MetricAvailability(
            metric="liquidations",
            status=MetricStatus.PROXY,
            note="Estimated from OI changes. Real liquidation feed unavailable.",
            last_updated=latest.get("ts")
        )]

        return liq_data, metrics, data_age

    def _compute_regimes(
        self,
        funding: Optional[FundingData],
        oi: Optional[OpenInterestData],
        volume: Optional[VolumeData],
        available_metrics: List[MetricAvailability]
    ) -> RegimeSummary:
        """Compute overall regime summary."""
        funding_regime = funding.regime if funding else FundingRegime.NEUTRAL
        oi_regime = oi.regime if oi else OIRegime.FLAT
        volume_regime = volume.regime if volume else VolumeRegime.NORMAL

        # Simple trend detection based on OI and volume
        trend_regime = TrendRegime.RANGE
        if oi_regime == OIRegime.BUILD and volume_regime in [VolumeRegime.HIGH, VolumeRegime.NORMAL]:
            trend_regime = TrendRegime.STRONG_TREND
        elif oi_regime == OIRegime.BUILD:
            trend_regime = TrendRegime.WEAK_TREND

        # Market condition
        condition = MarketCondition.UNKNOWN

        # Check for squeeze risk: extreme funding + OI build
        if funding_regime in [FundingRegime.EXTREME_POSITIVE, FundingRegime.EXTREME_NEGATIVE]:
            if oi_regime == OIRegime.BUILD:
                condition = MarketCondition.SQUEEZE_RISK

        # Check for capitulation: OI unwind + high volume
        elif oi_regime == OIRegime.UNWIND and volume_regime == VolumeRegime.HIGH:
            condition = MarketCondition.CAPITULATION

        # Trending healthy
        elif trend_regime in [TrendRegime.STRONG_TREND, TrendRegime.WEAK_TREND]:
            if funding_regime == FundingRegime.NEUTRAL:
                condition = MarketCondition.TRENDING_HEALTHY

        # Choppy
        elif oi_regime == OIRegime.FLAT and volume_regime == VolumeRegime.LOW:
            condition = MarketCondition.CHOPPY

        # Confidence based on metric availability
        real_count = sum(1 for m in available_metrics if m.status == MetricStatus.REAL)
        total_count = len(available_metrics)

        if total_count == 0:
            confidence = "low"
            confidence_note = "No data available"
        elif real_count == total_count:
            confidence = "high"
            confidence_note = None
        elif real_count >= total_count * 0.5:
            confidence = "medium"
            proxy_metrics = [m.metric for m in available_metrics if m.status == MetricStatus.PROXY]
            confidence_note = f"Proxy data: {', '.join(proxy_metrics)}" if proxy_metrics else None
        else:
            confidence = "low"
            confidence_note = "Limited data availability"

        return RegimeSummary(
            funding=funding_regime,
            oi=oi_regime,
            volume=volume_regime,
            trend=trend_regime,
            market_condition=condition,
            confidence=confidence,
            confidence_note=confidence_note
        )

    def _classify_funding_regime(self, annualized_rate: float) -> FundingRegime:
        """Classify funding regime from annualized rate."""
        if annualized_rate > 0.50:
            return FundingRegime.EXTREME_POSITIVE
        elif annualized_rate > 0.20:
            return FundingRegime.ELEVATED_POSITIVE
        elif annualized_rate < -0.50:
            return FundingRegime.EXTREME_NEGATIVE
        elif annualized_rate < -0.20:
            return FundingRegime.ELEVATED_NEGATIVE
        else:
            return FundingRegime.NEUTRAL

    def _classify_oi_regime(self, delta_24h_pct: float, delta_4h_pct: float) -> OIRegime:
        """Classify OI regime from deltas."""
        if delta_24h_pct > 3.0 and delta_4h_pct > 0:
            return OIRegime.BUILD
        elif delta_24h_pct < -3.0 and delta_4h_pct < 0:
            return OIRegime.UNWIND
        else:
            return OIRegime.FLAT

    def _classify_volume_regime(self, vol_24h: float, avg_7d: float) -> VolumeRegime:
        """Classify volume regime."""
        if avg_7d <= 0:
            return VolumeRegime.NORMAL

        ratio = vol_24h / avg_7d

        if ratio > 2.0:
            return VolumeRegime.HIGH
        elif ratio < 0.5:
            return VolumeRegime.LOW
        else:
            return VolumeRegime.NORMAL
