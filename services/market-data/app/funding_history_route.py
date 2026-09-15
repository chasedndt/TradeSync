"""``GET /funding-history/hyperliquid/{symbol}``: hourly Hyperliquid funding rate and premium rows.

State-api's timeframe records read it for the funding and premium features.
The provider list is the service's own, filled when the service starts, so the
route sees the provider as soon as it is enabled.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from tradesync_core.feed_heartbeat import iso

from .feed_status import feed

HEARTBEAT = feed("hyperliquid_funding_history", label="Hyperliquid funding-history route", kind="route", authority="display_only",
                 influence="Context for the Timeframes records: funding and premium carry only the weight they earn out of "
                           "sample on that page, and nothing in opportunity scoring.",
                 counts=("requests", "rows"))


def router_for(providers: list, symbols: list[str]) -> APIRouter:
    router = APIRouter()

    @router.get("/funding-history/hyperliquid/{symbol}")
    async def get_funding_history_rows(symbol: str, start_ms: int, end_ms: int | None = None):
        """Hourly Hyperliquid funding rate and premium for a window, as [time_s, rate, premium] rows (context for timeframe records)."""
        if symbol not in symbols:
            return JSONResponse(status_code=404, content={"error": "untracked_symbol", "symbol": symbol})
        provider = next((p for p in providers if p.venue == "hyperliquid" and p.enabled), None)
        if provider is None:
            HEARTBEAT.failed("the Hyperliquid provider is not enabled", state="unavailable")
            return JSONResponse(status_code=503, content={"error": "provider_unavailable", "venue": "hyperliquid"})
        try:
            rows = await provider.fetch_funding_history(symbol, start_ms, end_ms)
        except Exception as exc:
            HEARTBEAT.failed(exc)
            raise
        HEARTBEAT.count("requests")
        if rows:
            # The provider serves what it holds when a venue page fails, so the newest hour is the freshness to watch.
            HEARTBEAT.succeeded(rows=len(rows))
            HEARTBEAT.detail.update(newest_row_at=iso(max(int(r["ts"]) for r in rows) / 1000), last_symbol=symbol)
        else:
            HEARTBEAT.error(f"no funding rows for {symbol} in the requested window")
        return {"venue": "hyperliquid", "symbol": symbol, "authority": "display_only",
                "rows": [[int(r["ts"]) // 1000, float(r["rate"]), float(r.get("premium") or 0.0)] for r in rows]}

    return router
