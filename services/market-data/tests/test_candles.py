import pytest

from app.candles import (
    MAX_LIMIT,
    SUPPORTED_INTERVALS,
    CandleRequestError,
    normalize_candles,
    resolve_window,
)

NOW_MS = 1_788_830_000_000


def _raw(t, o="100", h="110", l="90", c="105", v="12.5"):
    return {"t": t, "T": t + 1, "s": "BTC", "i": "15m", "o": o, "h": h, "l": l, "c": c, "v": v}


class TestResolveWindow:
    def test_window_spans_limit_candles_of_the_interval(self):
        interval, limit, start, end = resolve_window("15m", 4, now_ms=NOW_MS)
        assert interval == "15m"
        assert limit == 4
        assert end == NOW_MS
        assert end - start == SUPPORTED_INTERVALS["15m"] * 4

    def test_limit_is_capped(self):
        _, limit, _, _ = resolve_window("1m", 99_999, now_ms=NOW_MS)
        assert limit == MAX_LIMIT

    def test_unsupported_interval_is_rejected_with_the_valid_set(self):
        with pytest.raises(CandleRequestError) as exc:
            resolve_window("7s", 10, now_ms=NOW_MS)
        assert "15m" in str(exc.value)

    def test_non_positive_limit_is_rejected(self):
        with pytest.raises(CandleRequestError):
            resolve_window("15m", 0, now_ms=NOW_MS)


class TestNormalizeCandles:
    def test_strings_become_numbers_and_ms_becomes_seconds(self):
        [candle] = normalize_candles([_raw(1_788_742_800_000)])
        assert candle["time"] == 1_788_742_800
        assert candle["open"] == 100.0
        assert candle["high"] == 110.0
        assert candle["low"] == 90.0
        assert candle["close"] == 105.0
        assert candle["volume"] == 12.5

    def test_candles_are_sorted_by_time(self):
        out = normalize_candles([_raw(3000), _raw(1000), _raw(2000)])
        assert [c["time"] for c in out] == [1, 2, 3]

    def test_duplicate_timestamps_keep_the_last_value(self):
        out = normalize_candles([_raw(1000, c="105"), _raw(1000, c="999")])
        assert len(out) == 1
        assert out[0]["close"] == 999.0

    def test_entries_missing_a_price_are_dropped_not_defaulted(self):
        out = normalize_candles([_raw(1000, c=None), _raw(2000)])
        assert [c["time"] for c in out] == [2]

    def test_missing_volume_becomes_zero_but_prices_never_do(self):
        [candle] = normalize_candles([_raw(1000, v=None)])
        assert candle["volume"] == 0.0
        assert candle["close"] == 105.0

    def test_malformed_entries_are_ignored(self):
        out = normalize_candles(["nope", {"t": "not-int"}, {}, _raw(5000)])
        assert [c["time"] for c in out] == [5]

    def test_empty_input_is_an_empty_chart_not_an_error(self):
        assert normalize_candles([]) == []
