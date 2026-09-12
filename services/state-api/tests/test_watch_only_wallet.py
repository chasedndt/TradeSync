from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
ADDRESS = '0x' + 'a' * 40

@pytest.mark.parametrize('address', ['', 'secret', '0x' + 'a' * 64, '0x' + 'g' * 40])
def test_invalid_address_never_calls_provider(address):
    with patch('app.main.httpx.AsyncClient') as transport:
        response = client.get('/state/execution/wallet-preview', params={'address': address})
    assert response.status_code == 422
    transport.assert_not_called()

def test_watch_lookup_does_not_change_configured_wallet():
    response = MagicMock()
    response.json.return_value = {'marginSummary': {'accountValue': '100', 'totalMarginUsed': '10'}, 'withdrawable': '90', 'assetPositions': []}
    transport = AsyncMock()
    transport.post.return_value = response
    with patch('app.main.WALLET_ADDRESS', ''), patch('app.main.httpx.AsyncClient') as factory:
        factory.return_value.__aenter__.return_value = transport
        result = client.get('/state/execution/wallet-preview', params={'address': ADDRESS})
        unconfigured = client.get('/state/execution/wallet-preview')
    assert result.status_code == 200
    assert result.json()['authority'] == 'read_only'
    assert result.json()['lookup_mode'] == 'session_watch_only'
    assert result.json()['account_value_usd'] == 100
    assert result.json()['observed_at']
    assert unconfigured.json()['configured'] is False
    assert transport.post.call_count == 1
    assert transport.post.call_args.kwargs['json'] == {'type': 'clearinghouseState', 'user': ADDRESS}

@pytest.mark.parametrize('payload', [{}, {'marginSummary': {}, 'assetPositions': []}, {'marginSummary': {'accountValue': 'NaN', 'totalMarginUsed': '0'}, 'assetPositions': []}])
def test_incomplete_response_not_zero_balance(payload):
    response = MagicMock()
    response.json.return_value = payload
    transport = AsyncMock()
    transport.post.return_value = response
    with patch('app.main.httpx.AsyncClient') as factory:
        factory.return_value.__aenter__.return_value = transport
        result = client.get('/state/execution/wallet-preview', params={'address': ADDRESS})
    assert result.status_code == 503
