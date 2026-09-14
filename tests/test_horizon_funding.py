"""Funding and premium are aligned to each horizon's bars, ranked against their own range, and carry records like any feature."""

from __future__ import annotations

import math

from tradesync_core.horizon_bars import Bars, align_hourly, with_funding
from tradesync_core.horizon_evaluation import evaluate_horizon
from tradesync_core.horizon_features import FEATURES
from tradesync_core.horizon_spec import BY_KEY, INTERVAL_SECONDS

T0 = 1_700_000_000 // 86400 * 86400
HOUR = 3600


def feature(key):
    return next(f for f in FEATURES if f.key == key)


def candles(n, step, drift=0.0005):
    return [{"time": T0 + i * step, "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1000.0}
            for i, c in enumerate(100 * math.exp(drift * i) for i in range(n))]


def test_short_bars_take_the_rate_in_force_at_their_close_and_days_take_the_mean() -> None:
    rows = [[T0, 0.1, 1.0], [T0 + HOUR, 0.2, 2.0], [T0 + 2 * HOUR, 0.3, 3.0]]
    quarters = [T0 + i * 900 for i in range(8)]
    assert align_hourly(quarters, 900, rows, 1) == (0.1, 0.1, 0.1, 0.2, 0.2, 0.2, 0.2, 0.3)
    late = [T0 + 6 * HOUR]  # closes 2h15m after the last row: too old to carry forward
    assert align_hourly(late, 900, rows, 1) == (None,)
    day_rows = [[T0 + h * HOUR, float(h), 0.0] for h in range(24)]
    assert align_hourly([T0], 86400, day_rows, 1) == (11.5,)
    assert align_hourly([T0], 86400, day_rows[:11], 1) == (None,)  # fewer than twelve hours


def test_bars_without_funding_rows_keep_no_extras_and_read_as_unavailable() -> None:
    plain = Bars.from_candles(candles(400, 86400))
    assert with_funding(plain, []) is plain and plain.extra("funding_rate") == (None,) * 400
    reading = feature("funding").read(plain, BY_KEY["1m"])
    assert reading.state is None and "funding history" in reading.text
    assert feature("premium").overlays(plain, BY_KEY["1m"], 0) == []


def test_funding_ranks_against_its_range_and_says_who_pays() -> None:
    hourly = BY_KEY["8h"]
    n = 900
    rows = [[T0 + i * HOUR, (i / n) * 5e-5, -1e-4 + (i / n) * 2e-4] for i in range(n + 1)]
    bars = with_funding(Bars.from_candles(candles(n, INTERVAL_SECONDS["1h"]), bar_seconds=INTERVAL_SECONDS["1h"]), rows)
    funding = feature("funding").read(bars, hourly)
    assert funding.state == "elevated" and "longs pay shorts" in funding.text and "of the past 30 days" in funding.text
    premium = feature("premium").read(bars, hourly)
    assert premium.state == "rich" and "above the oracle" in premium.text
    lower = feature("funding").overlays(bars, hourly, n - 100)
    assert lower[0]["pane"] == "lower" and lower[0]["guides"] == [0]


def test_evaluation_gives_funding_and_premium_a_record_and_a_weight() -> None:
    n = 1200
    rows = [[T0 + i * HOUR, 1e-5 * math.sin(i / 50), 1e-4 * math.cos(i / 70)] for i in range(n + 2)]
    bars = with_funding(Bars.from_candles(candles(n, INTERVAL_SECONDS["1h"], drift=0.0001), bar_seconds=INTERVAL_SECONDS["1h"]), rows)
    out = evaluate_horizon(bars, BY_KEY["8h"])
    by_key = {f["key"]: f for f in out["features"]}
    assert {"funding", "premium"} <= set(by_key)
    assert by_key["funding"]["state"] in ("elevated", "depressed", "normal") and by_key["funding"]["record"]["days"] > 0
    assert 0.0 <= by_key["premium"]["weight"] <= 1.0
