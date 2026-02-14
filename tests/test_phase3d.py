"""
Phase 3D Tests: Shared library + replay engine.

Tests:
- tradesync_core imports
- normalize_symbol correctness
- EnhancedScorer initialization + scoring
- RiskGuardian initialization + basic check
- calculate_score with synthetic events
- Replay engine against sample dataset (in-process, no Docker)
"""

import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure libs/ is importable for local testing
sys.path.insert(0, str(Path(__file__).parent.parent / "libs" / "tradesync_core"))
# Ensure backtest-runner app is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "backtest-runner"))


class TestTradesyncCoreImports:
    """Verify all public API symbols are importable."""

    def test_import_top_level(self):
        from tradesync_core import (
            EnhancedScorer,
            compute_enhanced_score,
            RiskGuardian,
            ReasonCode,
            RiskVerdict,
            normalize_symbol,
            normalize_venue,
            Event,
            calculate_score,
            ScoreBreakdown,
            ExecutionRisk,
            EnhancedScore,
        )
        # All should be non-None
        assert EnhancedScorer is not None
        assert compute_enhanced_score is not None
        assert RiskGuardian is not None
        assert ReasonCode is not None
        assert RiskVerdict is not None
        assert normalize_symbol is not None
        assert normalize_venue is not None
        assert Event is not None
        assert calculate_score is not None
        assert ScoreBreakdown is not None
        assert ExecutionRisk is not None
        assert EnhancedScore is not None

    def test_version(self):
        import tradesync_core
        assert tradesync_core.__version__ == "0.1.0"

    def test_all_exports(self):
        import tradesync_core
        assert len(tradesync_core.__all__) == 12


class TestNormalizeSymbol:
    def test_btcusdt(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("BTCUSDT") == "BTC-PERP"

    def test_btc_usdt_slash(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("BTC/USDT") == "BTC-PERP"

    def test_btc_perp_passthrough(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("BTC-PERP") == "BTC-PERP"

    def test_lowercase(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("btc-perp") == "BTC-PERP"

    def test_bare_symbol(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("ETH") == "ETH-PERP"

    def test_usdc_suffix(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("SOLUSDC") == "SOL-PERP"

    def test_empty_string(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("") == ""

    def test_none_returns_none(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol(None) is None


class TestNormalizeVenue:
    def test_hl_to_hyperliquid(self):
        from tradesync_core import normalize_venue
        assert normalize_venue("hl") == "hyperliquid"

    def test_drift_passthrough(self):
        from tradesync_core import normalize_venue
        assert normalize_venue("drift") == "drift"

    def test_empty(self):
        from tradesync_core import normalize_venue
        assert normalize_venue("") == ""


class TestEnhancedScorer:
    def test_init(self):
        from tradesync_core import EnhancedScorer
        scorer = EnhancedScorer()
        assert scorer.max_spread_bps == 50.0
        assert scorer.spread_penalty_weight == 0.5

    def test_basic_score(self):
        from tradesync_core import EnhancedScorer
        scorer = EnhancedScorer()
        result = scorer.compute_enhanced_score(
            raw_score=5.0,
            signal_confidence=0.5,
            symbol="BTC-PERP",
        )
        assert result.score_breakdown.alpha == 5.0
        assert result.score_breakdown.final_score == 5.0
        assert result.score_breakdown.microstructure_penalty == 0.0
        assert len(result.warnings) == 0

    def test_with_microstructure(self):
        from tradesync_core import EnhancedScorer
        scorer = EnhancedScorer()
        result = scorer.compute_enhanced_score(
            raw_score=5.0,
            signal_confidence=0.5,
            symbol="BTC-PERP",
            microstructure={
                "spread_bps": 100.0,  # Very wide spread
                "depth_usd": {"25bp": 50000},  # Below optimal
                "impact_est_bps": {"5000": 30.0},  # High impact
                "liquidity_score": 0.2,  # Below threshold
            },
        )
        assert result.score_breakdown.microstructure_penalty < 0
        assert result.score_breakdown.final_score < 5.0
        assert len(result.warnings) > 0
        assert "WIDE_SPREAD" in result.execution_risk.flags

    def test_to_dict(self):
        from tradesync_core import EnhancedScorer
        scorer = EnhancedScorer()
        result = scorer.compute_enhanced_score(
            raw_score=3.0, signal_confidence=0.3, symbol="ETH-PERP"
        )
        d = result.to_dict()
        assert "score_breakdown" in d
        assert "execution_risk" in d
        assert "warnings" in d


class TestRiskGuardian:
    def setup_method(self):
        os.environ["EXECUTION_ENABLED"] = "true"
        os.environ["MIN_QUALITY"] = "50.0"

    def test_init(self):
        from tradesync_core import RiskGuardian
        guardian = RiskGuardian()
        assert guardian.execution_enabled is True
        assert guardian.max_leverage == 5.0

    def test_pass(self):
        from tradesync_core import RiskGuardian, ReasonCode
        guardian = RiskGuardian()
        verdict = guardian.check(
            symbol="BTC-PERP",
            size_usd=1000.0,
            opportunity={"status": "new", "quality": 80.0},
        )
        assert verdict.allowed is True
        assert verdict.reason_code == ReasonCode.OK

    def test_dnt_block(self):
        from tradesync_core import RiskGuardian, ReasonCode
        guardian = RiskGuardian()
        verdict = guardian.check(
            symbol="LUNA-PERP",
            size_usd=1000.0,
            opportunity={"status": "new", "quality": 80.0},
        )
        assert verdict.allowed is False
        assert verdict.reason_code == ReasonCode.DNT

    def test_quality_block(self):
        from tradesync_core import RiskGuardian, ReasonCode
        guardian = RiskGuardian()
        verdict = guardian.check(
            symbol="BTC-PERP",
            size_usd=1000.0,
            opportunity={"status": "new", "quality": 10.0},
        )
        assert verdict.allowed is False
        assert verdict.reason_code == ReasonCode.MIN_QUALITY

    def test_exec_disabled(self):
        from tradesync_core import RiskGuardian, ReasonCode
        os.environ["EXECUTION_ENABLED"] = "false"
        guardian = RiskGuardian()
        verdict = guardian.check(
            symbol="BTC-PERP",
            size_usd=1000.0,
            opportunity={"status": "new", "quality": 80.0},
        )
        assert verdict.allowed is False
        assert verdict.reason_code == ReasonCode.EXEC_DISABLED


class TestCalculateScore:
    def test_empty_events(self):
        from tradesync_core import calculate_score
        assert calculate_score([]) == 0.0

    def test_long_bias(self):
        from tradesync_core import calculate_score, Event
        events = [
            Event(ts=datetime(2025, 1, 1, tzinfo=timezone.utc), source="tradingview", kind="alert", payload={"bias": "LONG"}),
        ]
        score = calculate_score(events)
        assert score == 1.0

    def test_short_bias(self):
        from tradesync_core import calculate_score, Event
        events = [
            Event(ts=datetime(2025, 1, 1, tzinfo=timezone.utc), source="tradingview", kind="alert", payload={"bias": "SHORT"}),
        ]
        score = calculate_score(events)
        assert score == -1.0

    def test_squeeze_logic_long(self):
        """Negative funding + rising OI = short squeeze = LONG bias."""
        from tradesync_core import calculate_score, Event
        events = [
            Event(
                ts=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
                source="metrics", kind="market_snapshot",
                payload={"funding": -0.0005, "oi": 1000000},
            ),
            Event(
                ts=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
                source="metrics", kind="market_snapshot",
                payload={"funding": -0.0005, "oi": 1020000},
            ),
        ]
        score = calculate_score(events)
        # Should be: squeeze +2.0 + base funding +0.5 = 2.5
        assert score == 2.5

    def test_squeeze_logic_short(self):
        """Positive funding + rising OI = long squeeze = SHORT bias."""
        from tradesync_core import calculate_score, Event
        events = [
            Event(
                ts=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
                source="metrics", kind="market_snapshot",
                payload={"funding": 0.0005, "oi": 500000},
            ),
            Event(
                ts=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
                source="metrics", kind="market_snapshot",
                payload={"funding": 0.0005, "oi": 510000},
            ),
        ]
        score = calculate_score(events)
        # Should be: squeeze -2.0 + base funding -0.5 = -2.5
        assert score == -2.5

    def test_clamp(self):
        from tradesync_core import calculate_score, Event
        # Many LONG signals to exceed 10
        events = [
            Event(ts=datetime(2025, 1, 1, 10, i, tzinfo=timezone.utc), source="tradingview", kind="alert", payload={"bias": "LONG"})
            for i in range(15)
        ]
        score = calculate_score(events)
        assert score == 10.0


class TestReplayEngine:
    """Test replay engine against sample dataset (in-process, no Docker)."""

    def setup_method(self):
        os.environ["EXECUTION_ENABLED"] = "true"
        os.environ["MIN_QUALITY"] = "1.0"  # Low threshold for sample data

    def test_sample_dataset(self):
        from app.replay import ReplayEngine

        dataset_path = Path(__file__).parent.parent / "data" / "replay" / "sample"
        engine = ReplayEngine(dataset_path=dataset_path)
        results = engine.run()

        # Should have processed events
        assert results.events_processed == 7

        # Should have 2 symbols
        assert len(results.symbols_processed) == 2
        assert "BTC-PERP" in results.symbols_processed
        assert "ETH-PERP" in results.symbols_processed

        # Should have signals for each symbol
        assert len(results.signals) == 2

        # BTC should be LONG (tradingview LONG + negative funding squeeze)
        btc_signal = next(s for s in results.signals if s.symbol == "BTC-PERP")
        assert btc_signal.direction == "LONG"
        assert btc_signal.score > 0

        # ETH should be SHORT (tradingview SHORT + positive funding squeeze)
        eth_signal = next(s for s in results.signals if s.symbol == "ETH-PERP")
        assert eth_signal.direction == "SHORT"
        assert eth_signal.score < 0

        # Should have risk verdicts
        assert len(results.risk_verdicts) == 2

    def test_empty_dataset(self, tmp_path):
        from app.replay import ReplayEngine

        # Create empty events file
        events_file = tmp_path / "events.jsonl"
        events_file.write_text("")

        engine = ReplayEngine(dataset_path=tmp_path)
        results = engine.run()

        assert results.events_processed == 0
        assert len(results.signals) == 0

    def test_evaluator(self, tmp_path):
        from app.replay import ReplayEngine
        from app.evaluator import generate_report

        dataset_path = Path(__file__).parent.parent / "data" / "replay" / "sample"
        engine = ReplayEngine(dataset_path=dataset_path)
        results = engine.run()

        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        generate_report(results, {"name": "test"}, output_dir)

        assert (output_dir / "report.json").exists()
        assert (output_dir / "report.md").exists()

        # Validate JSON report structure
        with open(output_dir / "report.json") as f:
            report = json.load(f)

        assert "summary" in report
        assert "results" in report
        assert report["summary"]["events_processed"] == 7
        assert report["summary"]["signals"]["total"] == 2

        # Validate Markdown report
        md_content = (output_dir / "report.md").read_text()
        assert "TradeSync Backtest Report" in md_content
        assert "Signal Distribution" in md_content
        assert "Risk Verdict Breakdown" in md_content
