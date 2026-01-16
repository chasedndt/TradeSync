import unittest
from datetime import datetime
import sys
import os

# Add specific app directory to sys.path to handle hyphenated service name
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'services', 'core-scorer', 'app')))

from main import calculate_score, Event

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

    def test_calculate_score_hyperliquid_funding_high(self):
        events = [
            self.create_event(source="hyperliquid", kind="snapshot", payload={"funding": 0.02}),
        ]
        # +2
        self.assertEqual(calculate_score(events), 2.0)

    def test_calculate_score_hyperliquid_funding_low(self):
        events = [
            self.create_event(source="hyperliquid", kind="snapshot", payload={"funding": -0.02}),
        ]
        # -2
        self.assertEqual(calculate_score(events), -2.0)

    def test_calculate_score_hyperliquid_funding_neutral(self):
        events = [
            self.create_event(source="hyperliquid", kind="snapshot", payload={"funding": 0.005}),
        ]
        # 0
        self.assertEqual(calculate_score(events), 0.0)

    def test_calculate_score_mixed_clamped(self):
        events = [
            # 12 LONGs = +12
            *[self.create_event(source="tradingview", payload={"bias": "LONG"}) for _ in range(12)],
            # Funding high = +2
            self.create_event(source="hyperliquid", kind="snapshot", payload={"funding": 0.02}),
        ]
        # Total 14, clamped to 10
        self.assertEqual(calculate_score(events), 10.0)

    def test_calculate_score_mixed_clamped_negative(self):
        events = [
            # 12 SHORTs = -12
            *[self.create_event(source="tradingview", payload={"bias": "SHORT"}) for _ in range(12)],
            # Funding low = -2
            self.create_event(source="hyperliquid", kind="snapshot", payload={"funding": -0.02}),
        ]
        # Total -14, clamped to -10
        self.assertEqual(calculate_score(events), -10.0)

    def test_calculate_score_latest_snapshot_only(self):
        events = [
            # Older snapshot with high funding (+2)
            self.create_event(source="hyperliquid", kind="snapshot", payload={"funding": 0.02}, ts=datetime(2023, 1, 1, 10, 0)),
            # Newer snapshot with neutral funding (0)
            self.create_event(source="hyperliquid", kind="snapshot", payload={"funding": 0.00}, ts=datetime(2023, 1, 1, 10, 1)),
        ]
        # Should use the newer one -> 0
        self.assertEqual(calculate_score(events), 0.0)

        # Should use the newer one -> 0
        self.assertEqual(calculate_score(events), 0.0)

from fastapi.testclient import TestClient
from main import app

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
