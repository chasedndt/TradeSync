"""The venue's own 1-minute candle close as the one-hour return's anchor across a gap.

The one-hour return anchors on TradeSync's own mark-price series: the newest
15-second sample at or before t minus one hour, within a five-minute tolerance.
Redis keeps that series across a market-data restart, but nothing observes the
market while market-data, Redis or Docker is down, so every outage longer than
the tolerance leaves a hole, and for the hour after recovery the anchor band
falls inside it. On 14 September a Docker Desktop outage ended at 17:41 UTC and
the return came back at 18:42, exactly an hour later, while every other feature
and the return's own 168-point history were intact.

Hyperliquid's candles cover the hole. The anchor becomes the close of the newest
1-minute candle that closed at or before t minus one hour, within the same
tolerance: never reaching forward, never wider. A candle close is the last trade
of that minute, not the mark price, so the derivation records ``anchor_source``
and the catalog states the measured difference. An observed mark sample always
wins; a candle is consulted only when no observed sample is admissible.

Fetching is scheduled, never awaited on the snapshot path: the first snapshot
after a gap schedules one request per market and a later snapshot, seconds on,
finds the anchor. One request answers every target up to the moment it was made,
which is the whole hour a gap lasts.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Sequence

logger = logging.getLogger(__name__)

ANCHOR_SOURCE = "venue_candle_close"
CANDLE_INTERVAL = "1m"
CANDLE_MS = 60_000
RETRY_AFTER_MS = 60_000
KEEP_MS = 3 * 60 * 60 * 1000

Fetch = Callable[[str, str, int, int], Awaitable[Sequence[Mapping[str, Any]]]]


@dataclass(frozen=True)
class CandleClose:
    open_ms: int
    close_ms: int
    price: float


def _price(value: Any) -> float | None:
    """Hyperliquid sends prices as strings; only a finite positive number is a price."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def closed_candles(raw: Sequence[Mapping[str, Any]], fetched_at_ms: int) -> list[CandleClose]:
    """Well-formed 1-minute candles that had closed when fetched, oldest first.

    A candle still open at the fetch has no close yet: its last price would
    change, so it is dropped rather than kept as if final.
    """
    closes: dict[int, CandleClose] = {}
    for entry in raw or []:
        if not isinstance(entry, Mapping) or entry.get("i", CANDLE_INTERVAL) != CANDLE_INTERVAL:
            continue
        open_ms = entry.get("t")
        if not isinstance(open_ms, int) or isinstance(open_ms, bool):
            continue
        price = _price(entry.get("c"))
        close_ms = open_ms + CANDLE_MS - 1
        if price is None or close_ms >= fetched_at_ms:
            continue
        closes[open_ms] = CandleClose(open_ms, close_ms, price)
    return [closes[key] for key in sorted(closes)]


def select_candle_anchor(
    candles: Sequence[CandleClose], target_ms: int, tolerance_ms: int
) -> CandleClose | None:
    """The newest candle that closed at or before ``target_ms`` and within the tolerance."""
    best: CandleClose | None = None
    for candle in candles:
        if candle.close_ms > target_ms or candle.close_ms < target_ms - tolerance_ms:
            continue
        if best is None or candle.close_ms > best.close_ms:
            best = candle
    return best


@dataclass
class _Market:
    candles: list[CandleClose] = field(default_factory=list)
    covered_from_ms: int | None = None
    covered_to_ms: int | None = None
    last_attempt_ms: int | None = None
    task: asyncio.Task | None = None


class CandleAnchors:
    """Closed 1-minute candles per market, fetched only when a return needs one."""

    def __init__(
        self,
        fetch: Fetch | None = None,
        *,
        clock: Callable[[], int] | None = None,
        retry_after_ms: int = RETRY_AFTER_MS,
        keep_ms: int = KEEP_MS,
    ) -> None:
        self._fetch = fetch or _venue_fetch
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._retry_after_ms = retry_after_ms
        self._keep_ms = keep_ms
        self._markets: dict[str, _Market] = {}

    def anchor(self, symbol: str, target_ms: int, tolerance_ms: int) -> dict[str, Any] | None:
        """A held candle close that can stand for ``target_ms``, with its provenance."""
        market = self._markets.get(symbol)
        candle = select_candle_anchor(market.candles, target_ms, tolerance_ms) if market else None
        if candle is None:
            return None
        return {
            "ts": candle.close_ms,
            "value": candle.price,
            "source": ANCHOR_SOURCE,
            "candle_open_ms": candle.open_ms,
            "candle_interval": CANDLE_INTERVAL,
        }

    def covers(self, symbol: str, target_ms: int, tolerance_ms: int) -> bool:
        """Whether the last fetch already settled every candle that could anchor ``target_ms``."""
        market = self._markets.get(symbol)
        if market is None or market.covered_from_ms is None or market.covered_to_ms is None:
            return False
        return market.covered_from_ms <= target_ms - tolerance_ms and target_ms < market.covered_to_ms

    def request(self, symbol: str, target_ms: int, tolerance_ms: int) -> None:
        """Schedule one fetch for ``target_ms`` unless covered, in flight or tried within the retry interval.

        Needs a running event loop, which the snapshot path always has; called
        anywhere else it does nothing, so a synchronous caller never starts I/O.
        """
        if self.covers(symbol, target_ms, tolerance_ms):
            return
        market = self._markets.setdefault(symbol, _Market())
        if market.task is not None and not market.task.done():
            return
        now = self._clock()
        if market.last_attempt_ms is not None and now - market.last_attempt_ms < self._retry_after_ms:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        market.last_attempt_ms = now
        market.task = loop.create_task(self.refresh(symbol, target_ms, tolerance_ms))

    async def refresh(self, symbol: str, target_ms: int, tolerance_ms: int) -> int:
        """Fetch the candles that can anchor ``target_ms`` and every later target; returns how many closed."""
        market = self._markets.setdefault(symbol, _Market())
        start_ms = target_ms - tolerance_ms - CANDLE_MS
        fetched_at_ms = self._clock()
        market.last_attempt_ms = fetched_at_ms
        try:
            raw = await self._fetch(symbol, CANDLE_INTERVAL, start_ms, fetched_at_ms)
        except Exception as exc:  # the return stays absent and the fetch is retried later
            logger.warning(f"1m candles unavailable for {symbol} ({type(exc).__name__}); 1h return stays absent")
            return 0
        candles = closed_candles(raw, fetched_at_ms)
        if not candles:
            logger.warning(f"no closed 1m candles for {symbol}; 1h return stays absent")
            return 0
        held = {c.open_ms: c for c in market.candles if c.open_ms >= fetched_at_ms - self._keep_ms}
        held.update({c.open_ms: c for c in candles})
        market.candles = [held[key] for key in sorted(held)]
        market.covered_from_ms = start_ms + CANDLE_MS
        market.covered_to_ms = fetched_at_ms
        logger.info(
            f"1h return for {symbol}: no mark-price sample at t-1h; "
            f"{len(candles)} closed 1m venue candles held as anchors (anchor_source={ANCHOR_SOURCE})"
        )
        return len(candles)

    async def wait_idle(self) -> None:
        """Wait for every scheduled fetch to finish."""
        pending = [m.task for m in self._markets.values() if m.task is not None and not m.task.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


_provider = None


async def _venue_fetch(symbol: str, interval: str, start_ms: int, end_ms: int) -> Sequence[Mapping[str, Any]]:
    """Hyperliquid ``candleSnapshot`` through the provider, sharing the venue rate limiter."""
    global _provider
    if _provider is None:
        from .providers.hyperliquid import HyperliquidProvider

        _provider = HyperliquidProvider()
    return await _provider.fetch_candles(symbol, interval, start_ms, end_ms)


# The service-wide cache used by the snapshot path.
CANDLE_ANCHORS = CandleAnchors()
