"""Talk to an advisory agent harness, and refuse anything it should not say.

The three capabilities the pipeline inspector listed as missing for
``agent_harness`` — a versioned task/response envelope, a configured health
endpoint, and an evidence writeback receipt — are the three things in this file.

The boundary itself lives in ``tradesync_core.agent_harness`` so it can be
tested without a model. What is here is the transport: probe a runtime, send a
task, and route the answer to quarantine. Nothing here can promote a harness
answer to evidence, because there is no code path from this module to the
feature catalog.

Off by default. ``AGENT_HARNESS_URL`` is unset unless the operator sets it, and
every surface answers "not configured" rather than pretending a model is absent
because it broke.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from tradesync_core.agent_harness import (
    HarnessError,
    RESPONSE_SCHEMA_VERSION,
    build_task,
    to_quarantine_submission,
    validate_response,
)

AGENT_HARNESS_URL = os.getenv("AGENT_HARNESS_URL", "").strip()
AGENT_HARNESS_MODEL = os.getenv("AGENT_HARNESS_MODEL", "llama3.1:8b").strip()
# Two dialects. "ollama" is the original local runtime (/api/tags, /api/generate).
# "openai" is the OpenAI-compatible surface the Hermes gateway's API server
# exposes (/v1/models, /v1/chat/completions, Bearer API_SERVER_KEY). The key is
# read once here and sent only in the Authorization header; never logged.
AGENT_HARNESS_API = os.getenv("AGENT_HARNESS_API", "ollama").strip().lower()
AGENT_HARNESS_KEY = os.getenv("AGENT_HARNESS_KEY", "").strip()


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {AGENT_HARNESS_KEY}"} if AGENT_HARNESS_KEY else {}
# Bounded so a hung runtime cannot hold a request open. Generous, because a
# cold local model loads several gigabytes into memory before it answers the
# first token, and that is a one-off cost rather than a fault.
AGENT_HARNESS_TIMEOUT_S = float(os.getenv("AGENT_HARNESS_TIMEOUT_S", "300"))
AGENT_HARNESS_PROBE_TIMEOUT_S = float(os.getenv("AGENT_HARNESS_PROBE_TIMEOUT_S", "3"))


def configured() -> bool:
    return bool(AGENT_HARNESS_URL)


async def probe() -> dict[str, Any]:
    """Is a harness runtime reachable, and what does it offer?

    Answers "not_configured" and "offline" as ordinary states. TradeSync is
    required to work with every optional connector disabled, so neither is an
    error — and reporting a stopped runtime as broken would repeat the
    healthcheck mistake this project already made once.
    """
    if not configured():
        return {
            "status": "not_configured",
            "url": None,
            "models": [],
            "detail": "AGENT_HARNESS_URL is unset; harnesses are optional",
        }

    try:
        async with httpx.AsyncClient(timeout=AGENT_HARNESS_PROBE_TIMEOUT_S) as client:
            if AGENT_HARNESS_API == "openai":
                response = await client.get(f"{AGENT_HARNESS_URL}/v1/models", headers=_headers())
            else:
                response = await client.get(f"{AGENT_HARNESS_URL}/api/tags")
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        return {
            "status": "offline",
            "url": AGENT_HARNESS_URL,
            "models": [],
            "detail": f"{type(exc).__name__}: {exc}",
        }

    if AGENT_HARNESS_API == "openai":
        models = [m.get("id") for m in payload.get("data", []) if isinstance(m, dict) and m.get("id")]
    else:
        models = [m.get("name") for m in payload.get("models", []) if m.get("name")]
    return {
        "status": "live",
        "url": AGENT_HARNESS_URL,
        "models": models,
        "configured_model": AGENT_HARNESS_MODEL,
        "model_present": AGENT_HARNESS_MODEL in models,
        # Stated on the probe so a reader of the pipeline inspector sees the
        # limit next to the status, not only in documentation.
        "authority": "advisory_only",
    }


async def ask(intent: str, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Send one task and return the accepted, boundary-checked answer.

    Raises ``HarnessError`` when the runtime says something it is not allowed to
    say. That is not a transport failure and must not be reported as one: a
    model claiming approval authority is a finding.
    """
    if not configured():
        raise HarnessError("not_configured", "AGENT_HARNESS_URL is unset")

    task = build_task(intent, prompt, context=context)

    started = time.monotonic()
    async with httpx.AsyncClient(timeout=AGENT_HARNESS_TIMEOUT_S) as client:
        if AGENT_HARNESS_API == "openai":
            response = await client.post(
                f"{AGENT_HARNESS_URL}/v1/chat/completions",
                headers=_headers(),
                json={
                    "model": AGENT_HARNESS_MODEL,
                    "messages": [{"role": "user", "content": _render(task)}],
                    "stream": False,
                },
            )
        else:
            response = await client.post(
                f"{AGENT_HARNESS_URL}/api/generate",
                json={"model": AGENT_HARNESS_MODEL, "prompt": _render(task), "stream": False},
            )
        response.raise_for_status()
        body = response.json()
    elapsed_ms = int((time.monotonic() - started) * 1000)

    # The runtime's own reply shape is not our envelope. It is wrapped into one
    # here so that validate_response checks a single known contract rather than
    # every runtime's dialect.
    if AGENT_HARNESS_API == "openai":
        choices = body.get("choices") or [{}]
        content = ((choices[0].get("message") or {}).get("content")) or ""
        runtime = "hermes-openai"
    else:
        content, runtime = body.get("response", ""), "ollama"
    envelope = {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "task_digest": task["task_digest"],
        "content": content,
        "model": body.get("model", AGENT_HARNESS_MODEL),
        "runtime": runtime,
        "elapsed_ms": elapsed_ms,
    }
    accepted = validate_response(envelope, task)
    return {"task": task, "accepted": accepted}


def _render(task: dict[str, Any]) -> str:
    """Turn a task envelope into the prompt text a runtime receives.

    The boundary is restated to the model. That is not the enforcement — the
    enforcement is ``validate_response`` refusing whatever comes back — but a
    model told plainly that it cannot approve is less likely to try, and the
    instruction is recorded in the task envelope either way.
    """
    lines = [
        "You are an advisory assistant for a paper-trading research system.",
        "You may explain, compare, summarise, draft and critique.",
        "You may NOT score, approve, gate, or instruct execution.",
        "Do not emit fields named approved, score, direction, side, signal or order.",
        "Answer in prose.",
        "",
        f"Task ({task['intent']}): {task['prompt']}",
    ]
    if task.get("context"):
        lines += ["", "Context recorded by the system:", str(task["context"])]
    return "\n".join(lines)


def quarantine_submission(result: dict[str, Any]) -> dict[str, Any]:
    """The quarantine submission for an accepted answer."""
    return to_quarantine_submission(result["accepted"], result["task"])
