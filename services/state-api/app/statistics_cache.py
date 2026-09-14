"""Slow outcome statistics, served from memory and measured behind the request.

The skill gate and the evidence cards bootstrap every cell together: tens of
seconds of pure-Python work. Measured per request, each Regime Lab page load
held the state API. Each reading is now measured in a worker thread, one
measurement at a time across every reading, kept with the time it was computed
and served from here:

- an entry younger than the TTL is served as it is;
- an older entry is served marked ``stale`` while it is measured again behind it;
- a market with no entry yet answers ``computing`` at once (HTTP 202) and is
  measured behind the request;
- the refresh loop re-measures every market someone asked about within the
  keep-warm window shortly before its entry expires, so an open page keeps
  finding a fresh reading.

A failed measurement keeps the previous entry and records the error. With no
entry to fall back on, the endpoint answers 503 naming that error, and the
measurement is retried after a pause rather than on every request.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Response

from app import background

Compute = Callable[[Any, "str | None"], Awaitable[dict[str, Any]]]

TTL_S = 600.0
KEEP_WARM_S = 1800.0
REFRESH_PERIOD_S = 60.0
RETRY_AFTER_S = 60.0
STARTUP_DELAY_S = 30.0
MAX_ENTRIES = 32
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,15}-PERP$")

_caches: list["StatisticsCache"] = []
_gate: tuple[asyncio.AbstractEventLoop, asyncio.Lock] | None = None


def checked_symbol(symbol: str | None) -> str | None:
    """A market filter, or None for every market; anything else never becomes a cache key."""
    if symbol is None or not symbol.strip():
        return None
    symbol = symbol.strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise HTTPException(status_code=400, detail="symbol must look like BTC-PERP")
    return symbol


def _one_at_a_time() -> asyncio.Lock:
    """One measurement at a time across every reading, per running event loop."""
    global _gate
    loop = asyncio.get_running_loop()
    if _gate is None or _gate[0] is not loop:
        _gate = (loop, asyncio.Lock())
    return _gate[1]


def _iso(ts: float | None) -> str | None:
    return None if ts is None else datetime.fromtimestamp(ts, timezone.utc).isoformat()


@dataclass
class Entry:
    body: dict[str, Any] | None = None
    computed_at: float | None = None
    duration_s: float | None = None
    error: str | None = None
    failed_at: float | None = None
    requested_at: float = 0.0


class StatisticsCache:
    def __init__(
        self,
        name: str,
        label: str,
        compute: Compute,
        schema_version: str,
        *,
        ttl_s: float = TTL_S,
        keep_warm_s: float = KEEP_WARM_S,
        clock: Callable[[], float] = time.time,
    ):
        self.name, self.label, self.compute = name, label, compute
        self.schema_version = schema_version
        self.ttl_s, self.keep_warm_s, self.clock = ttl_s, keep_warm_s, clock
        self.entries: dict[str | None, Entry] = {}
        self._tasks: dict[str | None, asyncio.Task] = {}

    def clear(self) -> None:
        self.entries.clear()
        self._tasks.clear()

    def measuring(self, symbol: str | None) -> bool:
        task = self._tasks.get(symbol)
        return task is not None and not task.done()

    async def refresh(self, pool, symbol: str | None) -> None:
        entry = self._entry(symbol)
        async with _one_at_a_time():
            started = self.clock()
            try:
                body = await self.compute(pool, symbol)
            except Exception as exc:  # the previous entry stays; retried after RETRY_AFTER_S
                entry.error = f"{type(exc).__name__}: {exc}"[:240]
                entry.failed_at = self.clock()
                return
            entry.body, entry.computed_at = body, self.clock()
            entry.duration_s = round(entry.computed_at - started, 3)
            entry.error = entry.failed_at = None

    def ensure_measuring(self, pool, symbol: str | None) -> asyncio.Task:
        task = self._tasks.get(symbol)
        if task is None or task.done():
            task = asyncio.create_task(self.refresh(pool, symbol), name=f"{self.name}:{symbol or 'all'}")
            self._tasks[symbol] = task
        return task

    def read(self, pool, symbol: str | None) -> tuple[int, dict[str, Any]]:
        now = self.clock()
        entry = self._entry(symbol)
        entry.requested_at = now
        measuring = self.measuring(symbol)
        expired = entry.computed_at is None or now - entry.computed_at >= self.ttl_s
        if expired and not measuring and self._may_retry(entry, now):
            self.ensure_measuring(pool, symbol)
            measuring = True
        if entry.body is not None:
            return 200, {**entry.body, **self._meta(entry, now, "ready", measuring)}
        if measuring:
            return 202, {
                "schema_version": self.schema_version,
                "symbol": symbol,
                **self._meta(entry, now, "computing", measuring),
                "note": (
                    f"{self.label} for {symbol or 'every market'} has not been measured since the API "
                    "started. It is being measured now, behind this request."
                ),
            }
        raise HTTPException(
            status_code=503,
            detail=f"{self.label} could not be measured ({entry.error}); retried within {int(RETRY_AFTER_S)} s",
        )

    def respond(self, pool, symbol: str | None, response: Response) -> dict[str, Any]:
        status, body = self.read(pool, symbol)
        response.status_code = status
        return body

    def due(self, now: float | None = None) -> list[str | None]:
        """Markets asked about within the keep-warm window whose entry expires within a refresh period."""
        now = self.clock() if now is None else now
        margin = min(REFRESH_PERIOD_S, self.ttl_s / 2)
        return [
            symbol
            for symbol, entry in list(self.entries.items())
            if now - entry.requested_at <= self.keep_warm_s
            and (entry.computed_at is None or now - entry.computed_at >= self.ttl_s - margin)
            and not self.measuring(symbol)
            and self._may_retry(entry, now)
        ]

    def _meta(self, entry: Entry, now: float, status: str, measuring: bool) -> dict[str, Any]:
        age = None if entry.computed_at is None else round(now - entry.computed_at, 1)
        return {
            "status": status,
            "computed_at": _iso(entry.computed_at),
            "cache": {
                "age_s": age,
                "ttl_s": self.ttl_s,
                "stale": age is not None and age >= self.ttl_s,
                "refreshing": measuring,
                "duration_s": entry.duration_s,
                "last_error": entry.error,
            },
        }

    def _may_retry(self, entry: Entry, now: float) -> bool:
        return entry.failed_at is None or now - entry.failed_at >= RETRY_AFTER_S

    def _entry(self, symbol: str | None) -> Entry:
        entry = self.entries.get(symbol)
        if entry is None:
            idle = [key for key in self.entries if not self.measuring(key)]
            if len(self.entries) >= MAX_ENTRIES and idle:
                oldest = min(idle, key=lambda key: self.entries[key].requested_at)
                self.entries.pop(oldest)
                self._tasks.pop(oldest, None)
            entry = self.entries[symbol] = Entry()
        return entry


async def refresh_due(pool) -> list[str]:
    """Measure every due reading, one after another; return what was measured."""
    if pool is None:
        return []
    measured: list[str] = []
    for cache in list(_caches):
        for symbol in cache.due():
            await cache.ensure_measuring(pool, symbol)
            measured.append(f"{cache.name}:{symbol or 'all'}")
    return measured


def register(cache: StatisticsCache, state) -> StatisticsCache:
    """Serve ``cache`` and keep it warm with the one refresh loop shared by every reading."""
    if cache not in _caches:
        _caches.append(cache)

    async def refresh_forever() -> None:
        await asyncio.sleep(STARTUP_DELAY_S)
        while True:
            try:
                await refresh_due(state.pool)
            except Exception as exc:  # the next pass retries; requests still measure on demand
                print(f"[Statistics] refresh pass failed: {type(exc).__name__}")
            await asyncio.sleep(REFRESH_PERIOD_S)

    background.add("outcome_statistics_refresh", refresh_forever)
    return cache
