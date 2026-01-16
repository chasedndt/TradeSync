import unittest
import asyncio
import sys
import os
from unittest.mock import MagicMock, patch

# Add ingest-gateway to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../services/ingest-gateway")))

from app.models.market import MarketSnapshot
from app.models.event import NormalizedEvent
from app.ingest import ingest_market_snapshot

class TestMarketSnapshot(unittest.TestCase):
    def test_validation(self):
        """Verify MarketSnapshot validates correct data."""
        data = {
            "source": "test_exchange",
            "symbol": "BTC-USD",
            "mark": 10000.0,
            "funding": 0.0001,
            "oi": 100.0,
            "volume": 500.0,
            "raw": {"foo": "bar"}
        }
        snapshot = MarketSnapshot(**data)
        self.assertEqual(snapshot.source, "test_exchange")
        self.assertEqual(snapshot.symbol, "BTC-USD")
        self.assertEqual(snapshot.mark, 10000.0)
        self.assertEqual(snapshot.raw, {"foo": "bar"})

    def test_invalid_data(self):
        """Verify MarketSnapshot raises error on missing fields."""
        data = {
            "source": "test_exchange",
            # Missing symbol
            "mark": 10000.0,
            "funding": 0.0001,
            "oi": 100.0,
            "volume": 500.0,
            "raw": {"foo": "bar"}
        }
        with self.assertRaises(ValueError):
            MarketSnapshot(**data)

class TestIngestSnapshot(unittest.IsolatedAsyncioTestCase):
    async def test_ingest_market_snapshot(self):
        """Verify ingest_market_snapshot creates NormalizedEvent and calls DB."""
        snapshot = MarketSnapshot(
            source="test_exchange",
            symbol="BTC-USD",
            mark=10000.0,
            funding=0.0001,
            oi=100.0,
            volume=500.0,
            raw={"foo": "bar"}
        )

        with patch("app.ingest.asyncpg.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            
            # Setup async mocks
            future_execute = asyncio.Future()
            future_execute.set_result(None)
            mock_conn.execute.return_value = future_execute
            
            future_close = asyncio.Future()
            future_close.set_result(None)
            mock_conn.close.return_value = future_close

            await ingest_market_snapshot(snapshot)

            # Verify execute was called
            self.assertTrue(mock_conn.execute.called)
            args, _ = mock_conn.execute.call_args
            query = args[0]
            self.assertIn("INSERT INTO events", query)
            
            # Verify NormalizedEvent construction (indirectly via args)
            # args[1] is id, args[2] is ts, args[3] is source, etc.
            self.assertEqual(args[3], "test_exchange") # source
            self.assertEqual(args[4], "market_snapshot") # kind
            self.assertEqual(args[5], "BTC-USD") # symbol

if __name__ == '__main__':
    unittest.main()
