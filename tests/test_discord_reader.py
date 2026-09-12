"""The reader establishes "now" on first sight, submits oldest first, and never loses a message."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_service_module  # noqa: E402

from tradesync_core.discord_evidence import ChannelSpec  # noqa: E402

_reader = load_service_module("discord_reader_app", "discord-reader", "main")
CH = ChannelSpec("123456789012345678", "hermes-macro", "agent")


def _redis(cursor):
    r = MagicMock()
    r.get = AsyncMock(return_value=cursor)
    r.set = AsyncMock()
    return r


def _msg(i: int):
    return {"id": str(1420000000000000000 + i), "content": f"m{i}", "author": {"id": "1", "username": "h", "bot": True},
            "timestamp": "2026-09-12T18:30:00Z", "embeds": [], "attachments": []}


@pytest.mark.asyncio
async def test_first_sight_records_now_and_submits_nothing() -> None:
    r = _redis(None)
    with patch.object(_reader, "fetch_new_messages", AsyncMock(return_value=[_msg(7)])), \
         patch.object(_reader, "submit", AsyncMock()) as sub:
        stats = await _reader.poll_channel(MagicMock(), r, "tok", CH)
    assert stats == {"read": 0, "accepted": 0, "refused": 0}
    r.set.assert_awaited_once_with(_reader.CURSOR_KEY.format(channel_id=CH.channel_id), str(1420000000000000007))
    assert sub.await_count == 0


@pytest.mark.asyncio
async def test_messages_after_the_cursor_are_submitted_oldest_first_and_cursor_advances() -> None:
    r = _redis("1420000000000000001")
    with patch.object(_reader, "fetch_new_messages", AsyncMock(return_value=[_msg(2), _msg(3)])), \
         patch.object(_reader, "submit", AsyncMock(side_effect=[True, False])) as sub:
        stats = await _reader.poll_channel(MagicMock(), r, "tok", CH)
    assert stats == {"read": 2, "accepted": 1, "refused": 1}
    submitted = [c.args[1]["payload"]["message_id"] for c in sub.await_args_list]
    assert submitted == [str(1420000000000000002), str(1420000000000000003)]
    assert r.set.await_args_list[-1].args[1] == str(1420000000000000003)


@pytest.mark.asyncio
async def test_a_failed_submit_leaves_the_cursor_on_the_last_stored_message() -> None:
    r = _redis("1420000000000000001")
    with patch.object(_reader, "fetch_new_messages", AsyncMock(return_value=[_msg(2), _msg(3)])), \
         patch.object(_reader, "submit", AsyncMock(side_effect=[True, RuntimeError("state-api down")])):
        stats = await _reader.poll_channel(MagicMock(), r, "tok", CH)
    assert stats["accepted"] == 1
    assert r.set.await_args_list[-1].args[1] == str(1420000000000000002)  # message 3 will be retried


@pytest.mark.asyncio
async def test_a_failed_read_changes_nothing() -> None:
    r = _redis("1420000000000000001")
    with patch.object(_reader, "fetch_new_messages", AsyncMock(return_value=None)):
        stats = await _reader.poll_channel(MagicMock(), r, "tok", CH)
    assert stats == {"read": 0, "accepted": 0, "refused": 0} and r.set.await_count == 0


def test_not_configured_without_both_token_and_channels() -> None:
    with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "", "DISCORD_READER_CHANNELS": "a=123456789012345678"}):
        assert _reader.configured() is None
    with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "x", "DISCORD_READER_CHANNELS": ""}):
        assert _reader.configured() is None
    with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "x", "DISCORD_READER_CHANNELS": "a=123456789012345678:alerts"}):
        token, specs = _reader.configured()
        assert token == "x" and specs[0].kind == "alerts"


def test_the_token_is_never_printed() -> None:
    import inspect

    source = inspect.getsource(_reader)
    assert "print(f\"[DiscordReader] {channel.label}: HTTP" in source
    assert "token}" not in source.replace('f"Bot {token}"', "")  # only in the Authorization header
