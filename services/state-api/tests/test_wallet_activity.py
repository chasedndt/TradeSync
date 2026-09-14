import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.wallet_activity import normalize, read_activity


def row(**updates):
    return dict(coin='BTC', side='A', limitPx='60000', px='60001', sz='0.1',
                timestamp=1700000000000, time=1700000000000, oid=123, tid=4,
                orderType='Stop Market', reduceOnly=True, isTrigger=True,
                triggerPx='59000', triggerCondition='Price below 59000',
                closedPnl='3', fee='0.1', feeToken='USDC', **updates)


def test_orders_preserve_triggers_and_reduce_only_without_actions():
    item = normalize([row()], 'orders')['rows'][0]
    assert item['side'] == 'SELL'
    assert item['reduce_only'] is True
    assert item['trigger_price'] == 59000
    assert item['order_id'] == '123'


def test_fills_preserve_fee_separately_from_closed_pnl():
    item = normalize([row()], 'fills')['rows'][0]
    assert item['closed_pnl'] == 3
    assert item['fee'] == .1
    assert item['fee_token'] == 'USDC'
    assert 'net_pnl' not in item


def test_invalid_rows_are_explicit_partial_not_empty_account():
    invalid = row()
    invalid['sz'] = 'nan'
    result = normalize([invalid, 'bad'], 'orders')
    assert result['status'] == 'partial'
    assert result['invalid_rows'] == 2
    assert result['rows'] == []
    with pytest.raises(ValueError): normalize({}, 'orders')


def test_sorts_latest_and_discloses_display_cap():
    rows = [dict(row(), timestamp=1700000000000+i) for i in range(110)]
    result = normalize(rows, 'orders')
    assert result['received_count'] == 110
    assert result['truncated'] is True
    assert len(result['rows']) == 100
    assert result['rows'][0]['time_ms'] > result['rows'][-1]['time_ms']


def test_one_dataset_failure_does_not_erase_other():
    async def post(url, json):
        if json['type'] == 'userFills': raise RuntimeError('private text')
        response = MagicMock()
        response.json.return_value = []
        return response
    with patch('app.wallet_activity.httpx.AsyncClient') as factory:
        factory.return_value.__aenter__.return_value = MagicMock(post=AsyncMock(side_effect=post))
        result = asyncio.run(read_activity('https://api.hyperliquid.xyz/info', '0x'+'a'*40))
    assert result['open_orders']['status'] == 'available'
    assert result['recent_fills']['status'] == 'unavailable'
    assert result['recent_fills']['rows'] is None
    assert 'private text' not in str(result)


def test_activity_rejects_private_key_shaped_input_before_provider():
    with patch('app.wallet_activity.read_activity') as read:
        assert TestClient(app).get('/state/execution/wallet-activity', params={'address': '0x'+'a'*64}).status_code == 422
        read.assert_not_called()
