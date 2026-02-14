"""
Enhanced scorer: policy + structure aware scoring.
Extracted from services/fusion-engine/app/scoring.py (Phase 3C).
"""
from __future__ import annotations

import os
import logging
from typing import Dict, Any, List, Optional

from .contracts import ScoreBreakdown, ExecutionRisk, EnhancedScore

logger = logging.getLogger(__name__)


class EnhancedScorer:
    """
    Computes policy + structure aware scoring.

    Phase 3C scoring considers:
    1. Alpha signals (from core-scorer)
    2. Microstructure penalties (spread, depth, slippage thresholds)
    3. Exposure penalties (position concentration, margin stress)
    4. Regime bonuses (trend alignment, confluence multipliers)
    """

    def __init__(self):
        # Microstructure thresholds
        self.max_spread_bps = float(os.getenv("MAX_SPREAD_BPS", "50.0"))
        self.optimal_spread_bps = float(os.getenv("OPTIMAL_SPREAD_BPS", "2.0"))
        self.min_depth_25bp_usd = float(os.getenv("MIN_DEPTH_25BP_USD", "100000"))
        self.optimal_depth_25bp_usd = float(os.getenv("OPTIMAL_DEPTH_25BP_USD", "500000"))
        self.max_impact_bps_5k = float(os.getenv("MAX_IMPACT_BPS_5K", "25.0"))
        self.optimal_impact_bps_5k = float(os.getenv("OPTIMAL_IMPACT_BPS_5K", "5.0"))
        self.min_liquidity_score = float(os.getenv("MIN_LIQUIDITY_SCORE", "0.3"))

        # Exposure thresholds
        self.max_exposure_per_symbol = float(os.getenv("MAX_EXPOSURE_PER_SYMBOL_USD", "25000"))
        self.margin_stress_threshold = float(os.getenv("MARGIN_STRESS_THRESHOLD", "0.8"))

        # Penalty weights
        self.spread_penalty_weight = 0.5
        self.depth_penalty_weight = 0.3
        self.impact_penalty_weight = 0.2

    def compute_enhanced_score(
        self,
        raw_score: float,
        signal_confidence: float,
        symbol: str,
        microstructure: Optional[Dict[str, Any]] = None,
        regime_data: Optional[Dict[str, Any]] = None,
        exposure_data: Optional[Dict[str, Any]] = None
    ) -> EnhancedScore:
        """
        Compute enhanced score with full breakdown.

        Args:
            raw_score: Base alpha score from core-scorer
            signal_confidence: Signal confidence 0-1
            symbol: Trading symbol
            microstructure: Current microstructure data (spread, depth, impact, liquidity)
            regime_data: Current regime classifications
            exposure_data: Current position exposure by symbol

        Returns:
            EnhancedScore with breakdown, execution_risk, and warnings
        """
        notes = []
        warnings = []

        # 1. Base alpha score
        alpha = raw_score
        notes.append(f"Base alpha from signal: {alpha:.2f}")

        # 2. Microstructure penalties
        micro_penalty = 0.0
        execution_risk = ExecutionRisk()

        if microstructure:
            micro_penalty, micro_notes, micro_warnings, execution_risk = self._compute_microstructure_penalty(
                microstructure
            )
            notes.extend(micro_notes)
            warnings.extend(micro_warnings)

        # 3. Exposure penalties
        exposure_penalty = 0.0
        if exposure_data:
            exposure_penalty, exp_notes, exp_warnings = self._compute_exposure_penalty(
                symbol, exposure_data
            )
            notes.extend(exp_notes)
            warnings.extend(exp_warnings)

        # 4. Regime bonuses
        regime_bonus = 0.0
        if regime_data:
            regime_bonus, regime_notes = self._compute_regime_bonus(
                raw_score, regime_data
            )
            notes.extend(regime_notes)

        # 5. Final score calculation
        final_score = alpha + micro_penalty + exposure_penalty + regime_bonus

        breakdown = ScoreBreakdown(
            alpha=round(alpha, 2),
            microstructure_penalty=round(micro_penalty, 2),
            exposure_penalty=round(exposure_penalty, 2),
            regime_bonus=round(regime_bonus, 2),
            final_score=round(final_score, 2),
            notes=notes
        )

        return EnhancedScore(
            score_breakdown=breakdown,
            execution_risk=execution_risk,
            warnings=warnings
        )

    def _compute_microstructure_penalty(
        self,
        microstructure: Dict[str, Any]
    ) -> tuple[float, List[str], List[str], ExecutionRisk]:
        """
        Compute microstructure-based penalty.

        Returns (penalty, notes, warnings, execution_risk)
        """
        notes = []
        warnings = []
        flags = []
        total_penalty = 0.0

        # Extract microstructure fields
        spread_bps = microstructure.get("spread_bps", 0)
        depth_25bp = microstructure.get("depth_usd", {}).get("25bp", 0)
        impact_5k = microstructure.get("impact_est_bps", {}).get("5000", 0)
        liquidity_score = microstructure.get("liquidity_score", 1.0)

        # Spread penalty
        if spread_bps > self.optimal_spread_bps:
            spread_excess = spread_bps - self.optimal_spread_bps
            spread_penalty = min(spread_excess / (self.max_spread_bps - self.optimal_spread_bps), 1.0)
            spread_penalty *= -2.0 * self.spread_penalty_weight  # Max -1.0
            total_penalty += spread_penalty
            notes.append(f"Spread penalty: {spread_penalty:.2f} (spread {spread_bps:.1f} bps)")

            if spread_bps > self.max_spread_bps:
                flags.append("WIDE_SPREAD")
                warnings.append(f"Spread {spread_bps:.1f} bps exceeds maximum threshold {self.max_spread_bps:.1f} bps")

        # Depth penalty
        if depth_25bp < self.optimal_depth_25bp_usd:
            depth_ratio = depth_25bp / self.optimal_depth_25bp_usd if depth_25bp > 0 else 0
            depth_penalty = (1 - depth_ratio) * -1.5 * self.depth_penalty_weight  # Max -0.45
            total_penalty += depth_penalty
            notes.append(f"Depth penalty: {depth_penalty:.2f} (depth ${depth_25bp:,.0f})")

            if depth_25bp < self.min_depth_25bp_usd:
                flags.append("THIN_DEPTH")
                warnings.append(f"Depth at 25bp (${depth_25bp:,.0f}) below minimum ${self.min_depth_25bp_usd:,.0f}")

        # Impact penalty
        if impact_5k > self.optimal_impact_bps_5k:
            impact_excess = impact_5k - self.optimal_impact_bps_5k
            impact_penalty = min(impact_excess / (self.max_impact_bps_5k - self.optimal_impact_bps_5k), 1.0)
            impact_penalty *= -1.5 * self.impact_penalty_weight  # Max -0.3
            total_penalty += impact_penalty
            notes.append(f"Impact penalty: {impact_penalty:.2f} (est. {impact_5k:.1f} bps for $5k)")

            if impact_5k > self.max_impact_bps_5k:
                flags.append("HIGH_SLIPPAGE")
                warnings.append(f"Expected slippage {impact_5k:.1f} bps exceeds limit {self.max_impact_bps_5k:.1f} bps")

        # Low liquidity flag
        if liquidity_score < self.min_liquidity_score:
            flags.append("LOW_LIQUIDITY")
            warnings.append(f"Liquidity score {liquidity_score:.2f} below minimum {self.min_liquidity_score:.2f}")

        execution_risk = ExecutionRisk(
            spread_bps=spread_bps,
            impact_est_bps_5k=impact_5k,
            depth_25bp=depth_25bp,
            liquidity_score=liquidity_score,
            flags=flags
        )

        return total_penalty, notes, warnings, execution_risk

    def _compute_exposure_penalty(
        self,
        symbol: str,
        exposure_data: Dict[str, Any]
    ) -> tuple[float, List[str], List[str]]:
        """
        Compute exposure-based penalty.

        Returns (penalty, notes, warnings)
        """
        notes = []
        warnings = []
        penalty = 0.0

        # Current exposure for this symbol
        symbol_exposure = exposure_data.get("by_symbol", {}).get(symbol, 0)
        margin_utilization = exposure_data.get("margin_utilization", 0)

        # Symbol concentration penalty
        if symbol_exposure > self.max_exposure_per_symbol * 0.5:
            exposure_ratio = symbol_exposure / self.max_exposure_per_symbol
            concentration_penalty = min(exposure_ratio, 1.0) * -0.5  # Max -0.5
            penalty += concentration_penalty
            notes.append(f"Exposure penalty: {concentration_penalty:.2f} (${symbol_exposure:,.0f} in {symbol})")

            if symbol_exposure > self.max_exposure_per_symbol:
                warnings.append(f"Existing {symbol} exposure ${symbol_exposure:,.0f} exceeds limit")

        # Margin stress penalty
        if margin_utilization > self.margin_stress_threshold:
            margin_penalty = (margin_utilization - self.margin_stress_threshold) / (1 - self.margin_stress_threshold)
            margin_penalty *= -1.0  # Max -1.0
            penalty += margin_penalty
            notes.append(f"Margin stress penalty: {margin_penalty:.2f} (utilization {margin_utilization:.0%})")
            warnings.append(f"Margin utilization {margin_utilization:.0%} exceeds stress threshold")

        return penalty, notes, warnings

    def _compute_regime_bonus(
        self,
        raw_score: float,
        regime_data: Dict[str, Any]
    ) -> tuple[float, List[str]]:
        """
        Compute regime-based bonus/penalty.

        Returns (bonus, notes)
        """
        notes = []
        bonus = 0.0

        funding_regime = regime_data.get("funding", "neutral")
        oi_regime = regime_data.get("oi", "flat")
        market_condition = regime_data.get("market_condition", "unknown")

        # Squeeze potential bonus
        if raw_score > 0:  # LONG bias
            if funding_regime in ["elevated_negative", "extreme_negative"] and oi_regime == "build":
                bonus += 0.5
                notes.append("Regime bonus: +0.5 (short squeeze potential - negative funding + OI build)")
        elif raw_score < 0:  # SHORT bias
            if funding_regime in ["elevated_positive", "extreme_positive"] and oi_regime == "build":
                bonus += 0.5
                notes.append("Regime bonus: +0.5 (long squeeze potential - positive funding + OI build)")

        # Trend alignment bonus
        if market_condition == "trending_healthy":
            bonus += 0.3
            notes.append("Regime bonus: +0.3 (healthy trending market)")
        elif market_condition == "choppy":
            bonus -= 0.3
            notes.append("Regime penalty: -0.3 (choppy market condition)")

        return bonus, notes


# Convenience function
def compute_enhanced_score(
    raw_score: float,
    signal_confidence: float,
    symbol: str,
    microstructure: Optional[Dict[str, Any]] = None,
    regime_data: Optional[Dict[str, Any]] = None,
    exposure_data: Optional[Dict[str, Any]] = None
) -> EnhancedScore:
    """Convenience function to compute enhanced score."""
    scorer = EnhancedScorer()
    return scorer.compute_enhanced_score(
        raw_score=raw_score,
        signal_confidence=signal_confidence,
        symbol=symbol,
        microstructure=microstructure,
        regime_data=regime_data,
        exposure_data=exposure_data
    )
