"""
TradeSync Core Library - Shared scoring, risk, and normalization logic.

Phase 3D: Extracted from service-level code to ensure replay/backtest
runs the exact same logic as live.
"""

from tradesync_core.contracts import ScoreBreakdown, ExecutionRisk, EnhancedScore
from tradesync_core.scoring import EnhancedScorer, compute_enhanced_score
from tradesync_core.risk import ReasonCode, RiskVerdict, RiskGuardian
from tradesync_core.symbols import normalize_symbol, normalize_venue
from tradesync_core.core_score import Event, calculate_score

__all__ = [
    "EnhancedScorer",
    "compute_enhanced_score",
    "RiskGuardian",
    "ReasonCode",
    "RiskVerdict",
    "normalize_symbol",
    "normalize_venue",
    "Event",
    "calculate_score",
    "ScoreBreakdown",
    "ExecutionRisk",
    "EnhancedScore",
]

__version__ = "0.1.0"
