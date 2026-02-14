"""
Pure scoring function extracted from services/core-scorer/app/main.py.
No DB or Redis dependencies - operates on plain dataclasses.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any


@dataclass
class Event:
    """Minimal event dataclass for scoring (no DB dependency)."""
    ts: datetime
    source: str
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)


def calculate_score(events: List[Event]) -> float:
    """
    Calculate a directional bias score from a list of events.

    Returns a score clamped to [-10.0, 10.0].
    Positive = LONG bias, Negative = SHORT bias.
    """
    if not events:
        return 0.0

    # Sort events by time
    sorted_events = sorted(events, key=lambda e: e.ts)
    score = 0.0

    # 1. TradingView Rules
    for event in sorted_events:
        if event.source == "tradingview":
            bias = event.payload.get("bias")
            if bias == "LONG":
                score += 1.0
            elif bias == "SHORT":
                score -= 1.0

    # 2. Metrics (Funding/OI) Logic
    metrics_events = [e for e in sorted_events if e.source == "metrics" and e.kind == "market_snapshot"]

    if metrics_events:
        latest = metrics_events[-1]
        first = metrics_events[0]

        funding = float(latest.payload.get("funding", 0.0) or 0.0)
        oi_current = float(latest.payload.get("oi", 0.0) or 0.0)
        oi_start = float(first.payload.get("oi", 0.0) or 0.0)

        oi_delta_pct = 0.0
        if oi_start > 0:
            oi_delta_pct = (oi_current - oi_start) / oi_start

        # MVP Rules: Squeeze Logic
        # Negative Funding + Rising OI -> Short Squeeze Risk (Long Bias)
        if funding < -0.0001 and oi_delta_pct > 0.005:
            score += 2.0
        # Positive Funding + Rising OI -> Long Squeeze Risk (Short Bias)
        elif funding > 0.0001 and oi_delta_pct > 0.005:
            score -= 2.0

        # Base Funding Bias
        if funding < 0:
            score += 0.5
        elif funding > 0:
            score -= 0.5

    # Clamp score
    return max(-10.0, min(10.0, score))
