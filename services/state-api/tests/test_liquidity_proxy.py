from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from app import main

client = TestClient(main.app)


@pytest.mark.parametrize('route', ['book-history', 'liquidation-context'])
def test_proxy_validates_symbol_and_preserves_coverage(route):
    response = MagicMock(status_code=200)
    response.json.return_value = {'authority': 'context_only', 'samples': [], 'status': 'collecting'}
    with patch.object(main, '_market_data_get', return_value=response) as fetch:
        assert client.get(f'/state/market/{route}?symbol=../../secrets').status_code == 400
        fetch.assert_not_called()
        result = client.get(f'/state/market/{route}?symbol=BTC-PERP')
        assert result.json()['status'] == 'collecting'
        assert fetch.call_args.args[0] == f'/{route}/BTC-PERP'


@pytest.mark.parametrize('route', ['book-history', 'liquidation-context'])
def test_provider_failure_is_not_empty_success(route):
    with patch.object(main, '_market_data_get', side_effect=RuntimeError('private diagnostic')):
        result = client.get(f'/state/market/{route}')
    assert result.status_code == 503
    assert 'private diagnostic' not in result.text
