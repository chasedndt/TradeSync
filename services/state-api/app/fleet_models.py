"""Payloads the host bridge posts (jobs, runs, token usage, gateway state) and the directives the Cockpit sends."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobSnapshot(BaseModel):
    job_id: str
    name: str
    enabled: bool = True
    schedule: dict[str, Any] = Field(default_factory=dict)
    schedule_display: str = ""
    deliver: str = "local"
    workdir: str | None = None
    script: str | None = None
    no_agent: bool = False
    model: str | None = None
    description: str = ""
    last_run_at: datetime | None = None
    last_status: str | None = None
    next_run_at: datetime | None = None
    state: str | None = None
    # Redacted by the bridge (tradesync_core.job_errors) before it leaves the host.
    last_error: str | None = None
    last_delivery_error: str | None = None


class RunSnapshot(BaseModel):
    id: str
    job_id: str
    status: str
    claimed_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None


class UsageSnapshot(BaseModel):
    fire_id: str
    job_id: str
    ts: datetime
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int | None = None
    deliver_target: str | None = None
    response_silent: bool | None = None
    error: str | None = None


class FleetSnapshot(BaseModel):
    jobs: list[JobSnapshot] = Field(default_factory=list)
    runs: list[RunSnapshot] = Field(default_factory=list)
    usage: list[UsageSnapshot] = Field(default_factory=list)
    # Hermes's own gateway_state.json (platform states, pid, version), as read by the bridge.
    gateway: dict[str, Any] | None = None


class DirectiveRequest(BaseModel):
    job_id: str
    kind: str
    preset: str | None = None  # for set_schedule
    enabled: bool | None = None  # for set_enabled
    workdir: str | None = None  # for set_workdir
    deliver: str | None = None  # for set_deliver: "local" or "discord:<channel id>"
    requested_by: str = "operator"


class DirectiveReport(BaseModel):
    id: str
    status: str
    previous: dict[str, Any] | None = None
    detail: str = ""
