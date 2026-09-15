import asyncio

from app.candle_anchor import (
    ANCHOR_SOURCE,
    CANDLE_MS,
    CandleAnchors,
    CandleClose,
    closed_candles,
    select_candle_anchor,
)

T0 = 1_789_430_400_000  # a whole minute
TOLERANCE_MS = 300_000


def candle(open_ms: int, close: float, interval: str = "1m") -> dict:
    """The shape Hyperliquid's candleSnapshot returns, prices as strings."""
    price = str(close)
    return {"t": open_ms, "T": open_ms + CANDLE_MS - 1, "s": "BTC", "i": interval,
            "o": price, "h": price, "l": price, "c": price, "v": "1.0", "n": 3}


def minutes(start_ms: int, end_ms: int, close: float = 100.0) -> list[dict]:
    first = (start_ms // CANDLE_MS) * CANDLE_MS
    return [candle(t, close) for t in range(first, end_ms, CANDLE_MS)]


class Clock:
    def __init__(self, now_ms: int) -> None:
        self.now_ms = now_ms

    def __call__(self) -> int:
        return self.now_ms


def test_only_closed_well_formed_one_minute_candles_are_kept():
    raw = [
        candle(T0, 101.0),  # still open when fetched
        candle(T0 - CANDLE_MS, 100.0),
        candle(T0 - 2 * CANDLE_MS, 99.0),
        candle(T0 - 3 * CANDLE_MS, 98.0, interval="5m"),
        {"t": T0 - 4 * CANDLE_MS, "c": "abc"},
        {"t": True, "c": "97"},
        {"t": T0 - 5 * CANDLE_MS, "c": "0"},
        "not-a-candle",
    ]
    kept = closed_candles(raw, fetched_at_ms=T0 + 30_000)
    assert [c.open_ms for c in kept] == [T0 - 2 * CANDLE_MS, T0 - CANDLE_MS]
    assert kept[-1] == CandleClose(T0 - CANDLE_MS, T0 - 1, 100.0)


def test_the_anchor_is_the_newest_candle_closed_at_or_before_the_target():
    candles = [
        CandleClose(T0 - 2 * CANDLE_MS, T0 - CANDLE_MS - 1, 99.0),
        CandleClose(T0 - CANDLE_MS, T0 - 1, 100.0),
        CandleClose(T0, T0 + CANDLE_MS - 1, 101.0),
    ]
    # The minute that opened at T0 closes after a target inside it: never used.
    assert select_candle_anchor(candles, T0 + 30_000, TOLERANCE_MS).price == 100.0
    assert select_candle_anchor(candles, T0 - 1, TOLERANCE_MS).price == 100.0
    assert select_candle_anchor(candles, T0 - 2, TOLERANCE_MS).price == 99.0


def test_a_candle_stranded_beyond_the_tolerance_is_not_an_anchor():
    candles = [CandleClose(T0 - 10 * CANDLE_MS, T0 - 9 * CANDLE_MS - 1, 98.0)]
    assert select_candle_anchor(candles, T0, TOLERANCE_MS) is None


def test_one_fetch_answers_every_target_up_to_the_moment_it_was_made():
    clock = Clock(T0)
    calls = []

    async def fetch(symbol, interval, start_ms, end_ms):
        calls.append((symbol, interval, start_ms, end_ms))
        return minutes(start_ms, end_ms)

    anchors = CandleAnchors(fetch, clock=clock)
    target = T0 - 3_600_000

    async def run():
        assert anchors.anchor("BTC-PERP", target, TOLERANCE_MS) is None
        anchors.request("BTC-PERP", target, TOLERANCE_MS)
        anchors.request("BTC-PERP", target, TOLERANCE_MS)  # in flight: no second fetch
        await anchors.wait_idle()
        held = anchors.anchor("BTC-PERP", target, TOLERANCE_MS)
        assert held["source"] == ANCHOR_SOURCE and target - TOLERANCE_MS <= held["ts"] <= target
        assert anchors.covers("BTC-PERP", T0 - 1, TOLERANCE_MS)
        assert not anchors.covers("BTC-PERP", T0 + 1, TOLERANCE_MS)
        clock.now_ms += 10 * 60_000
        anchors.request("BTC-PERP", T0 - CANDLE_MS, TOLERANCE_MS)  # still covered
        await anchors.wait_idle()

    asyncio.run(run())
    assert calls == [("BTC-PERP", "1m", target - TOLERANCE_MS - CANDLE_MS, T0)]


def test_a_failed_or_empty_fetch_leaves_no_anchor_and_is_retried_only_after_the_interval():
    clock = Clock(T0)
    answers = [RuntimeError("venue down"), []]
    calls = []

    async def fetch(symbol, interval, start_ms, end_ms):
        calls.append(end_ms)
        answer = answers.pop(0) if answers else minutes(start_ms, end_ms)
        if isinstance(answer, Exception):
            raise answer
        return answer

    anchors = CandleAnchors(fetch, clock=clock, retry_after_ms=60_000)
    target = T0 - 3_600_000

    async def attempt():
        anchors.request("BTC-PERP", target, TOLERANCE_MS)
        await anchors.wait_idle()
        return anchors.anchor("BTC-PERP", target, TOLERANCE_MS)

    async def run():
        assert await attempt() is None  # raised
        clock.now_ms += 30_000
        assert await attempt() is None  # within the retry interval: not tried
        clock.now_ms += 30_000
        assert await attempt() is None  # answered, but with nothing
        clock.now_ms += 60_000
        return await attempt()

    held = asyncio.run(run())
    assert len(calls) == 3
    assert held is not None and held["ts"] <= target


def test_without_a_running_loop_a_request_starts_nothing():
    calls = []

    async def fetch(*args):
        calls.append(args)
        return []

    CandleAnchors(fetch, clock=Clock(T0)).request("BTC-PERP", T0 - 3_600_000, TOLERANCE_MS)
    assert calls == []


def test_candles_older_than_the_keep_window_are_dropped_on_the_next_fetch():
    clock = Clock(T0)

    async def fetch(symbol, interval, start_ms, end_ms):
        return minutes(start_ms, end_ms)

    anchors = CandleAnchors(fetch, clock=clock, keep_ms=2 * 3_600_000)
    old_target = T0 - 3_600_000
    asyncio.run(anchors.refresh("BTC-PERP", old_target, TOLERANCE_MS))
    clock.now_ms += 3 * 3_600_000
    asyncio.run(anchors.refresh("BTC-PERP", clock.now_ms - 3_600_000, TOLERANCE_MS))
    assert anchors.anchor("BTC-PERP", old_target, TOLERANCE_MS) is None
    assert anchors.anchor("BTC-PERP", clock.now_ms - 3_600_000, TOLERANCE_MS) is not None
