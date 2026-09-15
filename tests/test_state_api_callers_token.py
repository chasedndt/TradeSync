"""Processes that change state through state-api send the operator token when one is configured, and nothing when not.

Only how each caller presents the token is tested here. Whether and how often
the claims harness, the Discord reader, the edition briefing and the timeframe
readings run is unchanged and not this file's concern.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_service_module  # noqa: E402

from tradesync_core.state_api_access import TOKEN_ENV, TOKEN_HEADER  # noqa: E402

_reader = load_service_module("discord_reader_app", "discord-reader", "main")
_harness = load_service_module("core_scorer_app", "core-scorer", "claims_harness")
STATE_API_APP = Path(__file__).resolve().parents[1] / "services" / "state-api" / "app"
TOKEN = "k" * 40


def _client(body: dict) -> MagicMock:
    response = MagicMock(status_code=200)
    response.raise_for_status = MagicMock()
    response.json.return_value = body
    return MagicMock(post=AsyncMock(return_value=response))


@pytest.mark.asyncio
async def test_the_discord_reader_sends_the_token_with_each_quarantine_submission() -> None:
    client = _client({"accepted": True})
    with patch.dict(os.environ, {TOKEN_ENV: TOKEN}):
        assert await _reader.submit(client, {"source": "discord", "payload": {}}) is True
    assert client.post.await_args.kwargs["headers"] == {TOKEN_HEADER: TOKEN}


@pytest.mark.asyncio
async def test_the_discord_reader_sends_no_token_header_when_none_is_configured() -> None:
    client = _client({"accepted": True})
    with patch.dict(os.environ, {TOKEN_ENV: ""}):
        await _reader.submit(client, {"source": "discord", "payload": {}})
    assert client.post.await_args.kwargs["headers"] == {}


@pytest.mark.asyncio
async def test_the_claims_harness_sends_the_token_with_each_ask() -> None:
    client = _client({"content": "[]"})
    with patch.dict(os.environ, {TOKEN_ENV: TOKEN}):
        assert await _harness.ask(client, "What did this post say?") == {"content": "[]"}
    assert client.post.await_args.kwargs["headers"] == {TOKEN_HEADER: TOKEN}


@pytest.mark.parametrize("module", ["editions.py", "horizon_reading.py"])
def test_state_api_calls_to_itself_carry_the_operator_headers(module: str) -> None:
    """The edition briefing and the timeframe readings ask the harness through state-api's own route."""
    tree = ast.parse((STATE_API_APP / module).read_text(encoding="utf-8"))
    self_posts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and ast.unparse(node.func).endswith(".post")
        and node.args
        and "SELF_URL" in ast.unparse(node.args[0])
    ]
    assert self_posts, f"{module} no longer calls state-api; update this test"
    for call in self_posts:
        assert any(
            keyword.arg == "headers" and ast.unparse(keyword.value) == "operator_headers()" for keyword in call.keywords
        ), f"{module}:{call.lineno} calls state-api without the operator headers"
