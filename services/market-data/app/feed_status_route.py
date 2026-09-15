"""``GET /feeds/status``: every market-data feed's heartbeat, as counted in memory since the service started."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .feed_status import REGISTRY

router = APIRouter()


@router.get("/feeds/status")
async def feeds_status() -> dict[str, Any]:
    return REGISTRY.snapshot()
