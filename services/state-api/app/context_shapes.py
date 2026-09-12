"""The response shapes every context provider answers in.

Kept apart from the fetching so the contract the Cockpit reads — status,
staleness, age, and the two authority fields that are always false — is one
short file rather than something reconstructed from four fetchers.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict


def disabled(provider: str, reason: str = "disabled_by_configuration") -> Dict[str, Any]:
    return {
        "provider": provider,
        "status": "disabled",
        "source_type": "context_only",
        "execution_authority": False,
        "reason": reason,
        "data": {},
    }


def unavailable(
    provider: str, error: str, failed_at: float, hold_seconds: int, ttl_seconds: int
) -> Dict[str, Any]:
    """No data at all, and how long before the provider is asked again."""
    retry_in = max(0, int(hold_seconds - (time.time() - failed_at)))
    return {
        "provider": provider,
        "status": "unavailable",
        "source_type": "context_only",
        "execution_authority": False,
        "cached": False,
        "stale": True,
        "age_seconds": None,
        "fetched_at": None,
        "ttl_seconds": ttl_seconds,
        "error": error,
        "retry_in_seconds": retry_in,
        "data": {},
    }


def formatted(
    provider: str, payload: Dict[str, Any], fetched_at: float, cached: bool, ttl_seconds: int
) -> Dict[str, Any]:
    """A cache entry as the Cockpit sees it; stale once older than its TTL."""
    age = max(0.0, time.time() - fetched_at)
    return {
        "provider": provider,
        "status": "healthy" if age <= ttl_seconds else "stale",
        "source_type": "context_only",
        "execution_authority": False,
        "cached": cached,
        "stale": age > ttl_seconds,
        "age_seconds": round(age, 3),
        "fetched_at": datetime.fromtimestamp(fetched_at, timezone.utc).isoformat(),
        "ttl_seconds": ttl_seconds,
        "data": payload,
    }
