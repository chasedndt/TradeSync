from unittest.mock import AsyncMock, MagicMock
import asyncio
from app import book_history


def test_snapshot_rejects_bad_levels_and_caps_depth():
    book = {'bids': [{'price': 100, 'size': 2}] * 12, 'asks': [{'price': 'nan', 'size': 1}]}
    result = book_history.snapshot(book)
    assert len(result['levels']) == 10
    assert result['levels'][0]['notional_usd'] == 200
    assert book_history.snapshot({'bids': [{'price': 0, 'size': 2}]}) is None


def test_capture_atomically_replaces_bucket_and_prunes_time_and_count():
    redis, pipe = MagicMock(), MagicMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock()
    pipe.execute = AsyncMock()
    redis.pipeline.return_value = pipe
    asyncio.run(book_history.capture(redis, 'BTC-PERP', {'bids': [{'price': 100, 'size': 2}]}))
    redis.pipeline.assert_called_once_with(transaction=True)
    pipe.zadd.assert_called_once()
    assert pipe.zremrangebyscore.call_count == 2
    pipe.zremrangebyrank.assert_called_once_with(book_history.PREFIX+'BTC-PERP', 0, -241)
    pipe.expire.assert_called_once_with(book_history.PREFIX+'BTC-PERP', 3600)
    pipe.execute.assert_awaited_once()


def test_no_history_is_collecting_not_zero_liquidity():
    redis = MagicMock(zrange=AsyncMock(return_value=[]))
    result = asyncio.run(book_history.history(redis, 'BTC-PERP'))
    assert result['status'] == 'collecting'
    assert result['age_seconds'] is None
    assert result['authority'] == 'display_only'
