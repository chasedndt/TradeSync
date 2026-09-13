"""Long-running background loops, started and stopped by the app's lifespan.

The state API is built with a lifespan handler, and FastAPI silently ignores
startup-event hooks when one is given. Three loops were once
registered that way and never ran, so the Hermes link sat at "checking" while
the gateway answered. Modules register their loops here instead; the lifespan
starts them once the database pool exists and cancels them on shutdown.

``STATE_API_BACKGROUND_LOOPS=false`` keeps them off (tests, one-off tooling).
"""

from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable

LoopFactory = Callable[[], Awaitable[None]]

_factories: list[tuple[str, LoopFactory]] = []
_tasks: list[asyncio.Task] = []


def add(name: str, factory: LoopFactory) -> None:
    """Register a loop by name; registering the same name again is ignored."""
    if any(existing == name for existing, _ in _factories):
        return
    _factories.append((name, factory))


def registered() -> list[str]:
    return [name for name, _ in _factories]


def running() -> list[str]:
    return [task.get_name() for task in _tasks if not task.done()]


def enabled() -> bool:
    return os.getenv("STATE_API_BACKGROUND_LOOPS", "true").lower() != "false"


async def _guard(name: str, factory: LoopFactory) -> None:
    try:
        await factory()
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # a loop that dies must not take the API with it
        print(f"[Background] loop {name} stopped: {type(exc).__name__}")


def start_all() -> list[str]:
    """Start every registered loop that is not already running; return the names started."""
    if not enabled():
        return []
    live = set(running())
    started: list[str] = []
    for name, factory in _factories:
        if name in live:
            continue
        _tasks.append(asyncio.create_task(_guard(name, factory), name=name))
        started.append(name)
    return started


async def stop_all() -> None:
    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
