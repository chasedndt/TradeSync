"""The one-hour return across a hole in the mark-price series: the venue candle stands in, and says so."""

import asyncio

import pytest

from app.candle_anchor import CANDLE_MS, CandleAnchors
from app.return_1h import (
    RETURN_1H_ANCHOR_TOLERANCE_MS,
    attach_derived_features,
    derive_return_1h_pct,
)

HOUR_MS = 60 * 60 * 1000
NOW = 1767297600000  # a whole minute


def _snapshot(ts: int, mark: float) -> dict:
    return {"venue": "hyperliquid", "symbol": "BTC-PERP", "ts": ts, "price": {"mark_price_usd": mark}}


def _venue(close: float, calls: list):
    async def fetch(symbol, interval, start_ms, end_ms):
        calls.append((start_ms, end_ms))
        first = (start_ms // CANDLE_MS) * CANDLE_MS
        return [{"t": t, "i": "1m", "c": str(close)} for t in range(first, end_ms, CANDLE_MS)]

    return fetch


class _Clock:
    def __init__(self, now_ms: int) -> None:
        self.now_ms = now_ms

    def __call__(self) -> int:
        return self.now_ms


def _held(close: float) -> CandleAnchors:
    anchors = CandleAnchors(_venue(close, []), clock=lambda: NOW)
    asyncio.run(anchors.refresh("BTC-PERP", NOW - HOUR_MS, RETURN_1H_ANCHOR_TOLERANCE_MS))
    return anchors


def test_an_observed_mark_anchor_is_used_even_when_a_candle_is_held():
    history = [{"ts": NOW - HOUR_MS, "value": 100.0}]
    observation = derive_return_1h_pct(_snapshot(NOW, 101.0), history, _held(50.0))
    assert observation["value"] == pytest.approx(1.0)
    assert observation["comparator"]["anchor_source"] == "observed_mark_price"
    assert "anchor_candle_open_ms" not in observation["comparator"]
    assert observation["source_event_id"].startswith("return1h:hyperliquid:BTC-PERP:")


def test_without_an_observed_anchor_the_candle_close_stands_in_and_the_comparator_says_so():
    observation = derive_return_1h_pct(_snapshot(NOW, 101.0), [], _held(100.0))
    assert observation["value"] == pytest.approx(1.0)
    comparator = observation["comparator"]
    assert comparator["anchor_source"] == "venue_candle_close"
    assert comparator["anchor_candle_interval"] == "1m"
    # Still at or before t minus one hour, and no further back than the tolerance.
    assert comparator["anchor_ts_ms"] <= NOW - HOUR_MS
    assert HOUR_MS <= comparator["anchor_lag_ms"] <= HOUR_MS + RETURN_1H_ANCHOR_TOLERANCE_MS
    assert comparator["anchor_candle_open_ms"] + CANDLE_MS - 1 == comparator["anchor_ts_ms"]
    assert observation["source_event_id"].startswith("return1h-candle:hyperliquid:BTC-PERP:")


def test_an_observed_anchor_beyond_the_tolerance_does_not_block_the_candle():
    stranded = [{"ts": NOW - HOUR_MS - 10 * 60_000, "value": 90.0}]
    observation = derive_return_1h_pct(_snapshot(NOW, 101.0), stranded, _held(100.0))
    assert observation["comparator"]["anchor_source"] == "venue_candle_close"
    assert observation["comparator"]["anchor_value"] == 100.0


def test_without_candle_anchors_the_derivation_stays_on_observed_marks_only():
    assert derive_return_1h_pct(_snapshot(NOW, 101.0), [], None) is None
    assert "derived" not in attach_derived_features(_snapshot(NOW, 101.0), [], None)


def test_restart_after_an_outage_gives_a_return_within_seconds_and_hands_back_to_observed_marks():
    """market-data comes back after five hours down. Its mark-price series has
    nothing between t-5h and the restart, so for the next hour no observed
    sample can anchor t-1h. Snapshots arrive every eight seconds."""
    restart = NOW
    clock = _Clock(restart)
    calls: list = []
    anchors = CandleAnchors(_venue(100.0, calls), clock=clock)
    history = [{"ts": restart - 5 * HOUR_MS - i * 15_000, "value": 90.0} for i in range(20)]

    async def service() -> list[tuple[int, str | None]]:
        seen = []
        t = restart
        while t <= restart + HOUR_MS + 5 * 60_000:
            clock.now_ms = t
            history.append({"ts": t, "value": 101.0})
            snapshot = attach_derived_features(_snapshot(t, 101.0), history, anchors)
            derived = snapshot.get("derived", {}).get("return_1h_pct")
            seen.append((t, derived["comparator"]["anchor_source"] if derived else None))
            await anchors.wait_idle()
            t += 8_000
        return seen

    seen = asyncio.run(service())
    first_value_at = next(t for t, source in seen if source is not None)
    # The first snapshot schedules the fetch; the next one, eight seconds on, has the return.
    assert seen[0] == (restart, None)
    assert first_value_at - restart <= 2 * 60_000
    assert all(source is not None for t, source in seen if t >= first_value_at)
    assert {source for t, source in seen if first_value_at <= t < restart + HOUR_MS} == {"venue_candle_close"}
    assert {source for t, source in seen if t >= restart + HOUR_MS} == {"observed_mark_price"}
    assert len(calls) == 1
