"""Features read on daily candles for the multi-horizon outlook: one module per feature, registered here."""

from __future__ import annotations

from . import drawdown, momentum, participation, range_position, rsi, trend, volatility
from .base import Bars, HorizonFeature, Reading

FEATURES: tuple[HorizonFeature, ...] = (
    trend.FEATURE,
    momentum.FEATURE,
    volatility.FEATURE,
    range_position.FEATURE,
    drawdown.FEATURE,
    rsi.FEATURE,
    participation.FEATURE,
)

__all__ = ["Bars", "FEATURES", "HorizonFeature", "Reading"]
