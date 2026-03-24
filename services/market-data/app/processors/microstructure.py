"""
Microstructure derivation module for Phase 3C.

Computes derived market microstructure metrics from raw orderbook data:
- Spread in basis points
- Depth at various BPS thresholds (10bp, 25bp, 50bp)
- Price impact estimates for different order sizes
- Liquidity score
- Compact book heatmap for visualization
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DepthSlice:
    """Depth at a specific BPS distance from mid price."""
    bid_usd: float = 0.0
    ask_usd: float = 0.0
    total_usd: float = 0.0


@dataclass
class ImpactEstimate:
    """Estimated price impact for a given order size."""
    size_usd: float = 0.0
    slippage_bps: float = 0.0
    fill_levels: int = 0
    avg_fill_price: float = 0.0


@dataclass
class HeatmapLevel:
    """Single level in the book heatmap."""
    price: float
    side: str  # "bid" or "ask"
    size_usd: float


@dataclass
class MicrostructureResult:
    """Complete microstructure derivation result."""
    spread_bps: float
    mid_price: float
    depth_usd: Dict[str, float]  # {"10bp": x, "25bp": y, "50bp": z}
    impact_est_bps: Dict[str, float]  # {"1000": x, "5000": y, "10000": z}
    liquidity_score: float
    book_heatmap: List[HeatmapLevel]
    available: bool = True
    note: Optional[str] = None


class MicrostructureDeriver:
    """
    Derives microstructure metrics from raw orderbook data.

    Input: Raw orderbook with bids/asks array and basic computed metrics
    Output: MicrostructureResult with derived depth, impact, liquidity metrics
    """

    # Depth thresholds in basis points
    DEPTH_THRESHOLDS_BPS = [10, 25, 50]

    # Order sizes in USD for impact estimation
    IMPACT_SIZES_USD = [1000, 5000, 10000]

    # Max levels to include in heatmap (per side)
    HEATMAP_MAX_LEVELS = 50

    # Liquidity score weights
    SPREAD_WEIGHT = 0.4
    DEPTH_WEIGHT = 0.6

    # Reference values for score normalization
    MAX_SPREAD_BPS = 5.0  # Spread >= this gives 0 spread score
    REFERENCE_DEPTH_USD = 3_000_000  # Depth at 25bp for 100% depth score

    def derive(
        self,
        orderbook_data: Dict[str, Any]
    ) -> MicrostructureResult:
        """
        Derive microstructure metrics from orderbook data.

        Args:
            orderbook_data: Dict containing:
                - best_bid: float
                - best_ask: float
                - mid_price: float
                - spread_bps: float
                - bids: List[Dict] with {price, size, size_usd}
                - asks: List[Dict] with {price, size, size_usd}

        Returns:
            MicrostructureResult with derived metrics
        """
        try:
            # Extract basic fields
            best_bid = orderbook_data.get("best_bid", 0)
            best_ask = orderbook_data.get("best_ask", 0)
            mid_price = orderbook_data.get("mid_price", 0)
            spread_bps = orderbook_data.get("spread_bps", 0)

            bids = orderbook_data.get("bids", [])
            asks = orderbook_data.get("asks", [])

            if not mid_price or mid_price <= 0:
                return MicrostructureResult(
                    spread_bps=0,
                    mid_price=0,
                    depth_usd={},
                    impact_est_bps={},
                    liquidity_score=0,
                    book_heatmap=[],
                    available=False,
                    note="No mid price available"
                )

            # Compute depth at various thresholds
            depth_usd = self._compute_depth_slices(bids, asks, mid_price)

            # Compute impact estimates
            impact_est_bps = self._compute_impact_estimates(asks, mid_price)

            # Compute liquidity score
            liquidity_score = self._compute_liquidity_score(
                spread_bps,
                depth_usd.get("25bp", 0)
            )

            # Build heatmap
            book_heatmap = self._build_heatmap(bids, asks)

            return MicrostructureResult(
                spread_bps=spread_bps,
                mid_price=mid_price,
                depth_usd=depth_usd,
                impact_est_bps=impact_est_bps,
                liquidity_score=liquidity_score,
                book_heatmap=book_heatmap,
                available=True
            )

        except Exception as e:
            logger.error(f"Microstructure derivation failed: {e}")
            return MicrostructureResult(
                spread_bps=0,
                mid_price=0,
                depth_usd={},
                impact_est_bps={},
                liquidity_score=0,
                book_heatmap=[],
                available=False,
                note=f"Derivation error: {str(e)}"
            )

    def _compute_depth_slices(
        self,
        bids: List[Dict],
        asks: List[Dict],
        mid_price: float
    ) -> Dict[str, float]:
        """
        Compute depth in USD at various BPS thresholds from mid price.

        For each threshold (10bp, 25bp, 50bp), sum the USD depth on both sides
        of the book within that distance from mid.
        """
        depth_usd = {}

        for threshold_bps in self.DEPTH_THRESHOLDS_BPS:
            threshold_ratio = threshold_bps / 10000  # Convert bps to ratio

            bid_threshold = mid_price * (1 - threshold_ratio)
            ask_threshold = mid_price * (1 + threshold_ratio)

            # Sum bid depth (prices >= bid_threshold)
            bid_depth = sum(
                self._get_level_usd(level)
                for level in bids
                if self._get_price(level) >= bid_threshold
            )

            # Sum ask depth (prices <= ask_threshold)
            ask_depth = sum(
                self._get_level_usd(level)
                for level in asks
                if self._get_price(level) <= ask_threshold
            )

            depth_usd[f"{threshold_bps}bp"] = round(bid_depth + ask_depth, 2)

        return depth_usd

    def _compute_impact_estimates(
        self,
        asks: List[Dict],
        mid_price: float
    ) -> Dict[str, float]:
        """
        Estimate price impact in BPS for various order sizes.

        Uses a book walk: for a buy order, walk up the asks until
        cumulative size >= order size, then compute VWAP slippage.
        """
        impact_est_bps = {}

        for size_usd in self.IMPACT_SIZES_USD:
            impact = self._walk_book_for_impact(asks, mid_price, size_usd)
            impact_est_bps[str(size_usd)] = round(impact.slippage_bps, 2)

        return impact_est_bps

    def _walk_book_for_impact(
        self,
        asks: List[Dict],
        mid_price: float,
        size_usd: float
    ) -> ImpactEstimate:
        """
        Walk the ask side of the book to estimate price impact.

        Returns ImpactEstimate with:
        - Number of levels consumed
        - Average fill price (VWAP)
        - Slippage from mid in BPS
        """
        if not asks or mid_price <= 0:
            return ImpactEstimate(size_usd=size_usd, slippage_bps=0)

        remaining_usd = size_usd
        total_cost = 0.0
        total_filled_usd = 0.0
        levels_consumed = 0

        # Sort asks by price ascending
        sorted_asks = sorted(asks, key=lambda x: self._get_price(x))

        for level in sorted_asks:
            price = self._get_price(level)
            level_usd = self._get_level_usd(level)

            if level_usd <= 0 or price <= 0:
                continue

            levels_consumed += 1

            if level_usd >= remaining_usd:
                # Partial fill of this level
                total_cost += remaining_usd
                total_filled_usd += remaining_usd
                remaining_usd = 0
                break
            else:
                # Full fill of this level
                total_cost += level_usd
                total_filled_usd += level_usd
                remaining_usd -= level_usd

        if total_filled_usd <= 0:
            return ImpactEstimate(size_usd=size_usd, slippage_bps=0)

        # Calculate weighted average fill price
        # For simplicity, approximate as proportional walk through prices
        avg_fill_price = self._calculate_vwap(sorted_asks, total_filled_usd)

        if avg_fill_price <= 0:
            avg_fill_price = self._get_price(sorted_asks[0]) if sorted_asks else mid_price

        # Calculate slippage from mid
        slippage_bps = ((avg_fill_price - mid_price) / mid_price) * 10000

        return ImpactEstimate(
            size_usd=size_usd,
            slippage_bps=max(0, slippage_bps),  # Slippage should be positive for buys
            fill_levels=levels_consumed,
            avg_fill_price=avg_fill_price
        )

    def _calculate_vwap(
        self,
        levels: List[Dict],
        target_usd: float
    ) -> float:
        """Calculate volume-weighted average price for target fill size."""
        remaining = target_usd
        weighted_sum = 0.0
        total_weight = 0.0

        for level in levels:
            price = self._get_price(level)
            level_usd = self._get_level_usd(level)

            if level_usd <= 0 or price <= 0:
                continue

            fill_amount = min(level_usd, remaining)
            weighted_sum += price * fill_amount
            total_weight += fill_amount
            remaining -= fill_amount

            if remaining <= 0:
                break

        return weighted_sum / total_weight if total_weight > 0 else 0

    def _compute_liquidity_score(
        self,
        spread_bps: float,
        depth_25bp_usd: float
    ) -> float:
        """
        Compute a composite liquidity score from 0 to 1.

        Formula: 0.4 * spread_score + 0.6 * depth_score

        spread_score = 1 - min(spread_bps / MAX_SPREAD_BPS, 1.0)
        depth_score = min(depth_25bp_usd / REFERENCE_DEPTH_USD, 1.0)
        """
        # Spread score: lower spread = higher score
        spread_score = 1.0 - min(spread_bps / self.MAX_SPREAD_BPS, 1.0)

        # Depth score: higher depth = higher score
        depth_score = min(depth_25bp_usd / self.REFERENCE_DEPTH_USD, 1.0)

        liquidity_score = (
            self.SPREAD_WEIGHT * spread_score +
            self.DEPTH_WEIGHT * depth_score
        )

        return round(liquidity_score, 3)

    def _build_heatmap(
        self,
        bids: List[Dict],
        asks: List[Dict]
    ) -> List[HeatmapLevel]:
        """
        Build a compact heatmap of top N levels per side.

        Returns list of HeatmapLevel sorted by price distance from mid.
        """
        heatmap = []

        # Add top N bids (sorted by price descending = closest to mid first)
        sorted_bids = sorted(bids, key=lambda x: self._get_price(x), reverse=True)
        for level in sorted_bids[:self.HEATMAP_MAX_LEVELS]:
            price = self._get_price(level)
            if price > 0:
                heatmap.append(HeatmapLevel(
                    price=price,
                    side="bid",
                    size_usd=round(self._get_level_usd(level), 2)
                ))

        # Add top N asks (sorted by price ascending = closest to mid first)
        sorted_asks = sorted(asks, key=lambda x: self._get_price(x))
        for level in sorted_asks[:self.HEATMAP_MAX_LEVELS]:
            price = self._get_price(level)
            if price > 0:
                heatmap.append(HeatmapLevel(
                    price=price,
                    side="ask",
                    size_usd=round(self._get_level_usd(level), 2)
                ))

        return heatmap

    def _get_price(self, level: Dict) -> float:
        """Extract price from a level dict, handling various formats."""
        if isinstance(level, dict):
            return float(level.get("price", 0) or level.get("px", 0) or 0)
        return 0

    def _get_level_usd(self, level: Dict) -> float:
        """Extract USD size from a level dict, handling various formats."""
        if isinstance(level, dict):
            # Try direct size_usd first
            if "size_usd" in level:
                return float(level["size_usd"] or 0)

            # Otherwise compute from price * size
            price = self._get_price(level)
            size = float(level.get("size", 0) or level.get("sz", 0) or 0)
            return price * size
        return 0


# Convenience function for direct usage
def derive_microstructure(orderbook_data: Dict[str, Any]) -> MicrostructureResult:
    """
    Convenience function to derive microstructure from orderbook data.

    Args:
        orderbook_data: Dict containing orderbook with bids/asks

    Returns:
        MicrostructureResult with derived metrics
    """
    deriver = MicrostructureDeriver()
    return deriver.derive(orderbook_data)
