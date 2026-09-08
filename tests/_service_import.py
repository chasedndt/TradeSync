"""Import a service's modules without claiming the global ``app`` name.

Every service in this repository packages its code as ``app``. Only one can own
that name in a Python process, so tests that inserted a service directory onto
``sys.path`` silently decided which service ``app`` meant for the whole run.

The symptom was order-dependent: ``tests/test_phase3d.py`` passed 32/32 alone
and failed 4 in a directory run, because ``test_market_data_math.py`` sorts
earlier and claimed ``app`` for market-data first. Nothing was wrong with the
code under test.

This loads a service under a private package name, with an explicit
``__path__`` so its own relative imports still resolve.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_service_package(alias: str, service_dir: str, package: str = "app"):
    """Register ``<service_dir>/<package>`` under ``alias`` and return it.

    ``alias`` must be unique per service, e.g. ``market_data_app``. Repeated
    calls return the already-registered module rather than re-importing.
    """
    if alias in sys.modules:
        return sys.modules[alias]

    root = REPO_ROOT / "services" / service_dir / package
    if not root.is_dir():
        raise ModuleNotFoundError(f"no {package} package at {root}")

    module = types.ModuleType(alias)
    module.__path__ = [str(root)]
    sys.modules[alias] = module
    return module


def load_service_module(alias: str, service_dir: str, module_name: str):
    """Import one module from a service, under the service's private alias."""
    load_service_package(alias, service_dir)
    return importlib.import_module(f"{alias}.{module_name}")


def load_module_by_path(alias: str, relative_path: str):
    """Load a single file as a module, bypassing package naming entirely.

    For services whose entry point is a bare ``main.py``: importing that by name
    picks up whichever ``main`` is first on the path, and this repository has one
    at its root.
    """
    if alias in sys.modules:
        return sys.modules[alias]

    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module
