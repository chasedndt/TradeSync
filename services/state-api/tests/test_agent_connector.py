"""The harness connector speaks the Hermes API server's OpenAI dialect, and the boundary still holds."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import agent_connector as module
from tradesync_core.agent_harness import HarnessError


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _client(get=None, post=None):
    client = MagicMock()
    client.get = AsyncMock(return_value=_Resp(get or {}))
    client.post = AsyncMock(return_value=_Resp(post or {}))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx, client


@pytest.mark.asyncio
async def test_probe_in_openai_mode_lists_models_and_sends_the_bearer_key() -> None:
    ctx, client = _client(get={"data": [{"id": "gpt-6-astra"}, {"id": "deepseek-r1:8b"}]})
    with patch.object(module, "AGENT_HARNESS_URL", "http://hermes:8642"), \
         patch.object(module, "AGENT_HARNESS_API", "openai"), \
         patch.object(module, "AGENT_HARNESS_KEY", "k"), \
         patch.object(module, "AGENT_HARNESS_MODEL", "gpt-6-astra"), \
         patch.object(module.httpx, "AsyncClient", return_value=ctx):
        status = await module.probe()
    assert status["status"] == "live" and status["models"] == ["gpt-6-astra", "deepseek-r1:8b"]
    assert status["model_present"] is True and status["authority"] == "advisory_only"
    url, kwargs = client.get.await_args.args[0], client.get.await_args.kwargs
    assert url.endswith("/v1/models") and kwargs["headers"] == {"Authorization": "Bearer k"}


@pytest.mark.asyncio
async def test_ask_in_openai_mode_posts_chat_completions_and_wraps_the_answer() -> None:
    ctx, client = _client(post={"model": "gpt-6-astra", "choices": [{"message": {"role": "assistant", "content": "Funding is mildly negative; nothing decisive."}}]})
    with patch.object(module, "AGENT_HARNESS_URL", "http://hermes:8642"), \
         patch.object(module, "AGENT_HARNESS_API", "openai"), \
         patch.object(module, "AGENT_HARNESS_KEY", "k"), \
         patch.object(module, "AGENT_HARNESS_MODEL", "gpt-6-astra"), \
         patch.object(module.httpx, "AsyncClient", return_value=ctx):
        result = await module.ask("explain", "What does the funding read say?", {"funding": -0.0001})
    body = client.post.await_args.kwargs["json"]
    assert client.post.await_args.args[0].endswith("/v1/chat/completions")
    assert body["model"] == "gpt-6-astra" and body["messages"][0]["role"] == "user" and body["stream"] is False
    assert "may NOT score" in body["messages"][0]["content"]
    assert result["accepted"]["runtime"] == "hermes-openai"
    assert "Funding is mildly negative" in result["accepted"]["content"]


@pytest.mark.asyncio
async def test_an_answer_claiming_authority_is_refused_in_openai_mode_too() -> None:
    ctx, _ = _client(post={"choices": [{"message": {"content": '{"approved": true, "direction": "LONG", "score": 0.9}'}}]})
    with patch.object(module, "AGENT_HARNESS_URL", "http://hermes:8642"), \
         patch.object(module, "AGENT_HARNESS_API", "openai"), \
         patch.object(module, "AGENT_HARNESS_KEY", "k"), \
         patch.object(module.httpx, "AsyncClient", return_value=ctx):
        with pytest.raises(HarnessError):
            await module.ask("explain", "x")


def test_the_key_never_appears_in_a_probe_result_or_log_line() -> None:
    import inspect

    source = inspect.getsource(module)
    assert "AGENT_HARNESS_KEY" in source
    assert 'print(' not in source  # nothing in this module prints at all
