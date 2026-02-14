"""
ReplayEngine: Replays JSONL event datasets through tradesync_core scoring + risk pipeline.
"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradesync_core import (
    Event,
    calculate_score,
    EnhancedScorer,
    RiskGuardian,
    normalize_symbol,
)


@dataclass
class SignalResult:
    symbol: str
    score: float
    direction: str
    confidence: float
    event_count: int
    ts: str


@dataclass
class OpportunityResult:
    symbol: str
    score: float
    enhanced_score: float
    quality: float
    direction: str
    warnings: List[str]
    execution_risk_flags: List[str]
    ts: str


@dataclass
class RiskResult:
    symbol: str
    allowed: bool
    reason_code: str
    reason: str
    ts: str


@dataclass
class ReplayResults:
    """Aggregated results from a replay run."""
    signals: List[SignalResult] = field(default_factory=list)
    opportunities: List[OpportunityResult] = field(default_factory=list)
    risk_verdicts: List[RiskResult] = field(default_factory=list)
    events_processed: int = 0
    symbols_processed: List[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signals": [asdict(s) for s in self.signals],
            "opportunities": [asdict(o) for o in self.opportunities],
            "risk_verdicts": [asdict(r) for r in self.risk_verdicts],
            "events_processed": self.events_processed,
            "symbols_processed": self.symbols_processed,
            "elapsed_seconds": self.elapsed_seconds,
        }


class ReplayEngine:
    def __init__(
        self,
        dataset_path: Path,
        realtime: bool = False,
        speed: float = 1.0,
    ):
        self.dataset_path = dataset_path
        self.realtime = realtime
        self.speed = max(0.1, speed)
        self.scorer = EnhancedScorer()
        self.risk_guardian = RiskGuardian()

    def _load_events(self) -> List[Dict[str, Any]]:
        events_file = self.dataset_path / "events.jsonl"
        if not events_file.exists():
            return []
        events = []
        with open(events_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    def run(self) -> ReplayResults:
        """Run the full replay pipeline."""
        t0 = time.time()
        results = ReplayResults()

        raw_events = self._load_events()
        if not raw_events:
            print("No events found in dataset.")
            return results

        # Group events by symbol
        by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for evt in raw_events:
            symbol = normalize_symbol(evt.get("symbol", "UNKNOWN"))
            by_symbol[symbol].append(evt)

        results.events_processed = len(raw_events)
        results.symbols_processed = sorted(by_symbol.keys())

        print(f"Loaded {len(raw_events)} events across {len(by_symbol)} symbols")

        prev_ts: Optional[datetime] = None

        for symbol, symbol_events in sorted(by_symbol.items()):
            # Sort by timestamp
            symbol_events.sort(key=lambda e: e["ts"])

            # Optional realtime pacing
            if self.realtime and prev_ts is not None:
                first_ts = datetime.fromisoformat(symbol_events[0]["ts"])
                delta = (first_ts - prev_ts).total_seconds()
                if delta > 0:
                    time.sleep(delta / self.speed)

            if symbol_events:
                last_evt = symbol_events[-1]
                prev_ts = datetime.fromisoformat(last_evt["ts"])

            # Convert to CoreEvent objects
            core_events = []
            for evt in symbol_events:
                core_events.append(Event(
                    ts=datetime.fromisoformat(evt["ts"]),
                    source=evt["source"],
                    kind=evt["kind"],
                    payload=evt.get("payload", {}),
                ))

            # Phase 1: Core scoring
            score = calculate_score(core_events)
            confidence = abs(score) / 10.0
            if score > 0:
                direction = "LONG"
            elif score < 0:
                direction = "SHORT"
            else:
                direction = "NEUTRAL"

            signal = SignalResult(
                symbol=symbol,
                score=score,
                direction=direction,
                confidence=confidence,
                event_count=len(core_events),
                ts=symbol_events[-1]["ts"],
            )
            results.signals.append(signal)
            print(f"  [{symbol}] Score: {score:+.2f} ({direction}, conf={confidence:.2f}, {len(core_events)} events)")

            # Phase 2: Enhanced scoring
            enhanced = self.scorer.compute_enhanced_score(
                raw_score=score,
                signal_confidence=confidence,
                symbol=symbol,
            )
            final_score = enhanced.score_breakdown.final_score

            opp = OpportunityResult(
                symbol=symbol,
                score=score,
                enhanced_score=final_score,
                quality=confidence * 100,
                direction=direction,
                warnings=enhanced.warnings,
                execution_risk_flags=enhanced.execution_risk.flags,
                ts=symbol_events[-1]["ts"],
            )
            results.opportunities.append(opp)

            # Phase 3: Risk check
            verdict = self.risk_guardian.check(
                symbol=symbol,
                size_usd=1000.0,
                opportunity={"status": "new", "quality": confidence * 100},
            )

            risk_result = RiskResult(
                symbol=symbol,
                allowed=verdict.allowed,
                reason_code=verdict.reason_code.value,
                reason=verdict.reason,
                ts=symbol_events[-1]["ts"],
            )
            results.risk_verdicts.append(risk_result)

            status = "PASS" if verdict.allowed else f"BLOCK ({verdict.reason_code.value})"
            print(f"  [{symbol}] Risk: {status}")

        results.elapsed_seconds = round(time.time() - t0, 3)
        print(f"\nReplay completed in {results.elapsed_seconds}s")
        return results
