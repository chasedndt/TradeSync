"""Features read on each horizon's bars for the multi-horizon outlook: one module per feature, registered here."""

from __future__ import annotations

from . import drawdown, funding, momentum, participation, premium, range_position, rsi, trend, volatility
from .base import Bars, HorizonFeature, Reading

FEATURES: tuple[HorizonFeature, ...] = (
    trend.FEATURE,
    momentum.FEATURE,
    volatility.FEATURE,
    range_position.FEATURE,
    drawdown.FEATURE,
    rsi.FEATURE,
    participation.FEATURE,
    funding.FEATURE,
    premium.FEATURE,
)

__all__ = ["Bars", "FEATURES", "HorizonFeature", "Reading"]
