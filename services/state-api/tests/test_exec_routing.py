import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
import json

client = TestClient(app)

@pytest.mark.asyncio
async def test_execute_routing_hyperliquid(monkeypatch):
    """Test that venue='hyperliquid' routes to the correct internal service."""
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    
    # Mock decision data
    mock_decision = {
        "id": "a4a43722-c0b4-4082-b640-4f8d6ec0b4d3",
        "opportunity_id": "e37f4127-df8e-4688-b337-2234fe4487ec",
        "venue": "hyperliquid",
        "requested": json.dumps({"size_usd": 50.0, "symbol": "BTC"}),
        "risk": json.dumps({"allowed": True}),
        "symbol": "BTC",
        "opp_status": "previewed",
        "quality": 100.0,
        "dir": "long",
        "expires_at": "2030-01-01T00:00:00+00:00"
    }
    
    # Mock signal
    mock_signal = {"symbol": "BTC", "bias": 0.5}

    # Mock DB Pool and Connection
    mock_conn = AsyncMock()
    mock_conn.fetchrow.side_effect = [
        None,           # 1. Idempotency Check (existing_order)
        mock_decision,  # 2. Re-validate Decision & Risk (dec_row)
        mock_signal     # Fetch latest signal (sig_row)
    ]
    
    # Partial mock of state.pool
    with patch("app.main.state") as mock_state:
        mock_state.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        # Mock httpx.AsyncClient.post
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json = MagicMock(return_value={
                "ok": True,
                "venue": "hyperliquid",
                "dry_run": True,
                "execution_enabled": True,
                "status": "placed",
                "order_id": "test-exec-id",
                "idempotency_key": str(mock_decision["id"]),
                "request_payload": {"size_usd": 50.0, "symbol": "BTC"},
                "response_payload": {},
                "error": None,
                "ts": "2026-07-11T00:00:00Z"
            })
            
            response = client.post("/actions/execute", json={"decision_id": str(mock_decision["id"]), "confirm": True})
            print(f"DEBUG: Response body: {response.json()}")
            
            # Assertions
            assert response.status_code == 200
            assert response.json()["status"] == "placed"
            assert response.json()["order_id"] == "test-exec-id"
            
            # Verify routing URL
            args, kwargs = mock_post.call_args
            assert args[0] == "http://exec-hl-svc:8004/exec/hl/order"
            assert kwargs["json"]["venue"] == "hyperliquid"
            assert kwargs["json"]["idempotency_key"] == str(mock_decision["id"])
            assert kwargs["json"]["side"] == "buy"
