"""Liquidity and liquidations per market: the resting-liquidity heatmap, the estimated liquidation map, and received liquidations.

- ``GET /state/market/liquidity-heatmap``: recorded aggregated Hyperliquid books
  (``market_depth_snapshots``) averaged per time bucket, with the latest books and
  the largest walls near price.
- ``GET /state/market/liquidation-map``: estimated liquidation levels from Binance
  open-interest history (30 days, the only public history) and Hyperliquid candles
  (``tradesync_core.liquidation_map``); an estimate, stated as one.
- ``GET /state/market/liquidations``: liquidations received from Bybit and Binance
  (``market_liquidation_events``), by side over time. Hyperliquid publishes no
  market-wide liquidation feed.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from tradesync_core.liquidation_map import Bar, estimate, skew
from tradesync_core.liquidity_heatmap import WINDOWS as HEATMAP_WINDOWS, build, walls

router = APIRouter(tags=["market"])

SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,15}-PERP$")
# window -> (span seconds, bar interval shared by Binance open interest and Hyperliquid candles)
MAP_WINDOWS: dict[str, tuple[int, str]] = {"24h": (86400, "5m"), "3d": (3 * 86400, "15m"), "7d": (7 * 86400, "1h"), "30d": (30 * 86400, "4h")}
INTERVAL_SECONDS = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
MAP_CACHE_S = 300
LIQUIDATION_WINDOWS = {"1h": (3600, 300), "24h": (86400, 3600), "7d": (7 * 86400, 4 * 3600)}

_map_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}


def checked_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise HTTPException(status_code=400, detail="symbol must look like BTC-PERP")
    return symbol


def _levels(value: Any) -> list[list[float]]:
    return json.loads(value) if isinstance(value, str) else list(value or [])


async def depth_rows(pool, symbol: str, n_sig_figs: int, since: datetime) -> tuple[list[dict[str, Any]], datetime | None]:
    """Recorded books since ``since`` for one aggregation, and when recording began for the market."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT observed_at, mid_price, bids, asks FROM market_depth_snapshots "
            "WHERE symbol = $1 AND n_sig_figs = $2 AND observed_at >= $3 ORDER BY observed_at",
            symbol, n_sig_figs, since,
        )
        first = await conn.fetchval("SELECT min(observed_at) FROM market_depth_snapshots WHERE symbol = $1", symbol)
    out = [{"observed_at": r["observed_at"], "mid_price": r["mid_price"], "bids": _levels(r["bids"]), "asks": _levels(r["asks"])} for r in rows]
    return out, first


async def map_bars(market_data_url: str, symbol: str, interval: str) -> list[Bar]:
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        oi = await client.get(f"{market_data_url}/open-interest-history/binance/{symbol}", params={"period": interval, "limit": 500})
        oi.raise_for_status()
        rows = oi.json().get("rows") or []
        if not rows:
            return []
        step = INTERVAL_SECONDS[interval]
        start, end = rows[0]["time"], rows[-1]["time"] + step
        candles = await client.get(f"{market_data_url}/candles/hyperliquid/{symbol}",
                                   params={"interval": interval, "start_ms": start * 1000, "end_ms": end * 1000})
        candles.raise_for_status()
    by_time = {int(c["time"]): c for c in candles.json().get("candles") or []}
    bars: list[Bar] = []
    for row in rows:
        candle = by_time.get(int(row["time"]) // step * step)
        if candle:
            bars.append(Bar(int(candle["time"]), float(candle["high"]), float(candle["low"]), float(candle["close"]), float(row["oi_usd"])))
    return bars


def register(app, state, *, market_data_url: str) -> None:
    @router.get("/state/market/liquidity-heatmap")
    async def liquidity_heatmap(symbol: str = Query("BTC-PERP", max_length=24), window: str = Query("24h", pattern="^(6h|24h|3d|7d|30d)$")):
        symbol = checked_symbol(symbol)
        if not state.pool:
            raise HTTPException(status_code=503, detail="database unavailable")
        span, bucket, n_sig_figs = HEATMAP_WINDOWS[window]
        end = int(time.time()) // bucket * bucket + bucket
        start = end - span
        rows, first = await depth_rows(state.pool, symbol, n_sig_figs, datetime.fromtimestamp(start, timezone.utc))
        heatmap = await asyncio.to_thread(build, rows, bucket, start, end)
        latest = rows[-1] if rows else None
        return {
            "symbol": symbol, "window": window, "n_sig_figs": n_sig_figs, **heatmap,
            "latest": {"observed_at": latest["observed_at"].isoformat(), "mid": latest["mid_price"], "bids": latest["bids"], "asks": latest["asks"],
                       "walls": walls(latest["bids"], latest["asks"], latest["mid_price"])} if latest and latest["mid_price"] else None,
            "recording_since": first.isoformat() if first else None,
            "authority": "display_only",
            "note": ("Resting Hyperliquid orders as displayed, aggregated to "
                     f"{n_sig_figs} significant figures and averaged over each bucket. Orders can be cancelled; "
                     "this is not executable depth and not liquidation levels. Recording began at the time shown."),
        }

    @router.get("/state/market/liquidation-map")
    async def liquidation_map(symbol: str = Query("BTC-PERP", max_length=24), window: str = Query("7d", pattern="^(24h|3d|7d|30d)$")):
        symbol = checked_symbol(symbol)
        key = (symbol, window)
        cached = _map_cache.get(key)
        if cached and time.time() - cached[0] < MAP_CACHE_S:
            return cached[1]
        span, interval = MAP_WINDOWS[window]
        try:
            bars = await map_bars(market_data_url, symbol, interval)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"open interest or candles unavailable ({type(exc).__name__})") from None
        if len(bars) < 12:
            raise HTTPException(status_code=409, detail="Binance publishes no open-interest history for this market")
        first_shown = next((i for i, b in enumerate(bars) if b.time >= bars[-1].time - span), 0)
        result = await asyncio.to_thread(estimate, bars, first_shown)
        payload = {
            "symbol": symbol, "window": window, "interval": interval, "bucket_seconds": INTERVAL_SECONDS[interval], **result,
            "skew_3pct": skew(result["profile"]), "source": "binance_open_interest",
            "coverage": {"from": datetime.fromtimestamp(bars[0].time, timezone.utc).isoformat(),
                         "to": datetime.fromtimestamp(bars[-1].time, timezone.utc).isoformat(), "bars": len(bars)},
            "authority": "context_only",
            "note": ("Estimated liquidation levels: Binance USDT-M open-interest changes placed at Hyperliquid prices with an assumed "
                     "leverage mix, cleared when price trades through them. An estimate of where leveraged positions would be forced "
                     "out, not observed orders, and not Hyperliquid's own positions."),
        }
        _map_cache[key] = (time.time(), payload)
        return payload

    @router.get("/state/market/liquidations")
    async def liquidations(symbol: str = Query("BTC-PERP", max_length=24), window: str = Query("24h", pattern="^(1h|24h|7d)$")):
        symbol = checked_symbol(symbol)
        if not state.pool:
            raise HTTPException(status_code=503, detail="database unavailable")
        span, bucket = LIQUIDATION_WINDOWS[window]
        since = datetime.fromtimestamp(time.time() - span, timezone.utc)
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT source, position_side, price, notional_usd, event_time FROM market_liquidation_events "
                "WHERE symbol = $1 AND event_time >= $2 ORDER BY event_time", symbol, since)
            first = await conn.fetchval("SELECT min(received_at) FROM market_liquidation_events")
        buckets: dict[int, dict[str, float]] = {}
        totals = {"long": 0.0, "short": 0.0}
        by_source: dict[str, dict[str, float]] = {}
        for r in rows:
            t = int(r["event_time"].timestamp()) // bucket * bucket
            cell = buckets.setdefault(t, {"long": 0.0, "short": 0.0})
            cell[r["position_side"]] += r["notional_usd"]
            totals[r["position_side"]] += r["notional_usd"]
            source = by_source.setdefault(r["source"], {"long": 0.0, "short": 0.0})
            source[r["position_side"]] += r["notional_usd"]
        largest = sorted(rows, key=lambda r: -r["notional_usd"])[:15]
        return {
            "symbol": symbol, "window": window, "bucket_seconds": bucket,
            "totals": {k: round(v) for k, v in totals.items()},
            "by_source": {s: {k: round(v) for k, v in sides.items()} for s, sides in by_source.items()},
            "buckets": [[t, round(v["long"]), round(v["short"])] for t, v in sorted(buckets.items())],
            "largest": [{"source": r["source"], "side": r["position_side"], "price": r["price"], "usd": round(r["notional_usd"]),
                         "time": r["event_time"].isoformat()} for r in largest],
            "events": len(rows), "recording_since": first.isoformat() if first else None,
            "authority": "context_only",
            "note": ("Liquidations received from Bybit (BTC, ETH, SOL) and Binance USDT-M, recorded once a minute. Binance sends at most one "
                     "liquidation per market per second, so bursts are undercounted. Hyperliquid publishes no market-wide liquidation feed."),
        }

    app.include_router(router)
