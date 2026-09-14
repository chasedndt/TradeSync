import asyncio
from unittest.mock import AsyncMock, patch

from app import fleet_live, hermes_jobs


def test_live_overlay_preserves_history_redacts_errors_and_caches():
    async def run():
        fleet_live.invalidate()
        rows = [{'job_id': 'abcdef123456', 'tokens_24h': 123, 'last_status': 'error'}]
        mock = AsyncMock(return_value=[{'id': 'abcdef123456', 'last_status': 'ok',
                                      'last_error': 'secret=abcdefghijk', 'prompt': 'private',
                                      'schedule': {'display': 'every 30m'}}])
        with patch.object(hermes_jobs, 'list_jobs', mock):
            result, meta = await fleet_live.overlay(rows)
            await fleet_live.overlay(rows)
        assert result[0]['tokens_24h'] == 123 and result[0]['last_status'] == 'ok'
        assert result[0]['last_error'] == 'secret=[redacted]'
        assert 'prompt' not in result[0] and meta['source'] == 'gateway'
        assert mock.await_count == 1
    asyncio.run(run())


def test_unavailable_gateway_is_not_reported_live():
    async def run():
        fleet_live.invalidate()
        with patch.object(hermes_jobs, 'list_jobs', AsyncMock(side_effect=hermes_jobs.HermesJobsError(502, 'down'))):
            result, meta = await fleet_live.overlay([{'job_id': 'abcdef123456'}])
        assert result[0]['state_source'] == 'bridge'
        assert meta['status'] == 'unavailable' and meta['observed_at'] is None
    asyncio.run(run())


def test_missing_gateway_job_is_not_claimed_live():
    async def run():
        fleet_live.invalidate()
        with patch.object(hermes_jobs, 'list_jobs', AsyncMock(return_value=[])):
            result, _ = await fleet_live.overlay([{'job_id': 'abcdef123456'}])
        assert result[0]['gateway_missing'] is True
    asyncio.run(run())
