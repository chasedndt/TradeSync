"""Bridge the Hermes fleet's job outputs into TradeSync quarantine.

Runs on the Windows host (Task Scheduler, every couple of minutes), because the
fleet lives in WSL and Docker Desktop cannot bind-mount the distro here. It
scans ``cron/output`` over the ``\\\\wsl.localhost`` share, posts every output
file newer than its cursor to ``state-api`` as source ``chaseos`` (see
``tradesync_core.hermes_output``), and advances the cursor only past files
that were stored.

First run establishes the cursor at "now" and reads forward: quarantine's
staleness bound would refuse older files anyway, and a backfill is a separate,
deliberate import.

Read-only against Hermes. Never writes into the WSL tree, never posts to
Discord, never touches the catalog.

Usage (from the repo root, with the project venv):
    python tools/hermes_output_bridge.py [--once] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "libs" / "tradesync_core"))

import httpx  # noqa: E402

from tradesync_core.hermes_output import (  # noqa: E402
    OutputFile,
    is_silent,
    parse_filename,
    parse_markdown_run,
    to_submission,
)

HERMES_HOME = Path(os.getenv("HERMES_HOME_WINDOWS", r"\\wsl.localhost\Ubuntu\home\chaseos\runtimes\hermes-home"))
OUTPUT_DIR = HERMES_HOME / "cron" / "output"
JOBS_FILE = HERMES_HOME / "cron" / "jobs.json"
CHANNELS_FILE = REPO / "config" / "chaseos" / "discord-channels.json"
STATE_FILE = Path(os.getenv("HERMES_BRIDGE_STATE", r"E:\Projects\TradeSync\dashboard-runtime\hermes-bridge-state.json"))
STATE_API = os.getenv("STATE_API_URL", "http://localhost:8000").rstrip("/")
MAX_PER_PASS = 200


def load_jobs() -> dict[str, dict]:
    try:
        data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        return {str(j.get("id")): j for j in data.get("jobs", []) if isinstance(j, dict)}
    except (OSError, ValueError) as exc:
        print(f"[HermesBridge] jobs.json unreadable ({type(exc).__name__}); labels fall back to job ids")
        return {}


def load_channels() -> dict[str, str]:
    try:
        data = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
        return {c["id"]: c["label"] for c in data.get("channels", [])}
    except (OSError, ValueError, KeyError):
        return {}


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def new_files(cursor_mtime_ns: int) -> list[tuple[Path, int, OutputFile]]:
    """Output files modified after the cursor, oldest first.

    Two forms exist side by side: a flat ``<job_id>_<stamp>.txt`` capture and,
    for some jobs, a dated ``<job_id>/<stamp>.md`` per run. Where a job has
    the per-job directory the markdown is the richer artifact and the flat
    capture for that job is skipped, so one run is not held twice.
    """
    found: list[tuple[Path, int, OutputFile]] = []
    jobs_with_dirs: set[str] = set()
    for entry in os.scandir(OUTPUT_DIR):
        if entry.is_dir():
            for run in os.scandir(entry.path):
                output = parse_markdown_run(entry.name, run.name) if run.is_file() else None
                if output is None:
                    continue
                jobs_with_dirs.add(entry.name)
                mtime_ns = run.stat().st_mtime_ns
                if mtime_ns > cursor_mtime_ns:
                    found.append((Path(run.path), mtime_ns, output))
    for entry in os.scandir(OUTPUT_DIR):
        output = parse_filename(entry.name) if entry.is_file() else None
        if output is None or output.job_id in jobs_with_dirs:
            continue
        mtime_ns = entry.stat().st_mtime_ns
        if mtime_ns > cursor_mtime_ns:
            found.append((Path(entry.path), mtime_ns, output))
    found.sort(key=lambda t: t[1])
    return found[:MAX_PER_PASS]


def run_pass(dry_run: bool = False) -> dict[str, int]:
    if not OUTPUT_DIR.is_dir():
        print(f"[HermesBridge] output dir not reachable: {OUTPUT_DIR}")
        return {"read": 0, "accepted": 0, "refused": 0}
    state = load_state()
    cursor = int(state.get("cursor_mtime_ns", 0))
    if not cursor:
        now_ns = time.time_ns()
        save_state({"cursor_mtime_ns": now_ns, "established_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        print("[HermesBridge] cursor established at now; reading forward from here")
        return {"read": 0, "accepted": 0, "refused": 0}

    jobs, channels = load_jobs(), load_channels()
    counts = {"read": 0, "accepted": 0, "refused": 0, "silent": 0}
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        for path, mtime_ns, output in new_files(cursor):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                print(f"[HermesBridge] cannot read {path.name}: {type(exc).__name__}; stopping this pass")
                break
            counts["read"] += 1
            if is_silent(content):
                # The fleet's own "nothing happened" stub; not evidence of anything.
                counts["silent"] += 1
                state["cursor_mtime_ns"] = mtime_ns
                if not dry_run:
                    save_state(state)
                continue
            submission = to_submission(output, content, jobs.get(output.job_id), channels, observed_at_ms=mtime_ns // 1_000_000)
            if dry_run:
                print(f"[HermesBridge] would submit {path.name} as '{submission['payload']['agent']}'")
                continue
            try:
                response = client.post(f"{STATE_API}/state/quarantine", json=submission)
                response.raise_for_status()
                accepted = bool(response.json().get("accepted"))
            except (httpx.HTTPError, ValueError) as exc:
                print(f"[HermesBridge] state-api refused the connection ({type(exc).__name__}); cursor kept at {path.name}")
                break
            counts["accepted" if accepted else "refused"] += 1
            state["cursor_mtime_ns"] = mtime_ns
            save_state(state)
    if counts["read"]:
        print(
            f"[HermesBridge] pass: read {counts['read']}, accepted {counts['accepted']}, "
            f"refused {counts['refused']}, silent skipped {counts['silent']}"
        )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--once", action="store_true", help="one pass (the scheduled-task mode)")
    parser.add_argument("--dry-run", action="store_true", help="read and label, post nothing, advance nothing")
    parser.add_argument("--interval", type=int, default=120, help="seconds between passes when not --once")
    args = parser.parse_args()
    if args.once or args.dry_run:
        run_pass(dry_run=args.dry_run)
        return 0
    while True:
        run_pass()
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
