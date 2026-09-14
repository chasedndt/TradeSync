"""Name what happened to a paper call over one horizon, net of trading costs.

A hit rate treats a 0.01% win and a 2% win as the same event, and it ignores
that every round trip pays fees, spread and slippage before it earns anything.
This module classifies each measured horizon against an explicit cost, so the
record reads the way a trader would describe the trade:

``clean_win``           finished beyond costs in the called direction, and the
                        worst adverse excursion was no larger than the net win.
``win_after_drawdown``  finished beyond costs, but only after an adverse
                        excursion larger than the net win it produced.
``reversed``            was beyond costs in favour at some point, then finished
                        beyond costs against the call.
``wrong_direction``     never moved beyond costs in favour, and finished beyond
                        costs against the call.
``no_follow_through``   finished inside the cost band either way: the move did
                        not pay for the round trip.

Pure: no clock, database or network. Inputs are the stored outcome columns, in
percent of the entry price. Excursions are magnitudes relative to the side that
was called, as ``tradesync_core.outcomes`` measures them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# The venue's base taker fee both ways (2 x 0.045%) plus 2 bps of spread and
# 1 bp of slippage: the same total the skill gate states. Callers may override.
DEFAULT_ROUND_TRIP_COST_PCT = 0.12
# "A drawdown larger than 1x the realised win" marks a win as hard-won.
DEFAULT_DRAWDOWN_MULTIPLE = 1.0

CLEAN_WIN = "clean_win"
WIN_AFTER_DRAWDOWN = "win_after_drawdown"
WRONG_DIRECTION = "wrong_direction"
REVERSED = "reversed"
NO_FOLLOW_THROUGH = "no_follow_through"

CLASSIFICATIONS = (
    CLEAN_WIN,
    WIN_AFTER_DRAWDOWN,
    WRONG_DIRECTION,
    REVERSED,
    NO_FOLLOW_THROUGH,
)
WINS = frozenset({CLEAN_WIN, WIN_AFTER_DRAWDOWN})
FAILURES = frozenset({WRONG_DIRECTION, REVERSED, NO_FOLLOW_THROUGH})


class ClassificationError(ValueError):
    """Raised for malformed input, never for an ordinary losing call."""


@dataclass(frozen=True)
class OutcomeClass:
    """One horizon's result after costs, with the label that describes it."""

    classification: str
    signed_return_pct: float
    net_return_pct: float
    cost_pct: float
    max_favourable_pct: float
    max_adverse_pct: float

    @property
    def won(self) -> bool:
        return self.classification in WINS

    @property
    def decided(self) -> bool:
        """The price left the cost band, so the call was clearly right or wrong."""
        return self.classification != NO_FOLLOW_THROUGH

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "signed_return_pct": self.signed_return_pct,
            "net_return_pct": self.net_return_pct,
            "cost_pct": self.cost_pct,
            "max_favourable_pct": self.max_favourable_pct,
            "max_adverse_pct": self.max_adverse_pct,
            "won": self.won,
            "decided": self.decided,
        }


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ClassificationError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ClassificationError(f"{field} must be finite")
    return number


def _excursion(value: Any, field: str) -> float:
    """An excursion magnitude. Missing means none was recorded, read as zero."""
    if value is None:
        return 0.0
    return max(0.0, _finite(value, field))


def classify_outcome(
    signed_return_pct: Any,
    max_favourable_pct: Any,
    max_adverse_pct: Any,
    cost_pct: Any = DEFAULT_ROUND_TRIP_COST_PCT,
    drawdown_multiple: Any = DEFAULT_DRAWDOWN_MULTIPLE,
) -> OutcomeClass:
    """Classify one measured horizon against a round-trip cost in percent."""

    signed = _finite(signed_return_pct, "signed_return_pct")
    cost = _finite(cost_pct, "cost_pct")
    if cost < 0:
        raise ClassificationError("cost_pct cannot be negative")
    multiple = _finite(drawdown_multiple, "drawdown_multiple")
    if multiple <= 0:
        raise ClassificationError("drawdown_multiple must be positive")
    favourable = _excursion(max_favourable_pct, "max_favourable_pct")
    adverse = _excursion(max_adverse_pct, "max_adverse_pct")

    net = signed - cost
    if signed > cost:
        label = WIN_AFTER_DRAWDOWN if adverse > multiple * net else CLEAN_WIN
    elif signed < -cost:
        label = REVERSED if favourable > cost else WRONG_DIRECTION
    else:
        label = NO_FOLLOW_THROUGH

    return OutcomeClass(
        classification=label,
        signed_return_pct=round(signed, 6),
        net_return_pct=round(net, 6),
        cost_pct=cost,
        max_favourable_pct=round(favourable, 6),
        max_adverse_pct=round(adverse, 6),
    )
