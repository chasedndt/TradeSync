"""Run a QA script inside the running state-api container against this checkout's code, writing nothing into the container.

The container keeps serving its deployed code. This sends one Python program on
stdin to ``docker exec -i <container> python -``: the ``app`` and ``tradesync_core``
packages from this checkout held in memory, any helper modules named with ``--with``,
the migration files the QA scripts apply as ``QA_FILES``, and the script itself. No file
is copied into the container, nothing is installed and the service is not restarted.
Credentials stay in the container's environment; this launcher never reads them.

    python tools/run_in_state_api.py tools/qa_managed_paper_positions.py \
        --with tools/qa_paper_live.py --with tools/qa_paper_replay.py -- [script args...]
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = os.environ.get("TRADESYNC_STATE_API_CONTAINER", "tradesync-full-state-api-1")
PACKAGES = {"app": ROOT / "services" / "state-api" / "app", "tradesync_core": ROOT / "libs" / "tradesync_core" / "tradesync_core"}
SHIPPED_FILES = ("ops/migrations/023_managed_paper_positions.sql", "ops/migrations/026_paper_control.sql",
                 "ops/migrations/032_managed_paper_funding.sql")

BOOTSTRAP = r'''
import importlib.abc
import importlib.util
import sys


class WorktreeSources(importlib.abc.MetaPathFinder, importlib.abc.InspectLoader):
    """Serves the shipped modules from memory ahead of the container's own copies."""

    def __init__(self, modules):
        self.modules = modules

    def find_spec(self, name, path=None, target=None):
        if name not in self.modules:
            return None
        return importlib.util.spec_from_loader(name, self, origin="worktree:" + name, is_package=self.modules[name][1])

    def get_source(self, name):
        return self.modules[name][0]

    def is_package(self, name):
        return self.modules[name][1]


for loaded in [name for name in sys.modules if name in MODULES]:
    del sys.modules[loaded]
sys.meta_path.insert(0, WorktreeSources(MODULES))
import builtins
builtins.QA_FILES = QA_FILES
sys.argv = ARGV
exec(compile(SCRIPT, ARGV[0], "exec"), {"__name__": "__main__", "QA_FILES": QA_FILES})
'''


def modules(helpers: list[Path]) -> dict[str, tuple[str, bool]]:
    shipped: dict[str, tuple[str, bool]] = {}
    for package, directory in PACKAGES.items():
        for path in sorted(directory.rglob("*.py")):
            parts = [package, *path.relative_to(directory).with_suffix("").parts]
            is_package = parts[-1] == "__init__"
            shipped[".".join(parts[:-1] if is_package else parts)] = (path.read_text(encoding="utf-8"), is_package)
        shipped.setdefault(package, ("", True))
    for helper in helpers:
        shipped[helper.stem] = (helper.read_text(encoding="utf-8"), False)
    return shipped


def parse(argv: list[str]) -> tuple[Path, list[Path], list[str]]:
    script, helpers, rest = Path(argv[0]).resolve(), [], argv[1:]
    while rest and rest[0] == "--with":
        helpers.append(Path(rest[1]).resolve())
        rest = rest[2:]
    return script, helpers, rest[1:] if rest[:1] == ["--"] else rest


def program(script: Path, helpers: list[Path], args: list[str]) -> str:
    files = {name: (ROOT / name).read_text(encoding="utf-8") for name in SHIPPED_FILES}
    return (f"MODULES = {modules(helpers)!r}\nQA_FILES = {files!r}\nARGV = {[script.name, *args]!r}\n"
            f"SCRIPT = {script.read_text(encoding='utf-8')!r}\n{BOOTSTRAP}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    script, helpers, args = parse(sys.argv[1:])
    command = ["docker", "exec", "-i", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PYTHONUNBUFFERED=1", CONTAINER, "python", "-"]
    return subprocess.run(command, input=program(script, helpers, args).encode("utf-8")).returncode


if __name__ == "__main__":
    raise SystemExit(main())
