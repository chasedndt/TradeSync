"""Targeted repairs to failing Hermes fleet scripts, applied over the WSL share with a backup.

Each fix is an exact text replacement in one fleet file: what it repairs, the
text it expects to find, and the text it puts there. A fix is skipped when its
replacement is already present (so the tool can run again) and refused when
the expected text is missing (the file changed; look before patching). Every
patched file is copied to a backup folder first and written in place, keeping
its line endings and permissions.

Run ``tools/restore_hermes_line_endings.py`` first: the expected texts use LF.

Usage (repo root, project venv):
    python tools/hermes_fleet_fixes.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from pathlib import Path

HERMES_HOME = Path(os.getenv("HERMES_HOME_WINDOWS", "//wsl.localhost/Ubuntu/home/chaseos/runtimes/hermes-home"))
BACKUP_ROOT = Path(os.getenv("FLEET_FIXES_BACKUP_ROOT", r"E:\Projects\TradeSync\dashboard-runtime\backups"))


@dataclass(frozen=True)
class Fix:
    job: str
    path: str
    why: str
    old: str
    new: str


FIXES: tuple[Fix, ...] = (
    Fix(
        job="9b8976a0804e StrikeZone Scheduled Market Edition",
        path="scripts/strikezone/publish/autonomous_publish_orchestrator.py",
        why="A Binance read timeout left the market model empty and the cycle crashed with KeyError: 'BTC'. "
            "Retry the build twice with a pause, and stop with the real cause instead of rendering an empty model.",
        old="""    model_error = None
    try:
        model = annotate_thesis_quality(build_fresh_market_model())
    except Exception as exc:
        model_error = repr(exc)
        model = {"schema": "strikezone_fresh_market_model_v2", "generated_at_utc": now_iso(), "source_freshness": {}, "assets": [], "derivatives": [], "macro_proxy_rows": [], "error": model_error}
    _write_json(STEP6E_DIR / "fresh_market_model.json", model)
""",
        new="""    model_error = None
    model = None
    for attempt in range(3):
        try:
            model = annotate_thesis_quality(build_fresh_market_model())
            model_error = None
            break
        except Exception as exc:
            model_error = repr(exc)
            if attempt < 2:
                time.sleep(30 * (attempt + 1))
    if model is None:
        model = {"schema": "strikezone_fresh_market_model_v2", "generated_at_utc": now_iso(), "source_freshness": {}, "assets": [], "derivatives": [], "macro_proxy_rows": [], "error": model_error}
    _write_json(STEP6E_DIR / "fresh_market_model.json", model)
    if not model.get("assets"):
        # Nothing to publish from: say why, rather than failing later on a missing asset.
        raise RuntimeError(f"fresh market model unavailable after 3 attempts: {model_error}")
""",
    ),
    Fix(
        job="c7b1fa0a2f3f StrikeZone approval publish watcher",
        path="scripts/strikezone_approval_publish_watchdog.py",
        why="The approval-plan probe was killed after 30 s (subprocess.TimeoutExpired). Allow 120 s and report a timeout plainly.",
        old="""def main() -> int:
    probe = subprocess.run(
        [sys.executable, str(PLAN_SCRIPT), "--detect-approval"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
""",
        new="""def main() -> int:
    try:
        probe = subprocess.run(
            [sys.executable, str(PLAN_SCRIPT), "--detect-approval"],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("APPROVAL_PROBE_TIMEOUT: the approval-plan probe ran longer than 120s; nothing was published; the next run retries")
        return 1
""",
    ),
    Fix(
        job="109d391ae292 ChaseOS daily compute analytics",
        path="scripts/chaseos_compute_analytics.py",
        why="The Discord fetch-back that verifies the daily post timed out after 30 s. Retry the read twice with a pause; "
            "the post itself is not retried (a timeout after sending could post twice), so it waits longer instead.",
        old="""    with urllib.request.urlopen(req, timeout=30) as response:
        created = json.loads(response.read())
    message_id = str(created["id"])
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        fetched = json.loads(response.read())
""",
        new="""    with urllib.request.urlopen(req, timeout=90) as response:
        created = json.loads(response.read())
    message_id = str(created["id"])
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
        headers=headers,
    )
    fetched: dict[str, Any] = {}
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                fetched = json.loads(response.read())
            break
        except (TimeoutError, socket.timeout, ConnectionError, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))
""",
    ),
    Fix(
        job="09490ac9c6d7 StrikeZone Hyperliquid paper-outcome resolver (and 83d45255c926 integrity watchdog)",
        path="scripts/strikezone/quant_eval/cron_paper_outcomes.sh",
        why="The funding archive only moved when outcomes resolved, so a quiet spell tripped funding_archive_stale. "
            "Sync funding before each resolver run; a sync failure does not stop the resolver, and the watchdog still reports staleness.",
        old="""exec /home/chaseos/runtimes/hermes-home/hermes-agent/venv/bin/python -m strikezone.quant_eval.cron_runner outcomes
""",
        new="""# Keep the funding archive under the integrity watchdog's 3h freshness bound between daily snapshots.
/home/chaseos/runtimes/hermes-home/hermes-agent/venv/bin/python -m strikezone.quant_eval.cron_runner funding-sync >/dev/null 2>&1 || true
exec /home/chaseos/runtimes/hermes-home/hermes-agent/venv/bin/python -m strikezone.quant_eval.cron_runner outcomes
""",
    ),
)


def apply(fix: Fix, dry_run: bool, backup_dir: Path) -> str:
    path = HERMES_HOME / fix.path
    data = path.read_bytes()
    text = data.decode("utf-8")
    if fix.new in text:
        return "already applied"
    if "\r\n" in text:
        return "refused: file has CRLF line endings; run restore_hermes_line_endings.py first"
    count = text.count(fix.old)
    if count != 1:
        return f"refused: expected text found {count} times"
    if dry_run:
        return "would apply"
    copy = backup_dir / fix.path
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes(data)
    path.write_bytes(text.replace(fix.old, fix.new).encode("utf-8"))
    return "applied"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    backup_dir = BACKUP_ROOT / f"fleet-fixes-{time.strftime('%Y%m%d_%H%M%S')}"
    failed = 0
    for fix in FIXES:
        try:
            outcome = apply(fix, args.dry_run, backup_dir)
        except OSError as exc:
            outcome = f"refused: {type(exc).__name__}"
        failed += outcome.startswith("refused")
        print(f"[FleetFixes] {fix.job}: {outcome}\n    {fix.path}\n    {fix.why}")
    if not args.dry_run and backup_dir.exists():
        print(f"[FleetFixes] backup {backup_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
