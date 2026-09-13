"""Put LF line endings back where the Hermes fleet needs them.

Two sources of CRLF broke fleet jobs:

1. ``tools/repoint_hermes_vault.py`` (2026-09-13) rewrote every file naming the
   retired vault with ``Path.write_text``, which on Windows turns each ``\\n``
   into ``\\r\\n``: 128 scripts, ``config.yaml`` and the Discord bindings file
   went from LF to CRLF.
2. Scripts edited from Windows long before that already had CRLF; the fleet
   inspector has listed some of those jobs as failing since 2026-07-27.

Bash cannot run a CRLF script (``set: pipefail\\r: invalid option name``), and a
shebang ending in ``\\r`` names an interpreter that does not exist
(``python3\\r``). Python itself reads either ending.

So this does two things, and changes nothing but ``\\r\\n`` to ``\\n``:

- **Restore**: every file the re-point wrote (its original in the re-point
  backup names the retired vault) whose original was LF goes back to LF,
  keeping the path edits. Files that were CRLF before are left for rule two.
- **Normalise**: every shell or Python script under ``scripts/`` (``.sh``,
  ``.bash``, ``.py``, or any file starting with a shebang) goes to LF. Windows
  launchers (``.cmd``, ``.ps1``), backups and data files are not scripts and
  are left alone.

Each rewritten file is copied to a new backup folder first and written in
place, so its permissions (the executable bit a shebang needs) survive.

Usage (repo root, project venv):
    python tools/restore_hermes_line_endings.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import time
import zipfile
from pathlib import Path

HERMES_HOME = Path(os.getenv("HERMES_HOME_WINDOWS", "//wsl.localhost/Ubuntu/home/chaseos/runtimes/hermes-home"))
REPOINT_BACKUP = Path(os.getenv("REPOINT_BACKUP", r"E:\Projects\TradeSync\dashboard-runtime\backups\repoint-20260913_043749"))
BACKUP_ROOT = Path(os.getenv("LINE_ENDINGS_BACKUP_ROOT", r"E:\Projects\TradeSync\dashboard-runtime\backups"))
BINDINGS = Path(r"C:\Users\chaseos\Documents\chaseos_chaseintech\.chaseos\discord_instance_bindings.yaml")
RETIRED_VAULT = b"chaseos_obsidian"
SCRIPT_SUFFIXES = {".sh", ".bash", ".py"}
SKIP_PARTS = {"venv", ".venv", "node_modules", "__pycache__", ".git"}


def restored(live: bytes, original: bytes) -> bytes | None:
    """LF again when the re-point wrote the file and its original was LF; else None."""
    if RETIRED_VAULT not in original or b"\r" in original or b"\r\n" not in live:
        return None
    return live.replace(b"\r\n", b"\n")


def normalised(live: bytes, name: str) -> bytes | None:
    """LF for a shell or Python script (by suffix or shebang) that has CRLF; else None."""
    is_script = Path(name).suffix.lower() in SCRIPT_SUFFIXES or live.startswith(b"#!")
    if not is_script or b"\r\n" not in live:
        return None
    return live.replace(b"\r\n", b"\n")


def repoint_originals() -> dict[str, tuple[Path, bytes]]:
    """label -> (live path, original bytes) for files the re-point wrote."""
    out: dict[str, tuple[Path, bytes]] = {}
    with zipfile.ZipFile(REPOINT_BACKUP / "scripts.zip") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            data = archive.read(info)
            if RETIRED_VAULT in data:
                out[f"scripts/{info.filename}"] = (HERMES_HOME / "scripts" / info.filename, data)
    for name, live in (("config.yaml", HERMES_HOME / "config.yaml"), ("discord_instance_bindings.yaml", BINDINGS)):
        original = REPOINT_BACKUP / name
        if original.exists() and RETIRED_VAULT in original.read_bytes():
            out[name] = (live, original.read_bytes())
    return out


def live_scripts() -> dict[str, Path]:
    root = HERMES_HOME / "scripts"
    out: dict[str, Path] = {}
    for path in root.rglob("*"):
        if path.is_file() and not SKIP_PARTS.intersection(path.parts) and ".bak" not in path.name and not path.name.startswith(".hermes-tmp"):
            out["scripts/" + path.relative_to(root).as_posix()] = path
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    backup_dir = BACKUP_ROOT / f"line-endings-{time.strftime('%Y%m%d_%H%M%S')}"
    originals = repoint_originals()
    labels = sorted(set(originals) | set(live_scripts()))
    scripts = live_scripts()
    counts = {"restored": 0, "normalised": 0}
    for label in labels:
        path = originals[label][0] if label in originals else scripts[label]
        try:
            live = path.read_bytes()
        except OSError:
            continue
        new, rule = None, ""
        if label in originals:
            new, rule = restored(live, originals[label][1]), "restored"
        if new is None and label.startswith("scripts/"):
            new, rule = normalised(live, label), "normalised"
        if new is None:
            continue
        counts[rule] += 1
        crlf = live.count(b"\r\n")
        print(f"[LineEndings] {'would be ' if args.dry_run else ''}{rule}: {label} ({crlf} CRLF)")
        if args.dry_run:
            continue
        copy = backup_dir / label
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(live)
        path.write_bytes(new)
    tail = "" if args.dry_run or not sum(counts.values()) else f"; backup {backup_dir}"
    print(f"[LineEndings] {'dry run: ' if args.dry_run else ''}{counts['restored']} restored, {counts['normalised']} normalised{tail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
