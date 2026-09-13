"""The horizon outlook reads trend, momentum and the record behind them, and says when history is too thin."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from tradesync_core.horizon_outlook import (
    HORIZONS,
    MIN_HISTORY_DAYS,
    compose_horizons,
    horizon_read,
    lean_of,
    trend_states,
)
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


def candles(closes):
    return [{"time": T0 + i * DAY, "open": c, "high": c, "low": c, "close": c} for i, c in enumerate(closes)]


def rising(n, daily=0.002, wobble=0.01):
    return [100 * math.exp(daily * i) * (1 + wobble * math.sin(i / 3)) for i in range(n)]


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
    week = horizon_read(closes, next(h for h in HORIZONS if h.key == "1w"))
    assert week["available"] and week["trend"]["state"] == "above_rising"
    assert week["lean"] == "up" and week["record"]["same_state"]["independent_windows"] >= 8
    low, high = week["implied_range"]["low"], week["implied_range"]["high"]
    assert low < closes[-1] < high
    half_year = horizon_read(closes, next(h for h in HORIZONS if h.key == "6m"))
    assert half_year["record"]["same_state"]["independent_windows"] < 8 and half_year["lean"] == "too_few"


def test_lean_needs_enough_independent_windows() -> None:
    assert lean_of({"independent_windows": 7, "share_up": 0.9}) == "too_few"
    assert lean_of({"independent_windows": 8, "share_up": 0.6}) == "up"
    assert lean_of({"independent_windows": 8, "share_up": 0.4}) == "down"
    assert lean_of({"independent_windows": 8, "share_up": 0.5}) == "mixed"


def test_compose_groups_horizons_into_bands_and_refuses_thin_history() -> None:
    out = compose_horizons("BTC-PERP", candles(rising(400)))
    assert out["available"] and [h["key"] for h in out["horizons"]] == ["3d", "1w", "2w", "1m", "3m", "6m"]
    assert [b["band"] for b in out["bands"]] == ["lower", "medium", "higher"]
    assert out["bands"][0]["agreement"] == "up"
    assert out["history"]["days"] == 400 and "not a forecast" in out["method"]["caveat"]
    thin = compose_horizons("BTC-PERP", candles(rising(MIN_HISTORY_DAYS - 1)))
    assert not thin["available"] and "at least 120" in thin["reason"]


def test_a_day_still_trading_ends_no_record_window() -> None:
    assert forward_returns([100, 110, 121], 1, last_complete=False) == [0.10000000000000009, None, None]
    closes = rising(700)
    opened = T0 + 699 * DAY
    trading = compose_horizons("BTC-PERP", candles(closes), datetime.fromtimestamp(opened + 3600, timezone.utc))
    closed = compose_horizons("BTC-PERP", candles(closes), datetime.fromtimestamp(opened + DAY + 60, timezone.utc))
    assert trading["history"]["last_day_complete"] is False and closed["history"]["last_day_complete"] is True
    for live, done in zip(trading["horizons"], closed["horizons"]):
        assert live["record"]["all_history"]["days"] == done["record"]["all_history"]["days"] - 1, live["key"]
        assert live["momentum"] == done["momentum"] and live["trend"] == done["trend"]  # today still reads the live close


def test_horizon_labels_read_as_adjectives_before_a_noun() -> None:
    assert [h.adjective for h in HORIZONS] == ["3-day", "1-week", "2-week", "1-month", "3-month", "6-month"]
