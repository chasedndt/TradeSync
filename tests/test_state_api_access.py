"""Callers find the operator token the way the guard expects it, and send it only in its header.

Every test here names its env file explicitly. None may fall through to the
real runtime.env, which holds the operator's secrets.
"""

from __future__ import annotations

from pathlib import Path

from tradesync_core.state_api_access import (
    HOST_STATE_API_URL,
    MIN_TOKEN_CHARS,
    RUNTIME_ENV_PATH_ENV,
    TOKEN_ENV,
    TOKEN_HEADER,
    host_operator_headers,
    operator_headers,
    read_env_file_value,
    token_state,
)

TOKEN = "t" * MIN_TOKEN_CHARS


def test_token_state_separates_unset_usable_and_too_short() -> None:
    assert token_state(None) == "disabled"
    assert token_state("   ") == "disabled"
    assert token_state(TOKEN) == "required"
    assert token_state("t" * (MIN_TOKEN_CHARS - 1)) == "misconfigured"


def test_a_container_sends_the_header_only_when_a_token_is_configured() -> None:
    assert operator_headers({}) == {}
    assert operator_headers({TOKEN_ENV: "  "}) == {}
    assert operator_headers({TOKEN_ENV: f" {TOKEN} "}) == {TOKEN_HEADER: TOKEN}


def test_the_last_assignment_in_the_env_file_wins_and_nothing_else_is_read(tmp_path: Path) -> None:
    env = tmp_path / "runtime.env"
    env.write_text(
        f"POSTGRES_PASSWORD=not-this\n{TOKEN_ENV}=replaced\n# {TOKEN_ENV}=commented-out\n  {TOKEN_ENV} = \"{TOKEN}\"  \n",
        encoding="utf-8",
    )
    assert read_env_file_value(env, TOKEN_ENV) == TOKEN
    assert read_env_file_value(env, "NOT_PRESENT") == ""
    assert read_env_file_value(tmp_path / "absent.env", TOKEN_ENV) == ""


def test_env_file_values_are_read_as_compose_reads_them(tmp_path: Path) -> None:
    env = tmp_path / "runtime.env"
    # set-runtime-secret.ps1 writes UTF-8 with a byte-order mark under Windows PowerShell.
    env.write_text(f"﻿{TOKEN_ENV}={TOKEN} # rotated 2026-09-15\n", encoding="utf-8")
    assert read_env_file_value(env, TOKEN_ENV) == TOKEN
    env.write_text(f"export {TOKEN_ENV}='{TOKEN}' # quoted\n", encoding="utf-8")
    assert read_env_file_value(env, TOKEN_ENV) == TOKEN


def test_a_host_tool_prefers_its_environment_then_runtime_env(tmp_path: Path) -> None:
    env = tmp_path / "runtime.env"
    env.write_text(f"{TOKEN_ENV}={TOKEN}\n", encoding="utf-8")
    other = "e" * 40
    assert host_operator_headers({TOKEN_ENV: other}, runtime_env=env) == {TOKEN_HEADER: other}
    assert host_operator_headers({}, runtime_env=env) == {TOKEN_HEADER: TOKEN}
    assert host_operator_headers({RUNTIME_ENV_PATH_ENV: str(env)}) == {TOKEN_HEADER: TOKEN}
    assert host_operator_headers({}, runtime_env=tmp_path / "absent.env") == {}


def test_host_tools_address_ipv4_loopback_rather_than_localhost() -> None:
    assert HOST_STATE_API_URL == "http://127.0.0.1:8000"
