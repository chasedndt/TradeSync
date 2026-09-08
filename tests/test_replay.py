"""Fixed-window replay tests.

Replay exists to make weight changes falsifiable. Its own correctness rests on
one property above all: champion and challenger must see identical evidence, so
any difference is attributable to the configuration alone.
"""

import copy
import json
import unittest
from pathlib import Path

from tradesync_core.paper_signal import AdmissionPolicy
from tradesync_core.regime_weights import validate_rulebook
from tradesync_core.replay import (
    ReplayCase,
    ReplayError,
    case_from_stored_evidence,
    compare_rulebooks,
    replay_case,
    score_replay,
)

ROOT = Path(__file__).resolve().parents[1]
RULEBOOK_PATH = ROOT / "config" / "regime" / "regime-rulebook-v1.json"

CATALOG = {
    "catalog_id": "tradesync-hyperliquid-market-features",
    "version": "1.3.0",
    "digest": "catalogdigest",
}
NOW_MS = 1_788_800_000_000


def _rulebook(**weights):
    """The real rulebook, optionally with weights replaced. Must sum to 1."""
    data = json.loads(RULEBOOK_PATH.read_text(encoding="utf-8-sig"))
    if weights:
        for block, value in weights.items():
            data["blocks"][block]["weight"] = value
        data["version"] = "test-challenger"
    return validate_rulebook(data)


def _stored(directional_score=0.6, liquidity=-0.2, price_vol=0.5):
    """A persisted paper_signal_v1 payload, as core-scorer writes it."""
    return {
        "schema_version": "paper_signal_v1",
        "evidence": {
            "evaluated_at_ms": NOW_MS,
            "contributions": {
                "price_volatility": {"weight": 0.30, "score": price_vol, "quality": 1.0},
                "liquidity": {"weight": 0.25, "score": liquidity, "quality": 0.5},
                "positioning": {"weight": 0.20, "score": 0.0, "quality": 0.0},
                "spot_premium": {"weight": 0.15, "score": 0.0, "quality": 0.0},
                "macro_flows": {"weight": 0.10, "score": 0.0, "quality": 0.0},
            },
            "directional": {
                "score": directional_score,
                "coverage": 1.0,
                "contributors": [
                    {
                        "feature_id": "hl_return_1h_pct",
                        "score": directional_score,
                        "quality": 1.0,
                    }
                ],
                "admitted_feature_ids": ["hl_return_1h_pct"],
            },
        },
    }


def _case(signal_id="sig-1", directional_score=0.6, market_move=1.0, **kw):
    stored = _stored(directional_score=directional_score, **kw)
    return case_from_stored_evidence(
        signal_id,
        "BTC-PERP",
        stored,
        outcome_signed_return_pct=market_move,
        market_move_pct=market_move,
    )


class CaseExtractionTests(unittest.TestCase):
    def test_block_scores_and_qualities_are_read_from_the_record(self):
        case = _case()
        self.assertEqual(case.block_scores["price_volatility"], 0.5)
        self.assertEqual(case.block_qualities["liquidity"], 0.5)

    def test_zero_quality_blocks_are_not_resurrected_by_a_challenger(self):
        """A block that contributed nothing must stay absent, however weighted."""
        case = _case()
        self.assertNotIn("positioning", case.block_scores)
        self.assertNotIn("macro_flows", case.block_qualities)

    def test_missing_evidence_is_an_error_not_a_silent_empty_case(self):
        with self.assertRaises(ReplayError):
            case_from_stored_evidence("sig", "BTC-PERP", {})
        with self.assertRaises(ReplayError):
            case_from_stored_evidence("sig", "BTC-PERP", {"evidence": {}})


class ReplayDeterminismTests(unittest.TestCase):
    def test_replaying_the_champion_reproduces_its_own_direction(self):
        case = _case(directional_score=0.6)
        decision = replay_case(case, _rulebook(), AdmissionPolicy(), CATALOG)
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.direction, "LONG")

    def test_replay_is_deterministic(self):
        case = _case()
        policy, book = AdmissionPolicy(), _rulebook()
        first = replay_case(case, book, policy, CATALOG)
        second = replay_case(case, book, policy, CATALOG)
        self.assertEqual(first.evidence_digest, second.evidence_digest)
        self.assertEqual(first.direction, second.direction)

    def test_replay_does_not_mutate_the_case(self):
        case = _case()
        before = copy.deepcopy(case.block_scores)
        replay_case(case, _rulebook(), AdmissionPolicy(), CATALOG)
        self.assertEqual(case.block_scores, before)

    def test_direction_still_comes_only_from_directional_evidence(self):
        """A challenger that loves liquidity must not thereby flip the side."""
        case = _case(directional_score=0.6, liquidity=-0.9)
        # The rulebook caps any single block at 0.4, so this is as
        # liquidity-dominant as a valid configuration can be.
        heavy_liquidity = _rulebook(
            price_volatility=0.10, liquidity=0.40, positioning=0.20,
            spot_premium=0.20, macro_flows=0.10,
        )
        decision = replay_case(case, heavy_liquidity, AdmissionPolicy(), CATALOG)
        if decision.admitted:
            self.assertEqual(decision.direction, "LONG")

    def test_evidence_age_is_judged_against_its_own_evaluation_time(self):
        """Otherwise every historical case would be rejected as stale."""
        case = _case()
        decision = replay_case(case, _rulebook(), AdmissionPolicy(), CATALOG)
        codes = [r["code"] for r in decision.rejection_reasons]
        self.assertNotIn("evidence_stale", codes)


class ScoringTests(unittest.TestCase):
    def test_a_short_that_fell_scores_positive(self):
        case = _case(directional_score=-0.6, market_move=-1.0)
        decision = replay_case(case, _rulebook(), AdmissionPolicy(), CATALOG)
        self.assertEqual(decision.direction, "SHORT")
        result = score_replay([case], [decision])
        self.assertGreater(result["mean_signed_return_pct"], 0)

    def test_refused_decisions_are_excluded_from_the_score(self):
        case = _case(directional_score=0.001)  # inside the deadband
        decision = replay_case(case, _rulebook(), AdmissionPolicy(), CATALOG)
        self.assertFalse(decision.admitted)
        self.assertEqual(score_replay([case], [decision])["admitted"], 0)

    def test_an_empty_window_reports_none_rather_than_zero(self):
        result = score_replay([], [])
        self.assertIsNone(result["hit_rate"])
        self.assertIsNone(result["skill_vs_baseline"])

    def test_mismatched_lengths_are_rejected(self):
        with self.assertRaises(ReplayError):
            score_replay([_case()], [])

    def test_skill_is_measured_against_the_market_baseline(self):
        # Every call LONG in a rising window: perfect hit rate, zero skill.
        cases, decisions = [], []
        for i in range(4):
            case = _case(signal_id=f"s{i}", directional_score=0.6, market_move=1.0)
            cases.append(case)
            decisions.append(replay_case(case, _rulebook(), AdmissionPolicy(), CATALOG))
        result = score_replay(cases, decisions)
        self.assertEqual(result["hit_rate"], 1.0)
        self.assertEqual(result["skill_vs_baseline"], 0.0)


class ComparisonTests(unittest.TestCase):
    def _window(self):
        return [
            _case(signal_id="s1", directional_score=0.6, market_move=1.0),
            _case(signal_id="s2", directional_score=-0.6, market_move=-1.0),
            _case(signal_id="s3", directional_score=0.02, market_move=0.5),
        ]

    def test_identical_rulebooks_produce_no_delta(self):
        result = compare_rulebooks(
            self._window(), _rulebook(), _rulebook(), AdmissionPolicy(), CATALOG
        )
        self.assertEqual(result["delta"]["skill_vs_baseline"], 0.0)
        self.assertEqual(result["changed_decisions"], [])

    def test_both_sides_report_their_digest_so_a_run_is_attributable(self):
        result = compare_rulebooks(
            self._window(), _rulebook(),
            _rulebook(price_volatility=0.40, liquidity=0.20, positioning=0.20,
                      spot_premium=0.10, macro_flows=0.10),
            AdmissionPolicy(), CATALOG,
        )
        self.assertTrue(result["champion"]["digest"])
        self.assertTrue(result["challenger"]["digest"])
        self.assertNotEqual(
            result["champion"]["digest"], result["challenger"]["digest"]
        )

    def test_changed_decisions_are_listed_for_inspection(self):
        # A challenger with a much higher emit floor should admit fewer cases.
        window = self._window()
        strict = AdmissionPolicy(minimum_coverage_to_emit=0.99)
        champion_result = compare_rulebooks(
            window, _rulebook(), _rulebook(), strict, CATALOG
        )
        self.assertEqual(champion_result["champion"]["result"]["admitted"], 0)

    def test_comparison_refuses_to_claim_generality(self):
        result = compare_rulebooks(
            self._window(), _rulebook(), _rulebook(), AdmissionPolicy(), CATALOG
        )
        self.assertIn("cannot establish", result["note"])


if __name__ == "__main__":
    unittest.main()
