
import sys
import os
import json
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

# Add specific app directory to sys.path to handle hyphenated service name
# Add services/ingest-gateway to sys.path so we can import app as a package
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'services', 'ingest-gateway')))

from app.main import app

class TestIngestGateway(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_healthz(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    @patch("app.db.get_db_connection", new_callable=AsyncMock)
    def test_ingest_tv_valid_payload(self, mock_connect):
        """
        Test that a valid TradingView payload is accepted and returns 200 OK.
        """
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value = None
        mock_conn.close.return_value = None
        
        payload = {
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "bias": "LONG",
            "confidence": 85.5,
            "price": 60000.0,
            "passphrase": "secure_phrase"
        }
        
        response = self.client.post("/ingest/tv", json=payload)
        
        # Assert Response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("id", data)
        
        # Assert DB Interaction
        self.assertTrue(mock_connect.called)
        self.assertTrue(mock_conn.execute.called)
        
        # Inspect the arguments passed to execute to verify provenance/meta
        args = mock_conn.execute.call_args[0]
        query = args[0]
        self.assertIn("INSERT INTO events", query)
        
        # Args: query, id, ts, source, kind, symbol, timeframe, payload, provenance, hash
        # provenance is at index 8 (9th argument)
        provenance_arg = args[8] 
        provenance = json.loads(provenance_arg)
        self.assertIn("ip", provenance)
        self.assertIn("user_agent", provenance)
        self.assertIn("received_at", provenance)

    def test_ingest_tv_invalid_missing_field(self):
        """
        Test that missing required fields (symbol) returns 400 validation_failed.
        """
        payload = {
            "timeframe": "15m",
            "bias": "LONG"
            # Missing symbol
        }
        
        response = self.client.post("/ingest/tv", json=payload)
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "validation_failed")
        self.assertIn("details", data)
        self.assertIn("symbol", str(data["details"]))

    def test_ingest_tv_invalid_type(self):
        """
        Test that invalid types (string for float) returns 400 validation_failed.
        """
        payload = {
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "confidence": "NOT_A_NUMBER" 
        }
        
        response = self.client.post("/ingest/tv", json=payload)
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "validation_failed")
        self.assertIn("confidence", str(data["details"]))

    @patch("app.db.get_db_connection", new_callable=AsyncMock)
    def test_ingest_tv_db_error(self, mock_connect):
        """
        Test that database errors return 500 db_error without leaking details.
        """
        # Simulate a DB connection error
        mock_connect.side_effect = Exception("Critical DB Failure")
        
        payload = {
            "symbol": "BTCUSDT",
            "timeframe": "15m"
        }
        
        # Patch print to suppress the expected "DB Error" message in the console
        with patch("builtins.print"):
            response = self.client.post("/ingest/tv", json=payload)
        
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertEqual(data["error"], "db_error")
        # Ensure internal error string is NOT in the response
        self.assertNotIn("Critical DB Failure", json.dumps(data))

if __name__ == "__main__":
    unittest.main()
