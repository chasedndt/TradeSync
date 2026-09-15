"""Wake-up requests between the paper risk loops.

Plain flags polled once a second rather than asyncio events, so nothing binds to
an event loop at import time and a request made from a route or a hook reaches
the loop that serves it.
"""

from __future__ import annotations

import asyncio
import time

# Entries need a reconciliation that started after this process did.
PROCESS_STARTED_AT = time.time()

_requested: dict[str, bool] = {"reconcile": False, "evaluate": False}


def request(name: str) -> None:
    _requested[name] = True


def take(name: str) -> bool:
    requested = _requested.get(name, False)
    _requested[name] = False
    return requested


async def sleep_unless_requested(name: str, seconds: float, *, poll_s: float = 1.0) -> bool:
    """Sleep up to ``seconds``; return True early if ``name`` is requested meanwhile."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if take(name):
            return True
        await asyncio.sleep(min(poll_s, max(0.0, deadline - time.monotonic())))
    return take(name)
