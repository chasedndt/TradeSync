import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
import json

client = TestClient(app)

@pytest.mark.asyncio
async def test_execute_routing_hyperliquid():
    """Test that venue='hyperliquid' routes to the correct internal service."""
    
    # Mock decision data
    mock_decision = {
        "id": "a4a43722-c0b4-4082-b640-4f8d6ec0b4d3",
        "opportunity_id": "e37f4127-df8e-4688-b337-2234fe4487ec",
        "venue": "hyperliquid",
        "requested": json.dumps({"size_usd": 50.0, "symbol": "BTC"}),
        "risk": json.dumps({"allowed": True}),
        "symbol": "BTC",
        "opp_status": "previewed",
        "quality": 1.0,
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
            mock_post.return_value.json.return_value = {
                "ok": True,
                "venue": "hyperliquid",
                "execution_id": "test-exec-id",
                "dry_run": True
            }
            
            response = client.post("/actions/execute", json={"decision_id": str(mock_decision["id"]), "confirm": True})
            print(f"DEBUG: Response body: {response.json()}")
            
            # Assertions
            assert response.status_code == 200
            assert response.json()["status"] == "placed"
            assert response.json()["execution_id"] == "test-exec-id"
            
            # Verify routing URL
            args, kwargs = mock_post.call_args
            assert args[0] == "http://exec-hl-svc:8004/exec/hl/order"
            assert kwargs["json"]["venue"] == "hyperliquid"
            assert kwargs["json"]["client_id"] == str(mock_decision["id"])

@pytest.mark.asyncio
async def test_execute_routing_drift():
    """Test that venue='drift' routes to the correct internal service."""
    
    mock_decision = {
        "id": "deacb09c-c29a-43ca-8e5a-b83dba5ca8e7",
        "opportunity_id": "98bdc9ab-7a1b-45a8-9464-13a1b0441825",
        "venue": "drift",
        "requested": json.dumps({"size_usd": 50.0, "symbol": "BTC"}),
        "risk": json.dumps({"allowed": True}),
        "symbol": "BTC",
        "opp_status": "previewed",
        "quality": 1.0,
        "expires_at": "2030-01-01T00:00:00+00:00"
    }
    
    mock_conn = AsyncMock()
    mock_conn.fetchrow.side_effect = [None, mock_decision, {"symbol": "BTC"}]
    
    with patch("app.main.state") as mock_state:
        mock_state.pool.acquire.return_value.__aenter__.return_value = mock_conn
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True, "execution_id": "drift-id", "dry_run": True}
            
            response = client.post("/actions/execute", json={"decision_id": str(mock_decision["id"]), "confirm": True})
            
            assert response.status_code == 200
            args, _ = mock_post.call_args
            assert args[0] == "http://exec-drift-svc:8003/exec/drift/order"
