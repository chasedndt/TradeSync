"""Horizon features read daily bars, carry a record for today's state, and describe how they are drawn."""

from __future__ import annotations

import math
from dataclasses import replace

from tradesync_core.horizon_chart import chart_payload, projection
from tradesync_core.horizon_evaluation import evaluate_all, evaluate_horizon, tally_sentence
from tradesync_core.horizon_features import FEATURES, Bars
from tradesync_core.horizon_features.rsi import wilder_rsi
from tradesync_core.horizon_outlook import HORIZONS, horizon_read
from tradesync_core.horizon_stats import rolling_extreme

DAY = 86400
T0 = 1_600_000_000
BY_KEY = {h.key: h for h in HORIZONS}


def bars(n=900, daily=0.002, wobble=0.03, volume=1000.0):
    closes = [100 * math.exp(daily * i) * (1 + wobble * math.sin(i / 5)) for i in range(n)]
    candles = [{"time": T0 + i * DAY, "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": volume * (1 + 0.1 * math.sin(i / 7))}
               for i, c in enumerate(closes)]
    return Bars.from_candles(candles)


def test_rolling_extremes_match_a_plain_scan() -> None:
    values = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]
    assert rolling_extreme(values, 3) == [None, None, 4.0, 4.0, 5.0, 9.0, 9.0, 9.0]
    assert rolling_extreme(values, 3, largest=False) == [None, None, 1.0, 1.0, 1.0, 1.0, 2.0, 2.0]


def test_wilder_rsi_of_a_steady_rise_is_high_and_of_a_fall_is_low() -> None:
    assert wilder_rsi(tuple(float(i) for i in range(40)), 14)[-1] == 100.0
    assert wilder_rsi(tuple(float(40 - i) for i in range(40)), 14)[-1] == 0.0


def test_every_feature_reads_a_rising_market_and_draws_something() -> None:
    b, month = bars(), BY_KEY["1m"]
    readings = {f.key: f.read(b, month) for f in FEATURES}
    assert readings["trend"].state == "above_rising" and readings["trend"].lean == "up"
    assert readings["momentum"].lean == "up"
    assert readings["range"].state in ("near_high", "middle") and readings["drawdown"].state in ("near_high", "pullback")
    assert readings["volatility"].state in ("compressed", "normal", "elevated") and readings["volatility"].lean == "context"
    assert readings["participation"].state in ("rising", "steady", "fading")
    for f in FEATURES:
        assert len(f.states(b, month)) == len(b)
        assert f.overlays(b, month, len(b) - 100), f.key


def test_participation_ignores_days_without_volume() -> None:
    b = bars(volume=0.0)
    assert FEATURES[-1].read(b, BY_KEY["1m"]).state is None


def test_evaluation_gives_each_feature_a_record_and_a_tally() -> None:
    b = bars()
    out = evaluate_horizon(b, BY_KEY["1w"])
    assert [f["key"] for f in out["features"]] == [f.key for f in FEATURES]
    assert sum(out["record_tally"].values()) == len(FEATURES)
    trend = out["features"][0]
    assert trend["record"]["days"] > 0 and trend["record_lean"] == "up"
    assert out["summary"].startswith("Over 1 week, the record behind today's reading leans higher for Trend")
    assert set(evaluate_all(b)) == {h.key for h in HORIZONS}


def test_tally_sentence_names_thin_features() -> None:
    features = [{"label": "Trend", "record_lean": "up"}, {"label": "RSI", "record_lean": "too_few"},
                {"label": "Participation", "record_lean": "unavailable"}]
    assert tally_sentence(BY_KEY["6m"], features) == (
        "Over 6 months, the record behind today's reading leans higher for Trend; is too thin to judge for RSI and Participation."
    )


def test_chart_payload_windows_candles_and_spreads_an_ordered_cone() -> None:
    b, week = bars(), BY_KEY["1w"]
    read = horizon_read(b.closes, week)
    payload = chart_payload(b, week, read)
    assert len(payload["candles"]) == 180 and set(payload["overlays"]) == {f.key for f in FEATURES}
    cone = payload["projection"]
    ends = {line["quantile"]: line["points"][-1] for line in cone["lines"]}
    assert ends["p10_pct"][1] <= ends["median_pct"][1] <= ends["p90_pct"][1]
    assert ends["median_pct"][0] == b.times[-1] + 7 * DAY and cone["lines"][0]["points"][0][1] == round(b.closes[-1], 8)
    assert projection(b, week, {"record": {}})["lines"] == []


def test_a_day_still_trading_is_marked_and_its_volume_waits_for_the_close() -> None:
    bar = [{"time": T0, "close": 1.0}]
    assert Bars.from_candles(bar, now_s=T0 + DAY - 1).last_partial
    assert not Bars.from_candles(bar, now_s=T0 + DAY).last_partial and not Bars.from_candles(bar).last_partial
    closed, month = bars(), BY_KEY["1m"]
    trading = replace(closed, volumes=closed.volumes[:-1] + (1.0,), last_partial=True)
    participation = next(f for f in FEATURES if f.key == "participation")
    assert participation.ratios(trading, month)[-1] == participation.ratios(closed, month)[-2]
    assert "closed days" in participation.read(trading, month).text
    week = evaluate_horizon(closed, BY_KEY["1w"])["features"][0]["record"]["days"]
    assert evaluate_horizon(trading, BY_KEY["1w"])["features"][0]["record"]["days"] in (week, week - 1)
