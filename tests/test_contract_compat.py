import httpx
import pytest
import time

BASE_URL = "http://localhost:8000"

@pytest.mark.asyncio
async def test_health_check_canonical():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/state/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "postgres" in data

@pytest.mark.asyncio
async def test_opportunities_alias_vs_canonical():
    async with httpx.AsyncClient() as client:
        # Canonical
        resp_c = await client.get(f"{BASE_URL}/state/opportunities")
        assert resp_c.status_code == 200
        
        # Alias
        resp_a = await client.get(f"{BASE_URL}/opps")
        assert resp_a.status_code == 200
        
        # Verify Deprecation headers on alias
        assert resp_a.headers.get("Deprecation") == "true"
        assert "/state/opportunities" in resp_a.headers.get("Link", "")
        
        # Schema parity check (at least top level keys if empty)
        # If there's data, check keys of first item
        data_c = resp_c.json()
        data_a = resp_a.json()
        assert isinstance(data_c, list)
        assert isinstance(data_a, list)
        if len(data_c) > 0 and len(data_a) > 0:
            assert data_c[0].keys() == data_a[0].keys()

@pytest.mark.asyncio
async def test_timeframe_precedence():
    async with httpx.AsyncClient() as client:
        symbol = "BTC-PERP"
        # 1. tf only
        resp = await client.get(f"{BASE_URL}/state/events/latest?symbol={symbol}&tf=5m")
        assert resp.status_code == 200
        # If results exist, they should all be 5m
        for evt in resp.json():
            assert evt["timeframe"] == "5m"
            
        # 2. timeframe only
        resp = await client.get(f"{BASE_URL}/state/events/latest?symbol={symbol}&timeframe=15m")
        assert resp.status_code == 200
        for evt in resp.json():
            assert evt["timeframe"] == "15m"
            
        # 3. both (timeframe should win)
        resp = await client.get(f"{BASE_URL}/state/events/latest?symbol={symbol}&tf=5m&timeframe=15m")
        assert resp.status_code == 200
        for evt in resp.json():
             assert evt["timeframe"] == "15m"

@pytest.mark.asyncio
async def test_symbol_normalization():
    async with httpx.AsyncClient() as client:
        # Use BTCUSDT and check if response contains BTC-PERP
        resp = await client.get(f"{BASE_URL}/state/opportunities?symbol=BTCUSDT")
        assert resp.status_code == 200
        for opp in resp.json():
            assert opp["symbol"] == "BTC-PERP"

@pytest.mark.asyncio
async def test_venue_normalization():
    async with httpx.AsyncClient() as client:
        # Use 'hl' and check if it resolves (mocked positions should have hyperliquid)
        resp = await client.get(f"{BASE_URL}/state/positions?venue=hl")
        assert resp.status_code == 200
        for pos in resp.json():
            assert pos["venue"] == "hyperliquid"

@pytest.mark.asyncio
async def test_execution_status_alias():
     async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/execution/status")
        assert resp.status_code == 200
        assert resp.headers.get("Deprecation") == "true"
        assert "/state/execution/status" in resp.headers.get("Link", "")
        data = resp.json()
        assert "execution_enabled" in data
        assert "venues" in data
