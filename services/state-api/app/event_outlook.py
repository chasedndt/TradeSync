"""Measured event reactions and recent coverage, for the outlook and the events panel.

Two slow things are kept warm in the background so no page waits on them:

- **reaction profiles**: past release dates per event kind (FRED for the data
  releases, the Fed's published calendar for FOMC) and a lookback of hourly
  Hyperliquid candles, measured by ``tradesync_core.event_reactions``;
  refreshed every six hours;
- **recent articles** on the event kinds scheduled this week, from GDELT's
  article list, cached for three hours, spaced and backed off so a rate limit
  degrades to "no articles" rather than an error.

``/state/market/event-reactions`` answers from that memory at once. The
edition builder uses the same functions, waiting for a first computation if
none exists yet.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter

from app import background
from tradesync_core.event_reactions import EVENT_KINDS, kind_for_title, profile, release_instant_s
from tradesync_core.market_outlook import LOOKAHEAD_MINUTES, key_events

# httpx logs request URLs at INFO; a FRED URL carries the API key.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

router = APIRouter(tags=["thesis"])


def _eastern():
    try:
        return ZoneInfo("America/New_York")
    except Exception:
        return timezone(timedelta(hours=-4))


ET = _eastern()
PROFILE_SYMBOLS = tuple(s.strip() for s in os.getenv("OUTLOOK_PROFILE_SYMBOLS", "BTC-PERP,ETH-PERP").split(",") if s.strip())
LOOKBACK_DAYS = int(os.getenv("OUTLOOK_LOOKBACK_DAYS", "180"))
PROFILE_REFRESH_S = 6 * 3600
ARTICLE_TTL_S = 3 * 3600
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_SPACING_S = 20.0
GDELT_BACKOFF_S = 900.0
CHUNK_DAYS = 25

_profiles: dict[str, Any] = {"computed_at": None, "computed_ts": 0.0, "data": {}, "window": {}, "errors": [], "computing": False}
_articles: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_gdelt = {"last": 0.0, "blocked_until": 0.0}
_lock: asyncio.Lock | None = None


def events_from_context(context: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    calendar = ((context or {}).get("providers") or {}).get("calendar") or {}
    return list((calendar.get("data") or {}).get("events") or [])


def upcoming_kinds(events: Sequence[Mapping[str, Any]]) -> list[str]:
    seen: list[str] = []
    for e in events:
        m = e.get("minutes_until")
        if not isinstance(m, int) or m < -60 or m > LOOKAHEAD_MINUTES:
            continue
        if not (e.get("impact") == "High" or e.get("market_moving")):
            continue
        kind = kind_for_title(str(e.get("title") or ""))
        if kind and kind.key not in seen:
            seen.append(kind.key)
    return seen


async def _release_dates(client: httpx.AsyncClient, kind, start: date, today: date) -> list[date]:
    if kind.fixed_dates:
        return [d for d in (date.fromisoformat(x) for x in kind.fixed_dates) if start <= d < today]
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key or kind.release_id is None:
        return []
    r = await client.get(
        "https://api.stlouisfed.org/fred/release/dates",
        params={"release_id": kind.release_id, "api_key": key, "file_type": "json", "realtime_start": start.isoformat(),
                "include_release_dates_with_no_data": "false", "sort_order": "asc", "limit": "400"},
        timeout=20.0,
    )
    r.raise_for_status()
    return sorted({d for d in (date.fromisoformat(x["date"]) for x in r.json().get("release_dates", [])) if start <= d < today})


async def _candles(client: httpx.AsyncClient, market_data_url: str, symbol: str, start_s: int, end_s: int) -> list[dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    t = start_s
    while t < end_s:
        e = min(end_s, t + CHUNK_DAYS * 86400)
        r = await client.get(f"{market_data_url}/candles/hyperliquid/{symbol}",
                             params={"interval": "1h", "start_ms": t * 1000, "end_ms": e * 1000}, timeout=30.0)
        r.raise_for_status()
        for c in r.json().get("candles", []):
            out[int(c["time"])] = c
        t = e
    return [out[k] for k in sorted(out)]


async def compute_profiles(market_data_url: str) -> dict[str, Any]:
    global _lock
    _lock = _lock or asyncio.Lock()
    async with _lock:
        _profiles["computing"] = True
        errors: list[str] = []
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=LOOKBACK_DAYS)
        data: dict[str, Any] = {}
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                instants: dict[str, list[int]] = {}
                for kind in EVENT_KINDS.values():
                    try:
                        days = await _release_dates(client, kind, start, today)
                        instants[kind.key] = [release_instant_s(d, kind, ET) for d in days]
                    except Exception as exc:  # type only: a FRED error message carries the URL and key
                        errors.append(f"{kind.key}: release dates {type(exc).__name__}")
                        instants[kind.key] = []
                every = sorted({t for ts in instants.values() for t in ts})
                start_s = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()) - 2 * 86400
                end_s = int(time.time())
                for symbol in PROFILE_SYMBOLS:
                    try:
                        candles = await _candles(client, market_data_url, symbol, start_s, end_s)
                    except Exception as exc:
                        errors.append(f"{symbol}: candles {type(exc).__name__}")
                        continue
                    for key, ts in instants.items():
                        if ts:
                            data.setdefault(key, {})[symbol] = profile(EVENT_KINDS[key], ts, candles, every)
        finally:
            _profiles.update(
                computed_at=datetime.now(timezone.utc).isoformat(), computed_ts=time.time(), data=data or _profiles["data"],
                errors=errors, computing=False,
                window={"lookback_days": LOOKBACK_DAYS, "from": start.isoformat(), "to": today.isoformat(),
                        "symbols": list(PROFILE_SYMBOLS), "candles": "1h Hyperliquid"},
            )
        return _profiles["data"]


async def ensure_profiles(market_data_url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not _profiles["data"] or time.time() - _profiles["computed_ts"] > PROFILE_REFRESH_S:
        await compute_profiles(market_data_url)
    return _profiles["data"], _profiles["window"]


async def fetch_articles(kinds: Sequence[str], max_fetch: int = 4) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    fetched = 0
    async with httpx.AsyncClient(trust_env=False, headers={"User-Agent": "TradeSync private research workstation"}) as client:
        for key in kinds:
            cached = _articles.get(key)
            if cached and time.time() - cached[0] < ARTICLE_TTL_S:
                out[key] = cached[1]
                continue
            if fetched >= max_fetch or time.time() < _gdelt["blocked_until"] or key not in EVENT_KINDS:
                out[key] = cached[1] if cached else []
                continue
            wait = GDELT_SPACING_S - (time.time() - _gdelt["last"])
            if wait > 0:
                await asyncio.sleep(wait)
            _gdelt["last"] = time.time()
            fetched += 1
            try:
                r = await client.get(GDELT_URL, params={"query": f"{EVENT_KINDS[key].query} sourcelang:english", "mode": "artlist",
                                                        "maxrecords": "8", "format": "json", "timespan": "5d", "sort": "hybridrel"}, timeout=25.0)
                if r.status_code == 429:
                    _gdelt["blocked_until"] = time.time() + GDELT_BACKOFF_S
                    out[key] = cached[1] if cached else []
                    continue
                r.raise_for_status()
                body = r.json()
            except (httpx.HTTPError, ValueError):
                out[key] = cached[1] if cached else []
                continue
            arts = []
            for a in body.get("articles") or []:
                url = str(a.get("url") or "")
                if not url.startswith(("http://", "https://")):
                    continue
                arts.append({"title": str(a.get("title") or "").strip()[:200], "url": url[:500],
                             "domain": str(a.get("domain") or "")[:80], "seen": str(a.get("seendate") or "")})
            _articles[key] = (time.time(), arts[:6])
            out[key] = arts[:6]
    return out


async def articles_for(events: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return await fetch_articles(upcoming_kinds(events))


def cached_articles() -> dict[str, list[dict[str, Any]]]:
    return {k: v[1] for k, v in _articles.items()}


def register(app, state, *, market_data_url: str, calendar: Callable[[], Awaitable[dict[str, Any]]]) -> None:
    @router.get("/state/market/event-reactions")
    async def event_reactions():
        """This week's key events with their measured reaction and recent coverage. Never waits on a fetch."""
        try:
            events = events_from_context(await calendar())
        except Exception:
            events = []
        return {
            "schema_version": "event_reactions_v1",
            "computed_at": _profiles["computed_at"],
            "computing": _profiles["computing"],
            "window": _profiles["window"],
            "errors": _profiles["errors"],
            "kinds": {k.key: {"label": k.label, "source_url": k.source_url} for k in EVENT_KINDS.values()},
            "key_events": key_events(events, _profiles["data"], cached_articles()),
            "profiles": _profiles["data"],
            "note": "Past reactions measured on Hyperliquid candles, beside ordinary days at the same hour. A record, not a forecast.",
        }

    async def refresher():
        await asyncio.sleep(90)  # let market-data and the calendar settle first
        while True:
            try:
                if not _profiles["data"] or time.time() - _profiles["computed_ts"] > PROFILE_REFRESH_S:
                    await compute_profiles(market_data_url)
                await fetch_articles(upcoming_kinds(events_from_context(await calendar())))
            except Exception as exc:
                print(f"[Outlook] refresh failed: {type(exc).__name__}")
            await asyncio.sleep(1800)

    background.add("event_outlook", refresher)

    app.include_router(router)
