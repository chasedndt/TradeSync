"""
Shared data contracts for scoring breakdown, execution risk, and enhanced scores.
Extracted from services/fusion-engine/app/scoring.py (Phase 3C).
"""

from typing import Dict, Any, List
from dataclasses import dataclass, field, asdict


@dataclass
class ScoreBreakdown:
    """Detailed scoring breakdown for transparency."""
    alpha: float = 0.0
    microstructure_penalty: float = 0.0
    exposure_penalty: float = 0.0
    regime_bonus: float = 0.0
    final_score: float = 0.0
    notes: List[str] = field(default_factory=list)


@dataclass
class ExecutionRisk:
    """Execution risk assessment based on microstructure."""
    spread_bps: float = 0.0
    impact_est_bps_5k: float = 0.0
    depth_25bp: float = 0.0
    liquidity_score: float = 0.0
    flags: List[str] = field(default_factory=list)


@dataclass
class EnhancedScore:
    """Complete enhanced score with breakdown, risk, and warnings."""
    score_breakdown: ScoreBreakdown
    execution_risk: ExecutionRisk
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score_breakdown": asdict(self.score_breakdown),
            "execution_risk": asdict(self.execution_risk),
            "warnings": self.warnings
        }
