"""``GET /funding-history/hyperliquid/{symbol}``: hourly Hyperliquid funding rate and premium rows.

State-api's timeframe records read it for the funding and premium features.
The provider list is the service's own, filled when the service starts, so the
route sees the provider as soon as it is enabled.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse


def router_for(providers: list, symbols: list[str]) -> APIRouter:
    router = APIRouter()

    @router.get("/funding-history/hyperliquid/{symbol}")
    async def get_funding_history_rows(symbol: str, start_ms: int, end_ms: int | None = None):
        """Hourly Hyperliquid funding rate and premium for a window, as [time_s, rate, premium] rows (context for timeframe records)."""
        if symbol not in symbols:
            return JSONResponse(status_code=404, content={"error": "untracked_symbol", "symbol": symbol})
        provider = next((p for p in providers if p.venue == "hyperliquid" and p.enabled), None)
        if provider is None:
            return JSONResponse(status_code=503, content={"error": "provider_unavailable", "venue": "hyperliquid"})
        rows = await provider.fetch_funding_history(symbol, start_ms, end_ms)
        return {"venue": "hyperliquid", "symbol": symbol, "authority": "display_only",
                "rows": [[int(r["ts"]) // 1000, float(r["rate"]), float(r.get("premium") or 0.0)] for r in rows]}

    return router
