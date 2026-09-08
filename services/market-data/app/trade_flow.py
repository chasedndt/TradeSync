"""Cumulative volume delta from Hyperliquid's taker trade stream.

CVD is the difference between aggressive buying and aggressive selling. It is
one of only a few genuinely *directional* measurements available here: most of
the catalog describes suitability — how tradeable conditions are — which can
never establish a side.

The sign convention was determined empirically against the live order book on
2026-09-08, because the venue documentation does not define it:

    side "B" -> 137 trades at/above the ask,   4 at/below the bid
    side "A" ->  29 trades at/above the ask, 137 at/below the bid

So ``B`` is an aggressive buy and ``A`` is an aggressive sell. Getting this
backwards would invert every direction the system produces, so the check is
recorded here rather than left as an assumption.

Only observed trades are counted. Nothing is inferred from candles or volume,
which is what the catalog means by "do not present candle or volume estimates
as direct CVD".
"""

from __future__ import annotations

import collections
import logging
import time
from typing import Any, Deque, Iterable, Mapping

logger = logging.getLogger(__name__)

HYPERLIQUID_WS_URL = "wss://api.hyperliquid.xyz/ws"

# CVD is reported as signed taker notional over a rolling window rather than a
# running total since startup. A cumulative figure drifts without bound and is
# not comparable across restarts, which would make its z-score meaningless.
CVD_WINDOW_MS = 5 * 60 * 1000

TAKER_BUY = "B"
TAKER_SELL = "A"


def signed_notional(trade: Mapping[str, Any]) -> float | None:
    """Return +notional for an aggressive buy, -notional for a sell.

    ``None`` when the trade is unparseable or carries an unknown side; an
    unrecognised side is skipped rather than guessed at.
    """
    side = trade.get("side")
    if side not in (TAKER_BUY, TAKER_SELL):
        return None
    try:
        price = float(trade["px"])
        size = float(trade["sz"])
    except (KeyError, TypeError, ValueError):
        return None
    if price <= 0 or size <= 0:
        return None
    notional = price * size
    return notional if side == TAKER_BUY else -notional


class TradeFlowWindow:
    """A rolling window of signed taker notional for one symbol."""

    def __init__(self, window_ms: int = CVD_WINDOW_MS):
        self.window_ms = window_ms
        self._events: Deque[tuple[int, float]] = collections.deque()
        self._total = 0.0
        self.trades_seen = 0

    def add(self, ts_ms: int, value: float) -> None:
        self._events.append((ts_ms, value))
        self._total += value
        self.trades_seen += 1

    def prune(self, now_ms: int) -> None:
        cutoff = now_ms - self.window_ms
        while self._events and self._events[0][0] < cutoff:
            _, value = self._events.popleft()
            self._total -= value
        # Floating point drift accumulates over long runs; re-total when empty.
        if not self._events:
            self._total = 0.0

    def value(self, now_ms: int) -> float:
        self.prune(now_ms)
        return round(self._total, 6)

    def __len__(self) -> int:
        return len(self._events)


class TradeFlowTracker:
    """Windowed CVD across the symbols this service follows."""

    def __init__(self, symbols: Iterable[str], window_ms: int = CVD_WINDOW_MS):
        # Keyed by the venue's own coin name, which is what the stream carries.
        self._windows: dict[str, TradeFlowWindow] = {
            symbol: TradeFlowWindow(window_ms) for symbol in symbols
        }

    def ingest(self, trades: Iterable[Mapping[str, Any]]) -> int:
        """Add a batch of trades. Returns how many were counted."""
        counted = 0
        for trade in trades:
            # The stream is external input: one malformed entry must not
            # discard the rest of the batch.
            if not isinstance(trade, Mapping):
                continue
            coin = trade.get("coin")
            window = self._windows.get(coin)
            if window is None:
                continue
            value = signed_notional(trade)
            if value is None:
                continue
            ts = trade.get("time")
            if not isinstance(ts, int) or isinstance(ts, bool):
                continue
            window.add(ts, value)
            counted += 1
        return counted

    def value(self, coin: str, now_ms: int | None = None) -> float | None:
        """Windowed CVD for one coin, or None when nothing has been observed.

        None matters: zero is a real reading meaning balanced flow, while
        "no trades observed yet" must not be presented as balance.
        """
        window = self._windows.get(coin)
        if window is None or window.trades_seen == 0:
            return None
        return window.value(now_ms if now_ms is not None else int(time.time() * 1000))

    def observed(self, coin: str) -> int:
        window = self._windows.get(coin)
        return window.trades_seen if window else 0
