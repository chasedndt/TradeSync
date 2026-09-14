"""The timeframe outlook per market: lower, medium and higher time frames, from daily candles.

Daily Hyperliquid candles (the venue's backfill from 2020-08-19; real trading
from 2023-02-26) are fetched from market-data in chunks under its 1000-candle
limit, kept for an hour per market, and measured by ``tradesync_core``:
``horizon_outlook`` (trend and momentum state and the record behind it),
``horizon_evaluation`` (each feature's reading and record) and
``horizon_chart`` (candles, overlays and the record's cone). The heavy
measuring runs in a worker thread so no request waits behind it: a market
measured within the last six hours is served at once while a stale hour is
measured again behind it, and each horizon's chart is drawn once per measurement.

Nothing here is a forecast and no feature carries a weight: none has measured
skill at these horizons.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from app import background, horizon_reading
from tradesync_core.horizon_chart import chart_payload
from tradesync_core.intraday_horizons import measure as measure_intraday
from tradesync_core.horizon_evaluation import evaluate_all
from tradesync_core.horizon_features import FEATURES, Bars
from tradesync_core.horizon_outlook import BANDS, HORIZONS, MIN_HISTORY_DAYS, compose_horizons

router = APIRouter(tags=["market"])

HISTORY_START_S = int(datetime(2020, 8, 1, tzinfo=timezone.utc).timestamp())
CHUNK_DAYS = 900
CACHE_TTL_S = 3600
SERVE_STALE_S = 6 * 3600
WARM_SYMBOLS = ("BTC-PERP", "ETH-PERP")
BACKFILL_UNTIL = "2023-02-26"
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,15}-PERP$")
BY_KEY = {h.key: h for h in HORIZONS}
NOTE = ("A record of what followed past days in the same state, from Hyperliquid daily candles; not a forecast. "
        "No feature is weighted: none has measured skill at these horizons.")

_cache: dict[str, dict[str, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}
_refreshing: dict[str, asyncio.Task] = {}


def checked_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise HTTPException(status_code=400, detail="symbol must look like BTC-PERP")
    return symbol


async def fetch_daily(market_data_url: str, symbol: str) -> list[dict[str, Any]]:
    now_s, out = int(time.time()), {}
    async with httpx.AsyncClient(trust_env=False, timeout=30.0) as client:
        start = HISTORY_START_S
        while start < now_s:
            end = min(now_s, start + CHUNK_DAYS * 86400)
            response = await client.get(f"{market_data_url}/candles/hyperliquid/{symbol}",
                                        params={"interval": "1d", "start_ms": start * 1000, "end_ms": end * 1000})
            response.raise_for_status()
            for candle in response.json().get("candles", []):
                out[int(candle["time"])] = candle
            start = end
    return [out[k] for k in sorted(out)]


def _measure(symbol: str, candles: list[dict[str, Any]]) -> dict[str, Any]:
    bars = Bars.from_candles(candles, time.time())
    outlook = compose_horizons(symbol, candles, datetime.now(timezone.utc))
    evaluation = evaluate_all(bars) if len(bars) >= MIN_HISTORY_DAYS else {}
    return {"at": time.time(), "bars": bars, "outlook": outlook, "evaluation": evaluation}


def _refresh_behind(market_data_url: str, symbol: str) -> None:
    if symbol in _refreshing:
        return

    async def refresh() -> None:
        try:
            await measured(market_data_url, symbol, force=True)
        except Exception as exc:  # the stale entry stays; the next request tries again
            print(f"[Horizons] {symbol} not re-measured: {type(exc).__name__}")
        finally:
            _refreshing.pop(symbol, None)

    _refreshing[symbol] = asyncio.create_task(refresh())


async def measured(market_data_url: str, symbol: str, force: bool = False) -> dict[str, Any]:
    entry = _cache.get(symbol)
    if entry and not force:
        age = time.time() - entry["at"]
        if age < CACHE_TTL_S:
            return entry
        if age < SERVE_STALE_S:
            _refresh_behind(market_data_url, symbol)
            return entry
    lock = _locks.setdefault(symbol, asyncio.Lock())
    async with lock:
        entry = _cache.get(symbol)
        if entry and not force and time.time() - entry["at"] < CACHE_TTL_S:
            return entry
        candles = await fetch_daily(market_data_url, symbol)
        entry = await asyncio.to_thread(_measure, symbol, candles)
        _cache[symbol] = entry
        return entry


async def _entry_or_502(market_data_url: str, symbol: str) -> dict[str, Any]:
    try:
        return await measured(market_data_url, symbol)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=502, detail=f"daily candles unavailable ({type(exc).__name__})") from None


def register(app, state, *, market_data_url: str) -> None:
    intraday_cache: dict[str, dict] = {}
    intraday_lock = asyncio.Lock()

    @router.get('/state/market/intraday-horizons')
    async def intraday_horizons(symbol: str = Query('BTC-PERP', max_length=24)):
        symbol = checked_symbol(symbol)
        async with intraday_lock:
            entry = intraday_cache.get(symbol)
            if entry and time.time() - entry['at'] < 60:
                return entry['data']
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
                    response = await client.get(f'{market_data_url}/candles/hyperliquid/{symbol}', params={'interval': '1h', 'limit': 1000})
                    response.raise_for_status()
                    data = await asyncio.to_thread(measure_intraday, response.json()['candles'], time.time())
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                raise HTTPException(502, 'Intraday history unavailable, incomplete or stale; no inferred replacement') from None
            data.update(symbol=symbol, computed_at=datetime.now(timezone.utc).isoformat())
            if len(intraday_cache) >= 32:
                intraday_cache.pop(next(iter(intraday_cache)))
            intraday_cache[symbol] = {'at': time.time(), 'data': data}
            return data

    @router.get("/state/market/horizons")
    async def horizons(symbol: str = Query("BTC-PERP", max_length=24)):
        symbol = checked_symbol(symbol)
        entry = await _entry_or_502(market_data_url, symbol)
        return {
            "schema_version": "horizon_page_v1",
            "symbol": symbol,
            "computed_at": datetime.fromtimestamp(entry["at"], timezone.utc).isoformat(),
            "bands": BANDS,
            "horizons": [{"key": h.key, "label": h.label, "days": h.days, "band": h.band} for h in HORIZONS],
            "features": [{"key": f.key, "label": f.label, "kind": f.kind, "measures": f.measures} for f in FEATURES],
            "outlook": entry["outlook"],
            "evaluation": entry["evaluation"],
            "reading": horizon_reading.job_state(symbol),
            "history_note": f"Daily candles before {BACKFILL_UNTIL} are the venue's backfill and carry no volume.",
            "note": NOTE,
        }

    @router.get("/state/market/horizons/chart")
    async def horizon_chart(symbol: str = Query("BTC-PERP", max_length=24),
                            horizon: str = Query("1m", pattern="^(3d|1w|2w|1m|3m|6m)$")):
        symbol = checked_symbol(symbol)
        entry = await _entry_or_502(market_data_url, symbol)
        charts = entry.setdefault("charts", {})
        if horizon not in charts:
            read = next((r for r in entry["outlook"].get("horizons") or [] if r.get("key") == horizon), {})
            charts[horizon] = await asyncio.to_thread(chart_payload, entry["bars"], BY_KEY[horizon], read)
        return charts[horizon]

    @router.post("/state/market/horizons/reading")
    async def start_reading(symbol: str = Query("BTC-PERP", max_length=24)):
        symbol = checked_symbol(symbol)
        if horizon_reading.job_state(symbol).get("status") == "running":
            return {"status": "already_running", "reading": horizon_reading.job_state(symbol)}
        entry = await _entry_or_502(market_data_url, symbol)
        if not entry["outlook"].get("available"):
            raise HTTPException(status_code=409, detail="not enough daily history to read")
        asyncio.create_task(horizon_reading.run_reading(symbol, entry["outlook"], entry["evaluation"]))
        await asyncio.sleep(0)
        return {"status": "started", "reading": horizon_reading.job_state(symbol)}

    async def warm() -> None:
        await asyncio.sleep(120)  # let market-data settle after a restart
        while True:
            for symbol in WARM_SYMBOLS:
                try:
                    await measured(market_data_url, symbol, force=True)
                except Exception as exc:  # the next pass retries; a request still measures on demand
                    print(f"[Horizons] {symbol} not measured: {type(exc).__name__}")
            await asyncio.sleep(CACHE_TTL_S - 120)

    background.add("horizons_warm", warm)
    app.include_router(router)
