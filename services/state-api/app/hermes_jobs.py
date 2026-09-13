"""Hermes jobs through the gateway's own jobs API, on its port.

The Hermes gateway serves a jobs API beside its chat API, behind the same
Bearer key: ``GET /api/jobs``, ``GET`` and ``PATCH /api/jobs/{id}`` (name,
schedule, prompt, deliver, skills, repeat, enabled), and ``POST
/api/jobs/{id}/pause``, ``/resume`` and ``/run``. Market Command uses it for
every change it allows: the gateway applies the change under its own lock and
re-anchors the schedule itself, which is safer than rewriting ``jobs.json``
from outside. The host bridge's file edit stays for what the API does not
expose (the working directory) and as the fallback when the gateway is
unreachable.

This module is the transport only. Validation of what an operator may ask for,
and the record of every action, live in ``app.fleet``.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app import agent_connector

JOB_ID_RE = re.compile(r"^[a-f0-9]{12}$")
API_TIMEOUT_S = 20.0


class HermesJobsError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def available() -> bool:
    """The gateway is configured and speaks the OpenAI-compatible surface that carries the jobs API."""
    return agent_connector.configured() and agent_connector.AGENT_HARNESS_API == "openai"


async def _call(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    if not available():
        raise HermesJobsError(503, "Hermes gateway is not configured")
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT_S) as client:
            response = await client.request(method, f"{agent_connector.AGENT_HARNESS_URL}{path}",
                                            headers=agent_connector._headers(), json=body)
    except httpx.HTTPError as exc:
        raise HermesJobsError(502, f"gateway unreachable ({type(exc).__name__})") from None
    if response.status_code >= 400:
        try:
            detail = str(response.json().get("error") or response.text)
        except ValueError:
            detail = response.text
        raise HermesJobsError(response.status_code, detail[:300])
    return response.json()


def _checked(job_id: str) -> str:
    if not JOB_ID_RE.fullmatch(job_id):
        raise HermesJobsError(400, "job ids are 12 lowercase hex characters")
    return job_id


async def list_jobs() -> list[dict[str, Any]]:
    return list((await _call("GET", "/api/jobs?include_disabled=true")).get("jobs") or [])


async def get_job(job_id: str) -> dict[str, Any]:
    return (await _call("GET", f"/api/jobs/{_checked(job_id)}"))["job"]


async def patch_job(job_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    return (await _call("PATCH", f"/api/jobs/{_checked(job_id)}", fields))["job"]


async def pause_job(job_id: str) -> dict[str, Any]:
    return (await _call("POST", f"/api/jobs/{_checked(job_id)}/pause"))["job"]


async def resume_job(job_id: str) -> dict[str, Any]:
    return (await _call("POST", f"/api/jobs/{_checked(job_id)}/resume"))["job"]


async def run_job(job_id: str) -> dict[str, Any]:
    return (await _call("POST", f"/api/jobs/{_checked(job_id)}/run"))["job"]


def schedule_display(job: dict[str, Any]) -> str:
    schedule = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
    return str(job.get("schedule_display") or schedule.get("display") or schedule.get("expr") or "")
