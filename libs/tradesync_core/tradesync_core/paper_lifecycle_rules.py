"""Managed paper position rules: one versioned place for every lifecycle and entry parameter.

Each holding style declares its stop, target, time expiry and trailing stop here
and nowhere else. A position freezes the rules it opened under, version included,
so a later revision never rewrites an open or closed position's plan.

The numbers are engineering hypotheses, not validated edges. Changing one is a new
``LIFECYCLE_VERSION`` with its reason in the change record, never an edit in place:
results gathered under one version are not evidence for another.

- Stop: ``stop_atr`` average true ranges from the entry fill, the range measured on
  ``atr_period`` closed ``atr_interval`` candles.
- Target: ``reward_risk`` stop distances beyond the entry fill, never closer than
  ``min_target_pct`` of it (the stop widens to keep the ratio).
- Time expiry: ``max_hold_s`` after entry.
- Trailing stop: once the exit-side price has moved ``trail_activate_r`` stop
  distances in the position's favour, the stop follows the best exit-side price seen,
  ``trail_atr`` ATRs behind it. It only ever tightens.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

LIFECYCLE_VERSION = "managed-paper-lifecycle-v2"


@dataclass(frozen=True)
class StyleRules:
    style: str
    atr_interval: str
    atr_seconds: int
    atr_period: int
    stop_atr: float
    reward_risk: float
    min_target_pct: float
    max_hold_s: int
    trail_activate_r: float
    trail_atr: float

    def to_dict(self) -> dict[str, Any]:
        return {"version": LIFECYCLE_VERSION, **asdict(self)}


RULES: dict[str, StyleRules] = {
    "scalp": StyleRules("scalp", "15m", 900, 14, 1.5, 2.0, 0.4, 3 * 3600, 1.0, 1.0),
    "intraday": StyleRules("intraday", "1h", 3600, 14, 1.5, 2.0, 0.8, 24 * 3600, 1.0, 1.25),
    "swing": StyleRules("swing", "4h", 14400, 14, 2.0, 2.0, 2.0, 7 * 86400, 1.5, 1.5),
}


@dataclass(frozen=True)
class CommonRules:
    """Gates and thresholds every paper position shares, whatever its style."""

    max_notional_usdc: float = 1000.0
    # Stop distance plus the entry cost budget, times quantity. A gap can exceed it.
    max_planned_risk_usdc: float = 50.0
    max_quote_age_s: float = 30.0
    max_quote_future_s: float = 2.0
    max_spread_bps: float = 20.0
    max_stop_share: float = 0.10
    min_reward_cost_multiple: float = 3.0
    min_net_reward_risk: float = 1.25
    # Admission budget only, when settled rows before entry average less: never profit and loss.
    planning_funding_floor_bps_hour: float = 0.125
    max_opportunity_age_s: float = 300.0
    # A longer silence between quote observations marks the position as not clean evidence.
    observation_gap_s: float = 45.0

    def to_dict(self) -> dict[str, Any]:
        return {"version": LIFECYCLE_VERSION, **asdict(self)}


COMMON = CommonRules()


def catalog() -> dict[str, Any]:
    """Every rule, in the shape the API serves and the Cockpit shows."""
    return {"version": LIFECYCLE_VERSION, "styles": {style: rules.to_dict() for style, rules in RULES.items()},
            "common": COMMON.to_dict()}
