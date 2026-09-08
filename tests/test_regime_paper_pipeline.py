"""End-to-end contract tests for the regime-backed paper path.

These cover the two seams that carry evidence between services: what the
producer publishes, and what the opportunity builder does with it.

Every service package in this repository is named ``app``, so importing one by
that name would shadow the others for the rest of the test session. Each is
loaded here under a private name instead: ``paper_producer`` by file path, and
the fusion worker through a package alias so its relative imports still
resolve.
"""

import asyncio
import importlib
import importlib.util
import json
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs" / "tradesync_core"))

from tradesync_core.paper_signal import decide_paper_signal  # noqa: E402


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


producer = _load_module(
    "core_scorer_paper_producer",
    ROOT / "services" / "core-scorer" / "app" / "paper_producer.py",
)

FUSION_PACKAGE = "fusion_engine_app"


def _load_fusion_worker():
    """Import the fusion worker without claiming the global ``app`` name."""
    package = types.ModuleType(FUSION_PACKAGE)
    package.__path__ = [str(ROOT / "services" / "fusion-engine" / "app")]
    sys.modules.setdefault(FUSION_PACKAGE, package)
    return importlib.import_module(f"{FUSION_PACKAGE}.worker")

NOW_MS = 1_767_297_600_000
CATALOG = {
    "catalog_id": "tradesync-hyperliquid-market-features",
    "version": "1.2.0",
    "digest": "catalogdigest",
}


def _decision(score=0.42, coverage=0.55, risk=0.5, allowed=True):
    evaluation = {
        "rulebook_id": "tradesync-intraday-regime",
        "rulebook_version": "1.0.0",
        "config_digest": "rulebookdigest",
        "weighted_score": score,
        "data_coverage": coverage,
        "paper_risk_multiplier": risk,
        "contributions": {},
        "missing_blocks": [],
        "risk_caps_applied": [],
        "calculation": "sum(weight * quality * score) / sum(weight * quality)",
    }
    features = [
        {
            "feature_id": "hl_return_1h_pct",
            "block": "price_volatility",
            "provenance": "derived",
            "observed_at_ms": NOW_MS - 1_000,
            "scoring_allowed": allowed,
            "score": score,
            "data_quality": 0.9,
            "history_count": 168,
        }
    ]
    return decide_paper_signal(
        symbol="BTC-PERP",
        evaluation=evaluation,
        feature_results=features,
        catalog_summary=CATALOG,
        evaluated_at_ms=NOW_MS,
        directional={
            "score": score,
            "coverage": 1.0,
            "contributors": [
                {"feature_id": "hl_return_1h_pct", "score": score, "quality": 1.0}
            ],
            "admitted_feature_ids": ["hl_return_1h_pct"],
            "ready_feature_ids": ["hl_return_1h_pct"],
        },
    )


class RecordingRedis:
    def __init__(self):
        self.published = []

    async def xadd(self, stream, fields):
        self.published.append((stream, fields))


class ProducerPublishTests(unittest.TestCase):
    def test_admitted_signal_is_published_with_its_evidence(self):
        decision = _decision()
        self.assertTrue(decision.admitted)
        redis = RecordingRedis()
        created = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
        published = asyncio.run(
            producer.publish_decision(redis, decision, "signal-1", created)
        )
        self.assertTrue(published)
        stream, fields = redis.published[0]
        self.assertEqual(stream, producer.SIGNAL_STREAM)
        envelope = json.loads(fields["data"])
        self.assertEqual(envelope["schema_version"], "paper_signal_v1")
        self.assertEqual(envelope["evidence_digest"], decision.evidence_digest)
        self.assertEqual(envelope["paper_signal"]["direction"], "LONG")
        self.assertFalse(envelope["paper_signal"]["execution_authority"])

    def test_refusal_is_never_published(self):
        decision = _decision(coverage=0.06)
        self.assertFalse(decision.admitted)
        redis = RecordingRedis()
        published = asyncio.run(
            producer.publish_decision(
                redis, decision, "signal-2", datetime.now(timezone.utc)
            )
        )
        self.assertFalse(published)
        self.assertEqual(redis.published, [])

    def test_refusal_note_lists_every_reason_code(self):
        decision = _decision(score=0.0, coverage=0.0)
        note = producer._refusal_note(decision)
        self.assertIn("No paper opportunity produced", note)
        for reason in decision.rejection_reasons:
            self.assertIn(reason["code"], note)


class RegimeSourceTests(unittest.TestCase):
    """The producer must ask for the symbol it intends to record."""

    @classmethod
    def setUpClass(cls):
        cls.source = _load_module(
            "core_scorer_regime_source",
            ROOT / "services" / "core-scorer" / "app" / "regime_source.py",
        )

    def _fetch(self, payload, status=200):
        recorded = {}

        class FakeResponse:
            status_code = status

            def raise_for_status(self):
                if status >= 400:
                    raise self.source.httpx.HTTPError("boom")

            def json(self):
                return payload

        class FakeClient:
            async def get(_self, url, params=None, timeout=None):
                recorded["url"] = url
                recorded["params"] = params
                return FakeResponse()

            async def aclose(_self):
                pass

        evidence = asyncio.run(
            self.source.fetch_regime_evidence(
                "ETH-PERP", state_api_url="http://state-api:8000", client=FakeClient()
            )
        )
        return evidence, recorded

    def test_the_requested_symbol_is_sent_to_the_state_api(self):
        payload = {
            "baseline_evaluation": {"weighted_score": 0.1},
            "feature_results": [],
            "catalog": {"version": "1.1.0"},
            "source_status": {"status": "live", "symbol": "ETH-PERP"},
        }
        evidence, recorded = self._fetch(payload)
        self.assertTrue(evidence.available)
        self.assertEqual(
            recorded["params"], {"venue": "hyperliquid", "symbol": "ETH-PERP"}
        )
        self.assertTrue(recorded["url"].endswith("/state/regime-lab/overview"))

    def test_non_live_observations_are_not_treated_as_evidence(self):
        payload = {
            "baseline_evaluation": {"weighted_score": 0.1},
            "source_status": {"status": "unavailable"},
        }
        evidence, _ = self._fetch(payload)
        self.assertFalse(evidence.available)
        self.assertIn("unavailable", evidence.reason)

    def test_a_missing_baseline_evaluation_is_not_a_zero_score(self):
        evidence, _ = self._fetch({"source_status": {"status": "live"}})
        self.assertFalse(evidence.available)
        self.assertEqual(evidence.evaluation, {})
        self.assertIn("no baseline evaluation", evidence.reason)


class FusionPassThroughTests(unittest.TestCase):
    """The opportunity builder must preserve regime evidence, not re-score it."""

    @classmethod
    def setUpClass(cls):
        cls.worker = _load_fusion_worker()

    def _envelope(self, decision, signal_id="signal-1"):
        return producer.build_stream_payload(
            decision, signal_id, datetime.now(timezone.utc)
        )

    def test_regime_envelope_is_recognised(self):
        envelope = self._envelope(_decision())
        self.assertTrue(self.worker.is_paper_signal_envelope(envelope))

    def test_legacy_envelope_is_not_treated_as_a_paper_signal(self):
        legacy = {
            "id": "legacy-1",
            "symbol": "BTC-PERP",
            "score": 3.0,
            "event_ids": ["11111111-1111-1111-1111-111111111111"],
        }
        self.assertFalse(self.worker.is_paper_signal_envelope(legacy))

    def test_envelope_without_a_digest_is_rejected(self):
        envelope = self._envelope(_decision())
        envelope["evidence_digest"] = ""
        self.assertFalse(self.worker.is_paper_signal_envelope(envelope))

    def test_opportunity_carries_the_directional_score_as_bias(self):
        """bias is a directional strength, so it must not carry suitability."""
        decision = _decision(score=0.42, coverage=0.55)
        envelope = self._envelope(decision)
        recorded = self._run_builder(envelope, insert_result="opp-1")
        self.assertEqual(recorded["bias"], decision.directional_score)
        self.assertAlmostEqual(recorded["quality"], decision.data_coverage * 100)
        self.assertEqual(recorded["dir"], "LONG")
        self.assertEqual(
            recorded["links"]["evidence_digest"], decision.evidence_digest
        )
        self.assertEqual(recorded["confluence"], decision.to_dict())

    def test_a_refusal_envelope_never_becomes_an_opportunity(self):
        decision = _decision(coverage=0.06)
        envelope = producer.build_stream_payload(
            decision, "signal-3", datetime.now(timezone.utc)
        )
        envelope["paper_signal"] = decision.to_dict()
        self.assertIsNone(self._run_builder(envelope, insert_result="opp-2"))

    def test_an_envelope_claiming_execution_authority_is_refused(self):
        decision = _decision()
        envelope = self._envelope(decision)
        envelope["paper_signal"]["execution_authority"] = True
        self.assertIsNone(self._run_builder(envelope, insert_result="opp-3"))

    def test_duplicate_delivery_does_not_double_count(self):
        envelope = self._envelope(_decision())
        before = self.worker.stats["opps_created"]
        self._run_builder(envelope, insert_result="opp-4")
        self._run_builder(envelope, insert_result=None)  # UNIQUE(signal_id) hit
        self.assertEqual(self.worker.stats["opps_created"], before + 1)

    def _run_builder(self, envelope, insert_result):
        """Run the builder against recording stand-ins and return the row."""
        worker = self.worker
        recorded = {}
        acked = []

        class FakeDb:
            async def insert_opportunity(self, data):
                recorded.update(data)
                return insert_result

        class FakeRedisClient:
            class client:
                @staticmethod
                async def xack(stream, group, msg_id):
                    acked.append(msg_id)

        db_module = sys.modules.setdefault(
            f"{FUSION_PACKAGE}.db", types.ModuleType(f"{FUSION_PACKAGE}.db")
        )
        db_module.db = FakeDb()
        original_redis = worker.redis_client
        worker.redis_client = FakeRedisClient
        try:
            asyncio.run(
                worker.build_paper_signal_opportunity(
                    envelope, "msg-1", envelope["symbol"], envelope["id"]
                )
            )
        finally:
            worker.redis_client = original_redis

        self.assertEqual(acked, ["msg-1"], "every message must be acknowledged")
        return recorded or None


if __name__ == "__main__":
    unittest.main()
