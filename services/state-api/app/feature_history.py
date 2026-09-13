"""Feature histories for the charts on Regime Lab: each catalog feature's recorded series.

market-data keeps each feature's cadence-governed series in Redis for seven
days and serves them in batches (``/feature-histories``). This proxies one
batch for the cockpit and turns millisecond points into ``[seconds, value]``
pairs, the shape the charting library draws. Display only: nothing here feeds
scoring, and the normalisation the chart shows comes from the Regime Lab
overview, not from this route.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["regime-lab"])

FEATURE_ID_RE = re.compile(r"^[a-z0-9_]{3,64}$")
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,15}-PERP$")
MAX_FEATURE_IDS = 32


def checked_ids(feature_ids: str) -> list[str]:
    ids = [part.strip() for part in feature_ids.split(",") if part.strip()]
    if not ids or len(ids) > MAX_FEATURE_IDS or any(not FEATURE_ID_RE.fullmatch(i) for i in ids):
        raise HTTPException(status_code=400, detail=f"feature_ids: 1 to {MAX_FEATURE_IDS} catalog ids (lowercase letters, digits, underscores)")
    return ids


def to_points(raw: list[Any]) -> list[list[float]]:
    """``{"ts": ms, "value": v}`` rows as ``[seconds, value]``, oldest first, skipping malformed rows."""
    out: list[list[float]] = []
    for row in raw:
        if isinstance(row, dict) and isinstance(row.get("ts"), (int, float)) and isinstance(row.get("value"), (int, float)):
            out.append([int(row["ts"]) // 1000, float(row["value"])])
    return out


async def fetch_series(market_data_url: str, symbol: str, ids: list[str], window: str, points: int) -> dict[str, Any]:
    async with httpx.AsyncClient(trust_env=False, timeout=15.0) as client:
        response = await client.get(f"{market_data_url}/feature-histories/hyperliquid/{symbol}",
                                    params={"feature_ids": ",".join(ids), "window": window, "points": points})
        response.raise_for_status()
        return response.json().get("series", {})


def register(app, state, *, market_data_url: str) -> None:
    @router.get("/state/regime-lab/feature-history")
    async def feature_history(
        symbol: str = Query("BTC-PERP", max_length=24),
        feature_ids: str = Query(..., max_length=2400),
        window: str = Query("7d", pattern="^(1h|4h|24h|7d)$"),
        points: int = Query(600, ge=10, le=2000),
    ):
        symbol = symbol.strip().upper()
        if not SYMBOL_RE.fullmatch(symbol):
            raise HTTPException(status_code=400, detail="symbol must look like BTC-PERP")
        ids = checked_ids(feature_ids)
        try:
            series = await fetch_series(market_data_url, symbol, ids, window, points)
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"feature histories unavailable ({type(exc).__name__})") from None
        return {
            "schema_version": "feature_history_v1",
            "symbol": symbol,
            "window": window,
            "series": {fid: to_points(series.get(fid) or []) for fid in ids},
            "authority": "display_only",
        }

    app.include_router(router)
