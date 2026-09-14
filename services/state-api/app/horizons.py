"""The timeframe outlook per market, from one hour to six months.

Two measurements per market, each cached and refreshed on its own clock:

- short term (1 hour to 1 day) from Hyperliquid 15-minute and hourly candles
  (the venue serves about 5,000 of each), re-measured every 5 minutes;
- lower, medium and higher time frames (3 days to 6 months) from daily
  candles since 2020, re-measured hourly.

Candles are backfilled once in chunks under market-data's 1000-candle limit and
then topped up with only the newest bars. ``tradesync_core`` measures them in a
worker thread: ``horizon_outlook`` (trend, momentum and the record),
``horizon_evaluation`` (each feature's reading, record and out-of-sample
weight) and ``horizon_chart`` (candles, overlays and the record's cone). A stale
measurement is served at once while it is measured again behind it; a page
never waits more than ``FIRST_WAIT_S`` for a market's first measurement, and
``POST /state/market/horizons/refresh`` measures now.
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
from tradesync_core.horizon_bars import Bars, with_funding
from tradesync_core.horizon_chart import chart_payload
from tradesync_core.horizon_evaluation import evaluate_all
from tradesync_core.horizon_features import FEATURES
from tradesync_core.horizon_outlook import MIN_HISTORY_BARS, band_summaries, compose_horizons
from tradesync_core.horizon_spec import BANDS, BY_KEY, HORIZONS, INTERVAL_SECONDS

router = APIRouter(tags=["market"])

PARTS: dict[str, tuple[str, ...]] = {"short": ("15m", "1h"), "long": ("1d",)}
PART_TTL_S = {"short": 300, "long": 3600}
SERVE_STALE_S = {"short": 3600, "long": 6 * 3600}
FIRST_WAIT_S = 20.0
DAILY_HISTORY_START_S = int(datetime(2020, 8, 1, tzinfo=timezone.utc).timestamp())
INTRADAY_BARS = 5000
CHUNK_BARS = 900
REFETCH_BARS = 3  # the newest bars are fetched again: the last one was still trading
WARM_SYMBOLS = ("BTC-PERP", "ETH-PERP")
BACKFILL_UNTIL = "2023-02-26"
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,15}-PERP$")
HORIZON_PATTERN = "^(" + "|".join(h.key for h in HORIZONS) + ")$"
NOTE = ("A record of what followed past bars in the same state, from Hyperliquid candles; not a forecast. "
        "Each feature carries only the weight it earned out of sample; a feature that earned nothing adds nothing.")

_candles: dict[tuple[str, str], dict[int, dict[str, Any]]] = {}
_backfilled: set[tuple[str, str]] = set()
_cache: dict[tuple[str, str], dict[str, Any]] = {}
_locks: dict[tuple[str, str], asyncio.Lock] = {}
_refreshing: dict[tuple[str, str], asyncio.Task] = {}
_errors: dict[tuple[str, str], str] = {}


def checked_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise HTTPException(status_code=400, detail="symbol must look like BTC-PERP")
    return symbol


def part_of(horizon_key: str) -> str:
    return "long" if BY_KEY[horizon_key].interval == "1d" else "short"


def history_start(interval: str, now_s: int) -> int:
    return DAILY_HISTORY_START_S if interval == "1d" else now_s - INTRADAY_BARS * INTERVAL_SECONDS[interval]


async def fetch_interval(client: httpx.AsyncClient, market_data_url: str, symbol: str, interval: str, now_s: int | None = None) -> list[dict[str, Any]]:
    """Every candle in the interval's history window: a full backfill once, then only the newest bars."""
    now_s = now_s or int(time.time())
    step = INTERVAL_SECONDS[interval]
    key = (symbol, interval)
    store = _candles.setdefault(key, {})
    first = history_start(interval, now_s)
    start = max(first, max(store) - REFETCH_BARS * step) if store and key in _backfilled else first
    while start < now_s:
        end = min(now_s, start + CHUNK_BARS * step)
        response = await client.get(f"{market_data_url}/candles/hyperliquid/{symbol}",
                                    params={"interval": interval, "start_ms": start * 1000, "end_ms": end * 1000})
        response.raise_for_status()
        for candle in response.json().get("candles", []):
            store[int(candle["time"])] = candle
        start = end
    _backfilled.add(key)
    for old in [t for t in store if t < first]:
        del store[old]
    return [store[t] for t in sorted(store)]


async def fetch_funding(client: httpx.AsyncClient, market_data_url: str, symbol: str, part: str) -> list[list[float]]:
    """Hourly funding rate and premium rows for the part's history; empty when unavailable (the candle analysis stands without them)."""
    now_s = int(time.time())
    start_s = DAILY_HISTORY_START_S if part == "long" else now_s - INTRADAY_BARS * 3600
    try:
        response = await client.get(f"{market_data_url}/funding-history/hyperliquid/{symbol}",
                                    params={"start_ms": start_s * 1000, "end_ms": now_s * 1000})
        response.raise_for_status()
        return response.json().get("rows") or []
    except (httpx.HTTPError, ValueError):
        return []


async def fetch_part(market_data_url: str, symbol: str, part: str) -> dict[str, list[Any]]:
    async with httpx.AsyncClient(trust_env=False, timeout=60.0) as client:
        out: dict[str, list[Any]] = {interval: await fetch_interval(client, market_data_url, symbol, interval) for interval in PARTS[part]}
        out["funding"] = await fetch_funding(client, market_data_url, symbol, part)
        return out


def _measure(symbol: str, part: str, candles: dict[str, list[Any]]) -> dict[str, Any]:
    now = time.time()
    funding = candles.get("funding") or []
    bars = {interval: with_funding(Bars.from_candles(rows, now, INTERVAL_SECONDS[interval]), funding)
            for interval, rows in candles.items() if interval in INTERVAL_SECONDS}
    horizons = tuple(h for h in HORIZONS if h.interval in PARTS[part])
    return {"at": now, "part": part, "bars": bars, "charts": {},
            "outlook": compose_horizons(symbol, bars, datetime.now(timezone.utc), horizons),
            "evaluation": evaluate_all(bars, horizons)}


def _refresh_behind(market_data_url: str, symbol: str, part: str) -> asyncio.Task:
    key = (symbol, part)
    if key in _refreshing:
        return _refreshing[key]

    async def refresh() -> None:
        try:
            await measured(market_data_url, symbol, part, force=True)
            _errors.pop(key, None)
        except Exception as exc:  # the stale entry stays; the next request tries again
            _errors[key] = type(exc).__name__
            print(f"[Horizons] {symbol} {part} not measured: {type(exc).__name__}")
        finally:
            _refreshing.pop(key, None)

    _refreshing[key] = asyncio.create_task(refresh())
    return _refreshing[key]


async def measured(market_data_url: str, symbol: str, part: str, force: bool = False) -> dict[str, Any]:
    key = (symbol, part)
    entry = _cache.get(key)
    if entry and not force:
        age = time.time() - entry["at"]
        if age < PART_TTL_S[part]:
            return entry
        if age < SERVE_STALE_S[part]:
            _refresh_behind(market_data_url, symbol, part)
            return entry
    requested = time.time()
    async with _locks.setdefault(key, asyncio.Lock()):
        entry = _cache.get(key)
        if entry and (entry["at"] >= requested or (not force and time.time() - entry["at"] < PART_TTL_S[part])):
            return entry
        candles = await fetch_part(market_data_url, symbol, part)
        entry = await asyncio.to_thread(_measure, symbol, part, candles)
        _cache[key] = entry
        return entry


async def part_or_error(market_data_url: str, symbol: str, part: str) -> tuple[dict[str, Any] | None, str | None]:
    key = (symbol, part)
    if key not in _cache:
        task = _refresh_behind(market_data_url, symbol, part)
        try:
            await asyncio.wait_for(asyncio.shield(task), FIRST_WAIT_S)
        except asyncio.TimeoutError:
            return None, "measuring"
        entry = _cache.get(key)
        return (entry, None) if entry else (None, f"{part} candles unavailable ({_errors.get(key, 'no candles')})")
    try:
        return await measured(market_data_url, symbol, part), None
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return None, f"{part} candles unavailable ({type(exc).__name__})"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def page_payload(symbol: str, entries: dict[str, dict[str, Any] | None], errors: dict[str, str], readings: dict[str, Any]) -> dict[str, Any]:
    present = [e for e in (entries.get("short"), entries.get("long")) if e]
    reads = {r["key"]: r for e in present for r in e["outlook"].get("horizons") or []}
    horizons = [reads[h.key] for h in HORIZONS if h.key in reads]
    available = any(r.get("available") for r in horizons)
    history: dict[str, Any] = {}
    evaluation: dict[str, Any] = {}
    for e in present:
        history.update(e["outlook"].get("history") or {})
        evaluation.update(e["evaluation"])
    outlook = {
        "schema_version": "horizon_outlook_v2", "symbol": symbol, "available": available,
        "reason": None if available else ("; ".join(errors.values()) or next((e["outlook"].get("reason") for e in present), None) or "no history"),
        "last_close": next((e["outlook"].get("last_close") for e in present if e["outlook"].get("available")), None),
        "history": history, "horizons": horizons, "bands": band_summaries(horizons),
        "method": next((e["outlook"]["method"] for e in present if e["outlook"].get("method")), {}),
    }
    return {
        "schema_version": "horizon_page_v2",
        "symbol": symbol,
        "computed_at": {part: _iso(e["at"]) for part, e in entries.items() if e},
        "bands": BANDS,
        "horizons": [{"key": h.key, "label": h.label, "steps": h.steps, "interval": h.interval, "band": h.band} for h in HORIZONS],
        "features": [{"key": f.key, "label": f.label, "kind": f.kind, "measures": f.measures} for f in FEATURES],
        "outlook": outlook,
        "evaluation": evaluation,
        "readings": readings,
        "errors": errors,
        "history_note": (f"Daily candles before {BACKFILL_UNTIL} are the venue's backfill and carry no volume. Hyperliquid serves about "
                         "5,000 15-minute and hourly candles, so short-term records cover about 52 and 208 days."),
        "note": NOTE,
    }


def register(app, state, *, market_data_url: str) -> None:
    @router.get("/state/market/horizons")
    async def horizons(symbol: str = Query("BTC-PERP", max_length=24)):
        symbol = checked_symbol(symbol)
        (short, short_error), (long, long_error) = await asyncio.gather(
            part_or_error(market_data_url, symbol, "short"), part_or_error(market_data_url, symbol, "long"))
        errors = {part: error for part, error in (("short", short_error), ("long", long_error)) if error}
        if short is None and long is None and "measuring" not in errors.values():
            raise HTTPException(status_code=502, detail="; ".join(errors.values()))
        readings = await horizon_reading.latest(getattr(state, "pool", None), symbol)
        return page_payload(symbol, {"short": short, "long": long}, errors, readings)

    @router.get("/state/market/horizons/chart")
    async def horizon_chart(symbol: str = Query("BTC-PERP", max_length=24), horizon: str = Query("1m", pattern=HORIZON_PATTERN)):
        symbol = checked_symbol(symbol)
        h = BY_KEY[horizon]
        entry, error = await part_or_error(market_data_url, symbol, part_of(horizon))
        if entry is None:
            raise HTTPException(status_code=503 if error == "measuring" else 502, detail=error)
        bars = entry["bars"].get(h.interval)
        if bars is None or len(bars) < MIN_HISTORY_BARS:
            raise HTTPException(status_code=409, detail=f"not enough {h.interval} candles to draw {h.label}")
        charts = entry["charts"]
        if horizon not in charts:
            read = next((r for r in entry["outlook"].get("horizons") or [] if r.get("key") == horizon), {})
            charts[horizon] = await asyncio.to_thread(chart_payload, bars, h, read)
        return charts[horizon]

    @router.post("/state/market/horizons/refresh")
    async def refresh(symbol: str = Query("BTC-PERP", max_length=24)):
        symbol = checked_symbol(symbol)
        results = await asyncio.gather(*(measured(market_data_url, symbol, part, force=True) for part in PARTS), return_exceptions=True)
        computed = {part: _iso(r["at"]) for part, r in zip(PARTS, results) if isinstance(r, dict)}
        errors = {part: type(r).__name__ for part, r in zip(PARTS, results) if not isinstance(r, dict)}
        if not computed:
            raise HTTPException(status_code=502, detail="; ".join(f"{p} candles unavailable ({e})" for p, e in errors.items()))
        return {"symbol": symbol, "computed_at": computed, "errors": errors}

    @router.post("/state/market/horizons/reading")
    async def start_reading(symbol: str = Query("BTC-PERP", max_length=24), scope: str = Query("short", pattern="^(short|lower|medium|higher)$")):
        symbol = checked_symbol(symbol)
        entry, error = await part_or_error(market_data_url, symbol, "short" if scope == "short" else "long")
        if entry is None:
            raise HTTPException(status_code=503 if error == "measuring" else 502, detail=error)
        if not entry["outlook"].get("available"):
            raise HTTPException(status_code=409, detail="not enough history to read")
        return await horizon_reading.start(getattr(state, "pool", None), symbol, scope, entry["outlook"], entry["evaluation"],
                                           datetime.fromtimestamp(entry["at"], timezone.utc))

    async def warm() -> None:
        await asyncio.sleep(120)  # let market-data settle after a restart
        while True:
            for symbol in WARM_SYMBOLS:
                for part in PARTS:
                    entry = _cache.get((symbol, part))
                    if entry is None or time.time() - entry["at"] >= PART_TTL_S[part] - 30:
                        try:
                            await measured(market_data_url, symbol, part, force=True)
                        except Exception as exc:  # the next pass retries; a request still measures on demand
                            print(f"[Horizons] {symbol} {part} not measured: {type(exc).__name__}")
            await asyncio.sleep(60)

    background.add("horizons_warm", warm)
    app.include_router(router)
