"""The Windows host tools reach state-api on 127.0.0.1 and send the operator token with every request.

They run from Task Scheduler with no console, so a refusal after the operator
token is switched on would show only as a stalled cursor in a log file. Every
httpx client they open must carry the operator headers, whether or not a token
is configured today.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOST_TOOLS = (
    "tools/hermes_fleet_bridge.py",
    "tools/hermes_output_bridge.py",
    "tools/strikezone_quant_bridge.py",
    "tools/thesis_video.py",
)


@pytest.mark.parametrize("relative", HOST_TOOLS)
def test_a_host_tool_defaults_to_ipv4_loopback(relative: str) -> None:
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert "localhost:8000" not in source
    assert 'os.getenv("STATE_API_URL", HOST_STATE_API_URL)' in source


@pytest.mark.parametrize("relative", HOST_TOOLS)
def test_every_http_client_in_a_host_tool_carries_the_operator_headers(relative: str) -> None:
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    clients = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) in ("httpx.Client", "httpx.AsyncClient")
    ]
    assert clients, f"{relative} opens no httpx client"
    for call in clients:
        headers = [keyword.value for keyword in call.keywords if keyword.arg == "headers"]
        assert headers and ast.unparse(headers[0]) == "host_operator_headers()", (
            f"{relative}:{call.lineno} opens a client without the operator headers"
        )
