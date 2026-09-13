"""Re-point the Hermes fleet from the retired vault to the canonical one.

The live fleet still names ``chaseos_obsidian`` (a stub holding only logs)
in 40 job records, 120 scripts, its terminal cwd, both Windows launchers and
the Discord bindings file. The canonical vault is ``chaseos_chaseintech``
(operator correction of 2026-09-08, reconfirmed 2026-09-11 and 2026-09-13).

What this does, on the Windows host over the WSL share, with a full backup
first:

1. ``cron/jobs.json``: every ``workdir`` and every ``prompt`` naming the old
   vault, both spellings. Schedules are not touched (a schedule edit makes
   Hermes re-anchor ``next_run_at``; a workdir edit does not). Written
   atomically; Hermes re-reads the file on its next tick.
2. ``scripts/`` (recursive, text files only): both spellings replaced.
3. ``config.yaml``: the ``terminal.cwd`` line.
4. ``C:\\Users\\chaseos\\.hermes\\gateway.cmd`` and ``hermes-daemon-loop.cmd``:
   the vault root, the WSL workdir, the daemon log, and the Windows
   interpreter, which in the canonical vault is ``.venv-win314`` (the
   ``.venv`` there is a POSIX venv with no ``Scripts``).
5. ``chaseos_chaseintech/.chaseos/discord_instance_bindings.yaml``: ``repo_root``.

Nothing is deleted from the old vault. Run with ``--dry-run`` to see the
counts without writing.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

OLD_POSIX = "/mnt/c/Users/chaseos/Documents/chaseos_obsidian"
NEW_POSIX = "/mnt/c/Users/chaseos/Documents/chaseos_chaseintech"
OLD_WIN = r"C:\Users\chaseos\Documents\chaseos_obsidian"
NEW_WIN = r"C:\Users\chaseos\Documents\chaseos_chaseintech"
OLD_WIN_ESC = OLD_WIN.replace("\\", "\\\\")
NEW_WIN_ESC = NEW_WIN.replace("\\", "\\\\")
OLD_WIN_FWD = OLD_WIN.replace("\\", "/")
NEW_WIN_FWD = NEW_WIN.replace("\\", "/")
PAIRS = ((OLD_POSIX, NEW_POSIX), (OLD_WIN_ESC, NEW_WIN_ESC), (OLD_WIN, NEW_WIN), (OLD_WIN_FWD, NEW_WIN_FWD))

HERMES_HOME = Path(os.getenv("HERMES_HOME_WINDOWS", r"\\wsl.localhost\Ubuntu\home\chaseos\runtimes\hermes-home"))
LAUNCHERS = [Path(r"C:\Users\chaseos\.hermes\gateway.cmd"), Path(r"C:\Users\chaseos\.hermes\hermes-daemon-loop.cmd")]
BINDINGS = Path(r"C:\Users\chaseos\Documents\chaseos_chaseintech\.chaseos\discord_instance_bindings.yaml")
BACKUP_ROOT = Path(os.getenv("REPOINT_BACKUP_ROOT", r"E:\Projects\TradeSync\dashboard-runtime\backups"))
TEXT_SUFFIXES = {".py", ".sh", ".json", ".yaml", ".yml", ".md", ".txt", ".cmd", ".ps1", ".toml", ".cfg", ".ini"}


def swap(text: str) -> tuple[str, int]:
    count = 0
    for old, new in PAIRS:
        count += text.count(old)
        text = text.replace(old, new)
    return text, count


def backup(paths: list[Path], stamp: str) -> Path:
    root = BACKUP_ROOT / f"repoint-{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    for p in paths:
        if p.is_dir():
            shutil.make_archive(str(root / p.name), "zip", p)
        elif p.exists():
            shutil.copy(p, root / p.name)
    return root


def repoint_jobs(dry: bool) -> dict[str, int]:
    path = HERMES_HOME / "cron" / "jobs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    counts = {"workdir": 0, "prompt": 0}
    for job in data.get("jobs", []):
        wd = job.get("workdir")
        if isinstance(wd, str) and OLD_POSIX in wd:
            job["workdir"] = wd.replace(OLD_POSIX, NEW_POSIX)
            counts["workdir"] += 1
        prompt = job.get("prompt")
        if isinstance(prompt, str):
            new, n = swap(prompt)
            if n:
                job["prompt"] = new
                counts["prompt"] += 1
    if not dry and (counts["workdir"] or counts["prompt"]):
        tmp = path.with_name(f".jobs_repoint_{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    return counts


def repoint_tree(root: Path, dry: bool) -> dict[str, int]:
    counts = {"files": 0, "lines": 0}
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES or any(part in ("venv", "node_modules", "__pycache__") for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new, n = swap(text)
        if n:
            counts["files"] += 1
            counts["lines"] += n
            if not dry:
                p.write_text(new, encoding="utf-8")
    return counts


def repoint_file(path: Path, dry: bool, extra: tuple[tuple[str, str], ...] = ()) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    new, n = swap(text)
    for old, rep in extra:
        n += new.count(old)
        new = new.replace(old, rep)
    if n and not dry:
        path.write_text(new, encoding="utf-8")
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    dry = args.dry_run
    stamp = time.strftime("%Y%m%d_%H%M%S")
    if not dry:
        root = backup([HERMES_HOME / "cron" / "jobs.json", HERMES_HOME / "config.yaml", HERMES_HOME / "scripts", BINDINGS, *LAUNCHERS], stamp)
        print(f"[Repoint] backup at {root}")
    print("[Repoint] jobs.json:", repoint_jobs(dry))
    print("[Repoint] scripts:", repoint_tree(HERMES_HOME / "scripts", dry))
    print("[Repoint] config.yaml lines:", repoint_file(HERMES_HOME / "config.yaml", dry))
    # The canonical vault's Windows interpreter lives in .venv-win314; the plain
    # .venv there is a POSIX venv with no Scripts directory.
    venv_fix = ((NEW_WIN + r"\.venv\Scripts\python.exe", NEW_WIN + r"\.venv-win314\Scripts\python.exe"),)
    for launcher in LAUNCHERS:
        print(f"[Repoint] {launcher.name} lines:", repoint_file(launcher, dry, extra=venv_fix))
    print("[Repoint] bindings repo_root lines:", repoint_file(BINDINGS, dry))
    print("[Repoint] " + ("dry run; nothing written" if dry else "done; Hermes re-reads jobs.json on its next tick"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
