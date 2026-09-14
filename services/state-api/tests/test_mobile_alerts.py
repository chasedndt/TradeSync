import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import mobile_alerts as mobile


def test_control_routes_fail_closed_without_server_key():
    with patch.dict('os.environ', {'MOBILE_ALERTS_CONTROL_KEY': ''}):
        client = TestClient(app)
        assert client.get('/state/mobile-alerts/status').json()['configured'] is False
        assert client.get('/state/mobile-alerts/devices').status_code == 503


def test_wrong_authorization_cannot_read_device_details():
    with patch.dict('os.environ', {'MOBILE_ALERTS_CONTROL_KEY': 'a'*32}):
        assert TestClient(app).get('/state/mobile-alerts/devices', headers={'X-API-Key': 'wrong'}).status_code == 403


def test_templates_cannot_contain_caller_trade_or_wallet_content():
    result = mobile.message('attention', uuid.UUID(int=1))
    assert result == 'TradeSync needs attention. Open your dashboard. Reference 00000000'
    with pytest.raises(ValueError): mobile.message('balance=1000 seed=secret', uuid.uuid4())


def test_only_generated_topics_can_be_published():
    with patch('app.mobile_alerts.httpx.AsyncClient') as client:
        with pytest.raises(ValueError): asyncio.run(mobile.publish('../admin', 'test', uuid.uuid4()))
        client.assert_not_called()


def test_provider_acceptance_is_verified_not_assumed_from_http_success():
    topic, identity = 'tradesync-'+'a'*48, uuid.uuid4()
    response = MagicMock()
    response.json.return_value = {'id': 'provider123', 'event': 'message', 'topic': topic, 'message': mobile.message('test', identity)}
    with patch('app.mobile_alerts.httpx.AsyncClient') as factory:
        transport = MagicMock(post=AsyncMock(return_value=response))
        factory.return_value.__aenter__.return_value = transport
        assert asyncio.run(mobile.publish(topic, 'test', identity)) == 'provider123'
        assert factory.call_args.kwargs['follow_redirects'] is False
        assert transport.post.call_args.args[0] == 'https://ntfy.sh/'+topic
        response.json.return_value['topic'] = 'different-topic'
        with pytest.raises(ValueError): asyncio.run(mobile.publish(topic, 'test', identity))


def test_enqueue_has_idempotency_and_expiry_without_external_send():
    conn = MagicMock(fetchval=AsyncMock(return_value=uuid.uuid4()))
    with patch('app.mobile_alerts.publish') as send:
        asyncio.run(mobile.enqueue(conn, uuid.uuid4(), 'attention', 'paper-trade:123:opened'))
        sql = conn.fetchval.call_args.args[0]
        assert 'ON CONFLICT(device_id,dedupe_key)' in sql
        assert "interval '10 minutes'" in sql
        send.assert_not_called()


def test_dispatch_does_not_touch_database_or_network_when_disabled():
    pool = MagicMock()
    with patch.dict('os.environ', {'MOBILE_ALERTS_CONTROL_KEY': ''}), patch('app.mobile_alerts.publish') as send:
        asyncio.run(mobile.dispatch_one(pool))
        pool.acquire.assert_not_called()
        send.assert_not_called()


def test_paper_producer_is_disabled_without_control_setup():
    pool = MagicMock()
    with patch.dict('os.environ', {'MOBILE_ALERTS_CONTROL_KEY': ''}), patch('app.mobile_alerts.publish') as send:
        asyncio.run(mobile.produce_paper_events(pool))
        pool.acquire.assert_not_called()
        send.assert_not_called()


def test_preferences_require_authorization_even_for_opt_out():
    with patch.dict('os.environ', {'MOBILE_ALERTS_CONTROL_KEY': 'a'*32}):
        result = TestClient(app).post(f'/state/mobile-alerts/devices/{uuid.uuid4()}/preferences', json={'paper_events': False})
        assert result.status_code == 403


def test_producer_failure_does_not_strand_existing_delivery_queue():
    with patch.object(mobile, 'produce_paper_events', AsyncMock(side_effect=RuntimeError('private detail'))), patch.object(mobile, 'dispatch_one', AsyncMock()) as dispatch:
        result = asyncio.run(mobile.worker_tick(MagicMock()))
        dispatch.assert_awaited_once()
        assert result == 'paper_intake:RuntimeError'


def test_both_worker_failures_are_visible_without_sensitive_exception_text():
    with patch.object(mobile, 'produce_paper_events', AsyncMock(side_effect=RuntimeError('private'))), patch.object(mobile, 'dispatch_one', AsyncMock(side_effect=TimeoutError('private'))):
        assert asyncio.run(mobile.worker_tick(MagicMock())) == 'paper_intake:RuntimeError, delivery:TimeoutError'


def test_worker_cancellation_does_not_continue_sending():
    with patch.object(mobile, 'produce_paper_events', AsyncMock(side_effect=asyncio.CancelledError)), patch.object(mobile, 'dispatch_one', AsyncMock()) as dispatch:
        with pytest.raises(asyncio.CancelledError): asyncio.run(mobile.worker_tick(MagicMock()))
        dispatch.assert_not_awaited()
