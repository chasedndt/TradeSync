"""The Hermes link: a continuous heartbeat on the gateway, not a one-off probe.

The pipeline used to call Hermes's authenticated ``/v1/models`` with a three
second timeout on every read. When Hermes was busy running a job the call
took longer and the dashboard said offline while the gateway was up. This
module keeps the link warm instead:

- every ``HEARTBEAT_S`` seconds, ``GET /health`` (unauthenticated, cheap) with
  a generous timeout; latency, version and the time of the last answer are
  kept;
- every ``MODELS_EVERY_S`` seconds, ``GET /v1/models`` with the Bearer key, so
  the models list and the key's validity are known without paying for it on
  every page load;
- the gateway's own state file (platform states: API server, Discord), posted
  by the host bridge, is read from ``hermes_gateway_state``.

``status()`` answers instantly from that memory. Live means an answer within
``LIVE_WITHIN_S``; degraded means reachable but the key or a platform is
failing; offline means no answer for longer than that.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from app import agent_connector

HEARTBEAT_S = float(os.getenv("HERMES_HEARTBEAT_S", "15"))
MODELS_EVERY_S = float(os.getenv("HERMES_MODELS_EVERY_S", "60"))
HEALTH_TIMEOUT_S = float(os.getenv("HERMES_HEALTH_TIMEOUT_S", "8"))
MODELS_TIMEOUT_S = float(os.getenv("HERMES_MODELS_TIMEOUT_S", "20"))
LIVE_WITHIN_S = float(os.getenv("HERMES_LIVE_WITHIN_S", "60"))
HISTORY = 40

_state: dict[str, Any] = {
    "started_at": None, "last_check_at": None, "last_seen_at": None, "last_latency_ms": None,
    "version": None, "platform": None, "consecutive_failures": 0, "last_error": None,
    "models": [], "models_checked_at": None, "models_ok": None, "models_error": None,
    "checks": deque(maxlen=HISTORY),
}


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


async def _check_health(client: httpx.AsyncClient) -> None:
    started = time.monotonic()
    now = time.time()
    _state["last_check_at"] = now
    try:
        r = await client.get(f"{agent_connector.AGENT_HARNESS_URL}/health", timeout=HEALTH_TIMEOUT_S)
        r.raise_for_status()
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        latency = int((time.monotonic() - started) * 1000)
        _state.update(last_seen_at=now, last_latency_ms=latency, version=body.get("version"),
                      platform=body.get("platform"), consecutive_failures=0, last_error=None)
        _state["checks"].append({"at": _iso(now), "ok": True, "latency_ms": latency})
    except (httpx.HTTPError, ValueError) as exc:
        _state["consecutive_failures"] += 1
        _state["last_error"] = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        _state["checks"].append({"at": _iso(now), "ok": False, "error": _state["last_error"][:120]})


async def _check_models(client: httpx.AsyncClient) -> None:
    now = time.time()
    _state["models_checked_at"] = now
    try:
        r = await client.get(f"{agent_connector.AGENT_HARNESS_URL}/v1/models", headers=agent_connector._headers(), timeout=MODELS_TIMEOUT_S)
        r.raise_for_status()
        _state["models"] = [m.get("id") for m in r.json().get("data", []) if isinstance(m, dict) and m.get("id")]
        _state.update(models_ok=True, models_error=None)
    except (httpx.HTTPError, ValueError) as exc:
        _state.update(models_ok=False, models_error=f"{type(exc).__name__}: {exc}"[:200])


async def run_forever() -> None:
    if not agent_connector.configured():
        return
    _state["started_at"] = time.time()
    last_models = 0.0
    async with httpx.AsyncClient(trust_env=False) as client:
        while True:
            await _check_health(client)
            if time.time() - last_models >= MODELS_EVERY_S:
                await _check_models(client)
                last_models = time.time()
            await asyncio.sleep(HEARTBEAT_S)


async def gateway_state(pool) -> dict[str, Any] | None:
    """The gateway's own state file, as the host bridge last posted it."""
    if not pool:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT payload, source_updated_at, snapshot_at FROM hermes_gateway_state WHERE id = 1")
    except Exception:
        return None
    if not row:
        return None
    payload = row["payload"] if not isinstance(row["payload"], str) else json.loads(row["payload"])
    return {"payload": payload, "source_updated_at": row["source_updated_at"].isoformat() if row["source_updated_at"] else None,
            "snapshot_at": row["snapshot_at"].isoformat()}


def status_now() -> dict[str, Any]:
    """The link as of the last heartbeat. Instant; never makes a request."""
    url = agent_connector.AGENT_HARNESS_URL
    parsed = urlparse(url) if url else None
    now = time.time()
    seen = _state["last_seen_at"]
    since = round(now - seen, 1) if seen else None
    if not agent_connector.configured():
        state = "not_configured"
    elif seen is None:
        state = "checking" if _state["consecutive_failures"] == 0 else "offline"
    elif since is not None and since <= LIVE_WITHIN_S:
        state = "degraded" if _state["models_ok"] is False else "live"
    else:
        state = "offline"
    checks = list(_state["checks"])
    ok = [c for c in checks if c.get("ok")]
    return {
        "status": state,
        "name": "Hermes gateway",
        "url": url or None,
        "host": parsed.hostname if parsed else None,
        "port": parsed.port if parsed else None,
        "api": agent_connector.AGENT_HARNESS_API,
        "version": _state["version"],
        "platform": _state["platform"],
        "last_seen_at": _iso(seen),
        "seconds_since_seen": since,
        "last_check_at": _iso(_state["last_check_at"]),
        "latency_ms": _state["last_latency_ms"],
        "consecutive_failures": _state["consecutive_failures"],
        "last_error": _state["last_error"],
        "models": _state["models"],
        "models_ok": _state["models_ok"],
        "models_error": _state["models_error"],
        "models_checked_at": _iso(_state["models_checked_at"]),
        "heartbeat_s": HEARTBEAT_S,
        "availability_recent": round(len(ok) / len(checks), 3) if checks else None,
        "checks": checks[-12:],
        "watching_since": _iso(_state["started_at"]),
    }
