"""The horizon outlook reads trend, momentum and the record behind them on each horizon's own bars, and says when history is too thin."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from tradesync_core.horizon_bars import Bars
from tradesync_core.horizon_outlook import (
    HORIZONS,
    MIN_HISTORY_BARS,
    compose_horizons,
    horizon_read,
    lean_of,
    trend_states,
)
from tradesync_core.horizon_spec import BY_KEY, INTERVAL_SECONDS, period, span
from tradesync_core.horizon_stats import (
    daily_volatility,
    forward_returns,
    independent_windows,
    moving_averages,
    quantile,
    summarize,
)

DAY = 86400
T0 = 1_700_000_000
DAILY = tuple(h for h in HORIZONS if h.interval == "1d")
SHORT = tuple(h for h in HORIZONS if h.band == "short")


def candles(closes, step=DAY):
    return [{"time": T0 + i * step, "open": c, "high": c, "low": c, "close": c} for i, c in enumerate(closes)]


def rising(n, per_bar=0.002, wobble=0.01):
    return [100 * math.exp(per_bar * i) * (1 + wobble * math.sin(i / 3)) for i in range(n)]


def bars(closes, interval="1d", now_s=None):
    return Bars.from_candles(candles(closes, INTERVAL_SECONDS[interval]), now_s, INTERVAL_SECONDS[interval])


def test_forward_returns_stop_where_the_window_runs_out() -> None:
    assert forward_returns([100, 110, 121], 1) == [0.10000000000000009, 0.10000000000000009, None]
    assert forward_returns([100, 110], 5) == [None, None]


def test_independent_windows_do_not_overlap() -> None:
    assert independent_windows([0, 1, 2, 10, 11, 25], 10) == 3
    assert independent_windows([], 10) == 0


def test_quantiles_moving_averages_and_volatility() -> None:
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert moving_averages([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    assert daily_volatility([100.0] * 40, 30) == 0.0
    assert daily_volatility([100.0, 101.0], 30) is None


def test_summary_reports_share_up_bands_and_independence() -> None:
    s = summarize([0.1, -0.05, 0.2, 0.3], [0, 1, 2, 3], 2)
    assert s["days"] == 4 and s["independent_windows"] == 2 and s["share_up"] == 0.75
    assert s["median_pct"] == 15.0 and s["p10_pct"] < s["p25_pct"] < s["p75_pct"] < s["p90_pct"]
    assert summarize([], [], 2)["share_up"] is None


def test_trend_state_of_a_steady_rise() -> None:
    states, _ = trend_states(rising(120, wobble=0.0), 20)
    assert states[:24] == [None] * 24 and set(states[25:]) == {"above_rising"}


def test_a_long_steady_rise_leans_up_on_short_horizons_and_is_too_thin_for_six_months() -> None:
    closes = rising(1100)
    week = horizon_read(closes, BY_KEY["1w"])
    assert week["available"] and week["trend"]["state"] == "above_rising" and week["trend"]["ma_label"] == "20-day"
    assert week["lean"] == "up" and week["record"]["same_state"]["independent_windows"] >= 8
    low, high = week["implied_range"]["low"], week["implied_range"]["high"]
    assert low < closes[-1] < high
    half_year = horizon_read(closes, BY_KEY["6m"])
    assert half_year["record"]["same_state"]["independent_windows"] < 8 and half_year["lean"] == "too_few"


def test_lean_needs_enough_independent_windows() -> None:
    assert lean_of({"independent_windows": 7, "share_up": 0.9}) == "too_few"
    assert lean_of({"independent_windows": 8, "share_up": 0.6}) == "up"
    assert lean_of({"independent_windows": 8, "share_up": 0.4}) == "down"
    assert lean_of({"independent_windows": 8, "share_up": 0.5}) == "mixed"


def test_compose_groups_daily_horizons_into_bands_and_refuses_thin_history() -> None:
    out = compose_horizons("BTC-PERP", {"1d": bars(rising(400))}, horizons=DAILY)
    assert out["available"] and [h["key"] for h in out["horizons"]] == ["3d", "1w", "2w", "1m", "3m", "6m"]
    assert [b["band"] for b in out["bands"]] == ["lower", "medium", "higher"]
    assert out["bands"][0]["agreement"] == "up"
    assert out["history"]["1d"]["bars"] == 400 and "not a forecast" in out["method"]["caveat"]
    thin = compose_horizons("BTC-PERP", {"1d": bars(rising(MIN_HISTORY_BARS - 1))}, horizons=DAILY)
    assert not thin["available"] and "at least 120" in thin["reason"]


def test_short_term_horizons_read_15_minute_and_hourly_bars() -> None:
    short = {"15m": bars(rising(900, per_bar=0.0004), "15m"), "1h": bars(rising(900, per_bar=0.001), "1h")}
    out = compose_horizons("BTC-PERP", short, horizons=SHORT)
    reads = {r["key"]: r for r in out["horizons"]}
    assert [r["key"] for r in out["horizons"]] == ["1h", "4h", "8h", "1d"] and all(r["available"] for r in reads.values())
    assert reads["1h"]["interval"] == "15m" and reads["1h"]["trend"]["ma_label"] == "5-hour"
    assert reads["1d"]["interval"] == "1h" and reads["1d"]["trend"]["ma_label"] == "2-day"
    assert out["bands"] == [{"band": "short", "label": "Short term", "horizons": ["1h", "4h", "8h", "1d"],
                             "leans": {k: r["lean"] for k, r in reads.items()}, "agreement": out["bands"][0]["agreement"]}]
    assert out["last_close"] == short["15m"].closes[-1]


def test_a_horizon_whose_bars_are_missing_says_so() -> None:
    out = compose_horizons("BTC-PERP", {"1d": bars(rising(400))})
    missing = next(r for r in out["horizons"] if r["key"] == "1h")
    assert not missing["available"] and "15-minute candles" in missing["reason"]


def test_a_bar_still_trading_ends_no_record_window() -> None:
    assert forward_returns([100, 110, 121], 1, last_complete=False) == [0.10000000000000009, None, None]
    closes = rising(700)
    opened = T0 + 699 * DAY
    trading = compose_horizons("BTC-PERP", {"1d": bars(closes, now_s=opened + 3600)}, datetime.fromtimestamp(opened + 3600, timezone.utc), DAILY)
    closed = compose_horizons("BTC-PERP", {"1d": bars(closes, now_s=opened + DAY + 60)}, datetime.fromtimestamp(opened + DAY + 60, timezone.utc), DAILY)
    assert trading["history"]["1d"]["last_bar_complete"] is False and closed["history"]["1d"]["last_bar_complete"] is True
    for live, done in zip(trading["horizons"], closed["horizons"]):
        assert live["record"]["all_history"]["days"] == done["record"]["all_history"]["days"] - 1, live["key"]
        assert live["momentum"] == done["momentum"] and live["trend"] == done["trend"]  # the latest bar still reads its live close


def test_labels_spans_and_periods_read_as_words() -> None:
    assert [h.adjective for h in HORIZONS] == ["1-hour", "4-hour", "8-hour", "1-day", "3-day", "1-week", "2-week", "1-month", "3-month", "6-month"]
    assert span(20, 900) == "5-hour" and span(3, 900) == "45-minute" and span(20, 86400) == "20-day"
    assert period(366, 86400) == "year" and period(2880, 900) == "30 days" and period(96, 900) == "day" and period(8, 900) == "2 hours"
