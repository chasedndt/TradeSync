import unittest
from datetime import datetime
import sys
import os

# Loaded by file path: importing "main" by name picks up whichever main.py is
# first on sys.path, and this repository has one at its root that shadowed the
# service module entirely, so this file could not even be collected.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_service_module  # noqa: E402

_core_scorer = load_service_module("core_scorer_app", "core-scorer", "main")
calculate_score = _core_scorer.calculate_score
Event = _core_scorer.Event

class TestCoreScorer(unittest.TestCase):
    def create_event(self, source, kind="alert", payload=None, ts=None):
        if ts is None:
            ts = datetime.now()
        if payload is None:
            payload = {}
        return Event(
            id="mock_id",
            ts=ts,
            source=source,
            kind=kind,
            symbol="BTC",
            payload=payload
        )

    def test_calculate_score_tradingview(self):
        events = [
            self.create_event(source="tradingview", payload={"bias": "LONG"}),
            self.create_event(source="tradingview", payload={"bias": "LONG"}),
            self.create_event(source="tradingview", payload={"bias": "SHORT"}),
        ]
        # 1 + 1 - 1 = 1
        self.assertEqual(calculate_score(events), 1.0)

    # Funding events must be source "metrics", kind "market_snapshot". The
    # earlier tests here used source "hyperliquid", kind "snapshot", which
    # calculate_score filters out and fetch_events would never have selected
    # from the database either, so every funding assertion below was scoring an
    # empty event list and passing or failing for unrelated reasons.
    def metrics(self, funding, oi=None, ts=None):
        payload = {"funding": funding}
        if oi is not None:
            payload["oi"] = oi
        return self.create_event(
            source="metrics", kind="market_snapshot", payload=payload, ts=ts
        )

    def test_positive_funding_alone_is_a_small_short_bias(self):
        """Longs are paying shorts, so the crowd is long: bias against it."""
        self.assertEqual(calculate_score([self.metrics(0.02)]), -0.5)

    def test_negative_funding_alone_is_a_small_long_bias(self):
        self.assertEqual(calculate_score([self.metrics(-0.02)]), 0.5)

    def test_flat_funding_scores_nothing(self):
        self.assertEqual(calculate_score([self.metrics(0.0)]), 0.0)

    def test_negative_funding_with_rising_open_interest_is_a_squeeze_long(self):
        """Shorts paying to stay short while more of them pile in.

        Open interest is compared first-to-latest across the window, so this
        needs two snapshots; one snapshot can only ever produce the base bias.
        """
        events = [
            self.metrics(-0.02, oi=100.0, ts=datetime(2023, 1, 1, 10, 0)),
            self.metrics(-0.02, oi=110.0, ts=datetime(2023, 1, 1, 10, 1)),
        ]
        # +2.0 squeeze, +0.5 base funding bias
        self.assertEqual(calculate_score(events), 2.5)

    def test_positive_funding_with_rising_open_interest_is_a_squeeze_short(self):
        events = [
            self.metrics(0.02, oi=100.0, ts=datetime(2023, 1, 1, 10, 0)),
            self.metrics(0.02, oi=110.0, ts=datetime(2023, 1, 1, 10, 1)),
        ]
        self.assertEqual(calculate_score(events), -2.5)

    def test_rising_open_interest_below_the_threshold_is_not_a_squeeze(self):
        """0.5% is the floor; 0.4% is noise and must not add the 2.0."""
        events = [
            self.metrics(0.02, oi=100.0, ts=datetime(2023, 1, 1, 10, 0)),
            self.metrics(0.02, oi=100.4, ts=datetime(2023, 1, 1, 10, 1)),
        ]
        self.assertEqual(calculate_score(events), -0.5)

    def test_calculate_score_mixed_clamped(self):
        events = [
            # 12 LONGs = +12
            *[self.create_event(source="tradingview", payload={"bias": "LONG"}) for _ in range(12)],
            # Positive funding = -0.5
            self.metrics(0.02),
        ]
        # Total 11.5, clamped to 10
        self.assertEqual(calculate_score(events), 10.0)

    def test_calculate_score_mixed_clamped_negative(self):
        events = [
            # 12 SHORTs = -12
            *[self.create_event(source="tradingview", payload={"bias": "SHORT"}) for _ in range(12)],
            # Negative funding = +0.5
            self.metrics(-0.02),
        ]
        # Total -11.5, clamped to -10
        self.assertEqual(calculate_score(events), -10.0)


    def test_funding_comes_from_the_latest_snapshot(self):
        """Funding is read from the newest snapshot, not the oldest or the mean."""
        events = [
            self.metrics(0.02, ts=datetime(2023, 1, 1, 10, 0)),
            self.metrics(0.0, ts=datetime(2023, 1, 1, 10, 1)),
        ]
        self.assertEqual(calculate_score(events), 0.0)

        # Reversed input order must not change the answer: the function sorts.
        self.assertEqual(calculate_score(list(reversed(events))), 0.0)

from fastapi.testclient import TestClient

# Same aliased module as above. A bare "from main import app" picked up the
# repository root main.py, which has no FastAPI app, so this file could not be
# collected at all.
app = _core_scorer.app


class TestCoreScorerAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_healthz(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    # Note: Testing /signals/latest requires mocking the DB, which is more involved.
    # For this "double check", verifying healthz ensures the app initializes correctly.
    # We rely on the logic tests for the core functionality.

if __name__ == "__main__":
    unittest.main()
