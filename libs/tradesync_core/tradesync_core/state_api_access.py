"""How TradeSync processes present the operator token to state-api, and where they find it.

state-api can require an operator token on every change (POST, PUT, PATCH,
DELETE); ``services/state-api/app/access_guard.py`` enforces it. It is off
unless ``STATE_API_OPERATOR_TOKEN`` is set, and every process that makes
changes already sends the token when it has one, so switching the guard on does
not strand a caller:

- containers (state-api's own self-calls, core-scorer, discord-reader) read it
  from their environment, which compose fills from runtime.env;
- host tools (the Hermes fleet and output bridges, the StrikeZone quant bridge,
  the edition renderer) read the same line from runtime.env, so the value is
  kept in one place.

The token travels only in the ``X-Operator-Token`` header. Nothing here logs,
prints or returns it.

Host tools address state-api as ``127.0.0.1``, not ``localhost``. The published
port is bound to IPv4 loopback only, and Windows resolves ``localhost`` to
``::1`` first: measured on 2026-09-15, every new connection then waited about
two seconds before falling back to 127.0.0.1.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping

TOKEN_ENV = "STATE_API_OPERATOR_TOKEN"
TOKEN_HEADER = "X-Operator-Token"
MIN_TOKEN_CHARS = 32

HOST_STATE_API_URL = "http://127.0.0.1:8000"
RUNTIME_ENV_PATH_ENV = "TRADESYNC_RUNTIME_ENV"
DEFAULT_RUNTIME_ENV = Path(r"E:\Projects\TradeSync\dashboard-runtime\runtime.env")


def token_state(token: str | None) -> str:
    """``disabled`` when unset, ``required`` when usable, ``misconfigured`` when set but too short to trust."""
    value = (token or "").strip()
    if not value:
        return "disabled"
    return "required" if len(value) >= MIN_TOKEN_CHARS else "misconfigured"


def operator_headers(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """What a container adds to a change: the token header, or nothing when no token is configured."""
    token = (os.environ if environ is None else environ).get(TOKEN_ENV, "").strip()
    return {TOKEN_HEADER: token} if token else {}


def read_env_file_value(path: Path, name: str) -> str:
    """One variable's value from a compose env file: the last assignment wins, ``""`` when absent.

    Reads ``NAME=value`` the way compose does for the values used here: spaces
    around ``=`` and a leading ``export`` allowed, surrounding quotes removed,
    and a `` #`` comment after an unquoted value ignored. No other line is
    returned or kept.
    """
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return ""
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=(.*)$")
    value = ""
    for line in lines:
        match = pattern.match(line)
        if match:
            value = match.group(1)
    value = value.strip()
    if value[:1] in ("'", '"'):
        end = value.find(value[0], 1)
        if end > 0:
            return value[1:end]
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def host_operator_headers(
    environ: Mapping[str, str] | None = None, runtime_env: Path | None = None
) -> dict[str, str]:
    """What a host tool adds to a change: the token from its environment, otherwise from runtime.env."""
    env = os.environ if environ is None else environ
    token = env.get(TOKEN_ENV, "").strip()
    if not token:
        path = runtime_env or Path(env.get(RUNTIME_ENV_PATH_ENV) or DEFAULT_RUNTIME_ENV)
        token = read_env_file_value(path, TOKEN_ENV)
    return {TOKEN_HEADER: token} if token else {}
