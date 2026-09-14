"""Prefix invariance: future bars must not rewrite a historical feature state, at any horizon or bar interval."""
import math

import pytest

from tradesync_core.horizon_features import Bars, FEATURES
from tradesync_core.horizon_features.rsi import wilder_rsi
from tradesync_core.horizon_outlook import HORIZONS


@pytest.mark.parametrize('horizon', HORIZONS, ids=lambda h: h.key)
def test_every_feature_state_uses_only_its_prefix(horizon):
    total = 3200 if horizon.interval != '1d' else 1000
    cut = total - 200
    rows = []
    for i in range(total):
        close = 100 * math.exp(0.0002 * i + 0.1 * math.sin(i / 17))
        rows.append(dict(time=1600000000 + i * horizon.bar_seconds, open=close, close=close,
                         high=close * 1.01, low=close * .99, volume=1000 + 100 * math.sin(i / 7)))
    prefix = Bars.from_candles(rows[:cut], bar_seconds=horizon.bar_seconds)
    full = Bars.from_candles(rows, bar_seconds=horizon.bar_seconds)
    for feature in FEATURES:
        assert feature.states(full, horizon)[:cut] == feature.states(prefix, horizon), feature.key


def test_flat_rsi_is_neutral_not_overbought():
    assert wilder_rsi((100.0,) * 120, 14)[-1] == 50.0
    assert wilder_rsi((100.0,) * 120, 98)[-1] == 50.0
