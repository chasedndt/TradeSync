"""Which directives exist, which channel may apply each, and the schedules the Fleet panel offers."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from app.fleet_models import DirectiveRequest

DIRECTIVE_KINDS = ("set_schedule", "set_enabled", "set_workdir", "set_deliver", "pause", "resume", "run_now")
# Applied at once through the Hermes gateway's jobs API on its port.
GATEWAY_KINDS = frozenset({"set_schedule", "set_enabled", "set_deliver", "pause", "resume", "run_now"})
# The host bridge can apply these by editing jobs.json: the working directory
# (which the API does not expose), and schedule or enabled when the gateway is down.
BRIDGE_KINDS = frozenset({"set_schedule", "set_enabled", "set_workdir"})
DELIVER_RE = re.compile(r"^(local|discord:[0-9][0-9:]{5,63})$")
# Schedules the panel offers. Anything else is a hand edit on the fleet host.
SCHEDULE_PRESETS = {
    "15m": {"kind": "interval", "minutes": 15, "display": "every 15m"},
    "30m": {"kind": "interval", "minutes": 30, "display": "every 30m"},
    "1h": {"kind": "interval", "minutes": 60, "display": "every 60m"},
    "3h": {"kind": "interval", "minutes": 180, "display": "every 180m"},
    "6h": {"kind": "interval", "minutes": 360, "display": "every 360m"},
    "daily-08": {"kind": "cron", "expr": "0 8 * * *", "display": "0 8 * * *"},
    "weekly-mon-08": {"kind": "cron", "expr": "0 8 * * 1", "display": "0 8 * * 1"},
}


def directive_payload(req: "DirectiveRequest") -> dict[str, Any]:
    if req.kind not in DIRECTIVE_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {', '.join(DIRECTIVE_KINDS)}")
    if req.kind == "set_schedule":
        if req.preset not in SCHEDULE_PRESETS:
            raise HTTPException(status_code=400, detail=f"preset must be one of {', '.join(SCHEDULE_PRESETS)}")
        return {"schedule": SCHEDULE_PRESETS[req.preset], "preset": req.preset}
    if req.kind == "set_enabled":
        if req.enabled is None:
            raise HTTPException(status_code=400, detail="enabled is required")
        return {"enabled": req.enabled}
    if req.kind == "set_workdir":
        if not req.workdir:
            raise HTTPException(status_code=400, detail="workdir is required")
        return {"workdir": req.workdir}
    if req.kind == "set_deliver":
        if not req.deliver or not DELIVER_RE.fullmatch(req.deliver):
            raise HTTPException(status_code=400, detail="deliver must be 'local' or 'discord:<channel id>'")
        return {"deliver": req.deliver}
    return {}
