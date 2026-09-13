"""Bridge the Hermes fleet's registry, ledgers and directives between WSL and Market Command.

Runs on the Windows host (Task Scheduler, every few minutes), beside the
output bridge. Each pass:

1. Reads ``cron/jobs.json`` (registry), ``cron/executions.db`` (runs, copied
   before opening so the fleet's own writer is never contended) and
   ``cron/usage_audit.jsonl`` (tokens per model call) over the WSL share and
   posts a snapshot to ``POST /state/fleet/snapshot``.
2. Fetches pending directives from ``GET /state/fleet/directives?status=pending``
   and applies them to ``jobs.json``: a timestamped backup first, then an
   atomic write of the whole file. Each directive is reported back with what
   it replaced, so the panel can reverse it.

The registry is the fleet's; this script only edits the fields a directive
names (``schedule``/``schedule_display``, ``enabled``, ``workdir``) and never
a prompt, a script path or a credential. Hermes reloads the registry on its
own cadence (see the change record); nothing here restarts the gateway.

Usage: python tools/hermes_fleet_bridge.py [--once] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import sys

import httpx

# Under pythonw.exe (no console window) there is no stdout; log to a file instead.
if sys.stdout is None or sys.stderr is None:
    _log = Path(os.getenv("TRADESYNC_LOG_DIR", r"E:\Projects\TradeSync\dashboard-runtime\logs")) / "hermes_fleet_bridge.log"
    _log.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(_log, "a", encoding="utf-8", buffering=1)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "libs" / "tradesync_core"))

from tradesync_core.job_errors import redact  # noqa: E402

HERMES_HOME = Path(os.getenv("HERMES_HOME_WINDOWS", r"\\wsl.localhost\Ubuntu\home\chaseos\runtimes\hermes-home"))
CRON = HERMES_HOME / "cron"
STATE_API = os.getenv("STATE_API_URL", "http://localhost:8000").rstrip("/")
USAGE_TAIL_LINES = 2000
RUNS_LIMIT = 1500
DESCRIPTION_CHARS = 400


def _iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def describe(job: dict) -> str:
    """A short description: the prompt's first sentences, or the script it runs."""
    prompt = str(job.get("prompt") or "").strip()
    if prompt:
        return " ".join(prompt.split())[:DESCRIPTION_CHARS]
    script = job.get("script")
    return f"script job: {script}" if script else ""


def read_jobs() -> tuple[dict, list[dict]]:
    data = json.loads((CRON / "jobs.json").read_text(encoding="utf-8"))
    jobs = []
    for j in data.get("jobs", []):
        if not isinstance(j, dict) or not j.get("id"):
            continue
        schedule = j.get("schedule") if isinstance(j.get("schedule"), dict) else {}
        jobs.append({
            "job_id": str(j["id"]), "name": str(j.get("name") or j["id"]), "enabled": bool(j.get("enabled", True)),
            "schedule": schedule, "schedule_display": str(j.get("schedule_display") or schedule.get("display") or ""),
            "deliver": str(j.get("deliver") or "local"), "workdir": j.get("workdir"), "script": j.get("script"),
            "no_agent": bool(j.get("no_agent", False)), "model": j.get("model"), "description": describe(j),
            "last_run_at": _iso(j.get("last_run_at")), "last_status": j.get("last_status"),
            "next_run_at": _iso(j.get("next_run_at")), "state": j.get("state"),
            # A script's output can hold anything; token-, key- and webhook-shaped text is removed first.
            "last_error": redact(j.get("last_error")), "last_delivery_error": redact(j.get("last_delivery_error")),
        })
    return data, jobs


def read_runs() -> list[dict]:
    src = CRON / "executions.db"
    if not src.exists():
        return []
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "executions.db"
        shutil.copy(src, dst)
        c = sqlite3.connect(dst)
        rows = c.execute(
            "SELECT id, job_id, status, claimed_at, started_at, finished_at, error FROM executions ORDER BY claimed_at DESC LIMIT ?",
            (RUNS_LIMIT,),
        ).fetchall()
        c.close()
    out = []
    for rid, job_id, status, claimed, started, finished, error in rows:
        duration = None
        if started and finished:
            try:
                duration = int((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds() * 1000)
            except ValueError:
                duration = None
        out.append({"id": rid, "job_id": job_id, "status": status, "claimed_at": _iso(claimed), "started_at": _iso(started),
                    "finished_at": _iso(finished), "duration_ms": duration, "error": (error or None) and str(error)[:500]})
    return out


def read_usage() -> list[dict]:
    src = CRON / "usage_audit.jsonl"
    if not src.exists():
        return []
    lines = src.read_text(encoding="utf-8", errors="replace").splitlines()[-USAGE_TAIL_LINES:]
    out = []
    for line in lines:
        try:
            u = json.loads(line)
        except ValueError:
            continue
        if not u.get("fire_id") or not u.get("job_id") or not u.get("ts"):
            continue
        out.append({
            "fire_id": u["fire_id"], "job_id": u["job_id"], "ts": _iso(u["ts"]), "model": u.get("model"),
            "prompt_tokens": int(u.get("prompt_tokens") or 0), "completion_tokens": int(u.get("completion_tokens") or 0),
            "total_tokens": int(u.get("total_tokens") or 0), "duration_ms": u.get("duration_ms"),
            "deliver_target": u.get("deliver_target"), "response_silent": u.get("response_silent"), "error": u.get("error"),
        })
    return out


def read_gateway() -> dict | None:
    """Hermes's gateway_state.json: whether the API server and Discord platforms are up."""
    try:
        data = json.loads((HERMES_HOME / "gateway_state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    keep = ("kind", "gateway_state", "pid", "code_version", "code_sha", "active_agents", "platforms",
            "updated_at", "exit_reason", "restart_requested")
    return {k: data.get(k) for k in keep if k in data}


def apply_directive(data: dict, directive: dict) -> tuple[dict | None, str]:
    """Mutate the registry in memory. Returns (previous values, detail)."""
    job = next((j for j in data.get("jobs", []) if str(j.get("id")) == directive["job_id"]), None)
    if job is None:
        return None, "job not found in registry"
    kind, payload = directive["kind"], directive.get("payload") or {}
    if kind == "set_schedule":
        previous = {"schedule": job.get("schedule"), "schedule_display": job.get("schedule_display")}
        job["schedule"] = dict(payload["schedule"])
        job["schedule_display"] = payload["schedule"].get("display", "")
        return previous, f"schedule -> {job['schedule_display']}"
    if kind == "set_enabled":
        previous = {"enabled": job.get("enabled", True)}
        job["enabled"] = bool(payload["enabled"])
        return previous, f"enabled -> {job['enabled']}"
    if kind == "set_workdir":
        previous = {"workdir": job.get("workdir")}
        job["workdir"] = payload["workdir"]
        return previous, f"workdir -> {job['workdir']}"
    return None, f"unknown directive kind {kind}"


def write_registry(data: dict) -> Path:
    """Backup, then atomic replace. The fleet's own writer uses the same pattern."""
    target = CRON / "jobs.json"
    backup = CRON / f"jobs.json.bak-tradesync-{time.strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(target, backup)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = CRON / f".jobs_tradesync_{os.getpid()}.tmp"
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)
    return backup


def run_pass(dry_run: bool = False) -> None:
    data, jobs = read_jobs()
    snapshot = {"jobs": jobs, "runs": read_runs(), "usage": read_usage(), "gateway": read_gateway()}
    with httpx.Client(timeout=60.0, trust_env=False) as client:
        if dry_run:
            print(f"[FleetBridge] would post {len(jobs)} jobs, {len(snapshot['runs'])} runs, {len(snapshot['usage'])} usage rows")
        else:
            r = client.post(f"{STATE_API}/state/fleet/snapshot", json=snapshot)
            r.raise_for_status()
            print(f"[FleetBridge] snapshot: {r.json()}")
        pending = client.get(f"{STATE_API}/state/fleet/directives", params={"status": "pending"}).json().get("directives", [])
        if not pending:
            return
        applied = []
        for d in sorted(pending, key=lambda x: x["requested_at"]):
            previous, detail = apply_directive(data, d)
            applied.append((d["id"], "applied" if previous is not None else "failed", previous, detail))
        if dry_run:
            for a in applied:
                print(f"[FleetBridge] would apply {a[0]}: {a[3]}")
            return
        if any(a[1] == "applied" for a in applied):
            backup = write_registry(data)
            print(f"[FleetBridge] registry written; backup {backup.name}")
        for did, status, previous, detail in applied:
            client.post(f"{STATE_API}/state/fleet/directives/report",
                        json={"id": did, "status": status, "previous": previous, "detail": detail}).raise_for_status()
            print(f"[FleetBridge] {status} {did}: {detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()
    if args.once or args.dry_run:
        run_pass(dry_run=args.dry_run)
        return 0
    while True:
        try:
            run_pass()
        except Exception as exc:  # keep the loop alive; the next pass retries
            print(f"[FleetBridge] pass failed: {type(exc).__name__}: {exc}")
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
