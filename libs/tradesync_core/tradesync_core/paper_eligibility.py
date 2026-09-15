"""Which opportunities may open a managed paper position: directional, fresh, and in the tracked universe.

The universe is whatever market-data reports it tracks (one compose anchor,
``MARKET_SYMBOLS``); nothing here names a symbol. An unreadable universe admits
nothing rather than falling back to a list.

Each check returns ``(status, message)`` for a refusal, or None: 422 for an
opportunity that can never be admitted, 409 for one that is too old now, 503 when
the universe cannot be read.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Collection, Mapping

from .paper_lifecycle_rules import COMMON


def direction(opportunity: Mapping[str, Any]) -> str | None:
    value = str(opportunity.get("dir") or "").strip().lower()
    return value if value in ("long", "short") else None


def age_s(opportunity: Mapping[str, Any], now_s: float) -> float | None:
    at = opportunity.get("snapshot_ts")
    if isinstance(at, datetime):
        if at.tzinfo is None:
            return None
        at = at.timestamp()
    if isinstance(at, bool) or not isinstance(at, (int, float)) or not math.isfinite(at):
        return None
    return now_s - at


def opportunity_refusal(opportunity: Mapping[str, Any], now_s: float) -> tuple[int, str] | None:
    if direction(opportunity) is None:
        return 422, "Only directional (long or short) opportunities can open a paper position"
    age = age_s(opportunity, now_s)
    if age is None or not 0 <= age <= COMMON.max_opportunity_age_s:
        return 409, f"Opportunity older than {COMMON.max_opportunity_age_s / 60:g} minutes or timestamp unavailable"
    return None


def universe_refusal(symbol: str, universe: Collection[str]) -> tuple[int, str] | None:
    if not universe:
        return 503, "Tracked symbol universe unavailable; no paper entry admitted"
    if symbol not in universe:
        return 422, f"{symbol} is not in the tracked symbol universe"
    return None
