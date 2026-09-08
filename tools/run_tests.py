#!/usr/bin/env python
"""Run every Python test suite in this repository, each in its own process.

Why separate processes
----------------------
Every service packages its code as ``app``. A Python process can only have one
``app``, so a single ``pytest tests services`` run silently decides which
service that name means for the whole run: with all four suites collected
together, market-data claimed ``app`` and state-api's tests then imported
market-data's ``main`` and failed on names that were never supposed to be there.

The service suites are deliberately written against ``app``, because that is
how the service is imported inside its own container. Keeping that property and
running them together at the same time is not possible, so they are run one
process each and the results are combined here.

The root ``tests/`` suite is different: it reaches across services, so it uses
``tests/_service_import.py`` to load each one under a private alias.

Usage
-----
    python tools/run_tests.py               # every unit suite
    python tools/run_tests.py --integration  # and the ones needing the stack
    python tools/run_tests.py state-api      # one suite, by name
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_LIB = ROOT / "libs" / "tradesync_core"


@dataclass(frozen=True)
class Suite:
    name: str
    path: Path
    cwd: Path


SUITES: tuple[Suite, ...] = (
    # Cross-service; imports each service under a private alias.
    Suite("root", ROOT / "tests", ROOT),
    # Service-local; each imports its own code as "app", as its container does.
    Suite("state-api", Path("tests"), ROOT / "services" / "state-api"),
    Suite("market-data", Path("tests"), ROOT / "services" / "market-data"),
    Suite("exec-hl-svc", Path("tests"), ROOT / "services" / "exec-hl-svc"),
    Suite("signer-svc", Path("tests"), ROOT / "services" / "signer-svc"),
)

# Needs the bounded Docker profile up. Kept out of the default run: a service
# restarting mid-run is not a code failure, and conflating the two is how a red
# suite stops meaning anything.
INTEGRATION = Suite("integration", ROOT / "tests", ROOT)


def run(suite: Suite, extra: list[str]) -> tuple[int, str, list[str]]:
    """Run one suite; return its exit code, summary line and failing tests."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(suite.path), "-q", *extra],
        cwd=suite.cwd,
        text=True,
        capture_output=True,
        env={**_env(), "PYTHONPATH": str(CORE_LIB)},
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    summary = lines[-1] if lines else "(no output)"
    # Named so an intermittent failure is identifiable from the summary alone.
    # A run that only reports "1 failed" tells you nothing you can act on, and
    # the detail is gone by the time anyone looks.
    failures = [
        line.split(" ", 1)[1].strip()
        for line in lines
        if line.startswith("FAILED ") or line.startswith("ERROR ")
    ]
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
    return result.returncode, summary, failures


def _env() -> dict[str, str]:
    import os

    return dict(os.environ)


def main() -> int:
    args = list(sys.argv[1:])
    with_integration = "--integration" in args
    args = [a for a in args if a != "--integration"]

    wanted = set(args) & {s.name for s in SUITES}
    extra = [a for a in args if a not in wanted]
    selected = [s for s in SUITES if not wanted or s.name in wanted]
    if with_integration and not wanted:
        selected = selected + [INTEGRATION]

    results: list[tuple[Suite, int, str, list[str]]] = []
    for suite in selected:
        print(f"=== {suite.name} ===", flush=True)
        suite_extra = extra + (['-m', 'integration'] if suite is INTEGRATION else [])
        code, summary, failures = run(suite, suite_extra)
        print(f"{suite.name}: {summary}", flush=True)
        results.append((suite, code, summary, failures))

    print()
    print("summary")
    if not with_integration:
        print("  (integration tests skipped; add --integration with the stack up)")
    for suite, code, summary, failures in results:
        mark = "ok  " if code == 0 else "FAIL"
        print(f"  {mark} {suite.name:<12} {summary}")
        for failure in failures:
            print(f"       {failure}")

    return 0 if all(code == 0 for _, code, _, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
