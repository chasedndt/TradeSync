"""Measure what actually happened after a paper opportunity was recorded.

Without this the system produces opinions and never learns whether any of them
were worth anything. Every tuning decision before an outcome loop exists is
guesswork.

Deliberately conservative:

- Nothing is measured until the full horizon has elapsed. A partially observed
  window is reported as pending, never as a short-horizon result.
- A gap in candle coverage is reported, not interpolated over.
- The entry is the first candle *at or after* the opportunity timestamp, so the
  measurement can never use a price that existed before the decision.

Nothing here implies a trade was placed. These are paper measurements of what
the market did after a recorded observation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "opportunity_outcome_v1"

# Horizons measured for every opportunity, in minutes. Multiple horizons make
# it visible whether an edge decays, rather than committing to one guess.
DEFAULT_HORIZONS_MINUTES = (15, 60, 240)

# A horizon needs candles covering it. Allow a small shortfall for the final
# candle boundary, but refuse to score a window with a real hole in it.
DEFAULT_COVERAGE_TOLERANCE = 0.90


class OutcomeError(ValueError):
    """Raised for malformed input, never for an unmeasurable window."""


@dataclass(frozen=True)
class HorizonOutcome:
    """What the market did over one horizon after the opportunity."""

    horizon_minutes: int
    status: str  # measured | pending | insufficient_candles
    entry_price: float | None = None
    exit_price: float | None = None
    forward_return_pct: float | None = None
    signed_return_pct: float | None = None
    max_favourable_pct: float | None = None
    max_adverse_pct: float | None = None
    candles_used: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_minutes": self.horizon_minutes,
            "status": self.status,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "forward_return_pct": self.forward_return_pct,
            "signed_return_pct": self.signed_return_pct,
            "max_favourable_pct": self.max_favourable_pct,
            "max_adverse_pct": self.max_adverse_pct,
            "candles_used": self.candles_used,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class OpportunityOutcome:
    opportunity_id: str
    symbol: str
    direction: str
    opened_at_s: int
    horizons: list[HorizonOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "opportunity_id": self.opportunity_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "opened_at_s": self.opened_at_s,
            "horizons": [h.to_dict() for h in self.horizons],
            "note": (
                "Paper measurement of subsequent market movement. No order was "
                "placed and no position existed."
            ),
        }


def _direction_sign(direction: str) -> int:
    """+1 for LONG, -1 for SHORT. Anything else has no side to be right about."""
    if direction == "LONG":
        return 1
    if direction == "SHORT":
        return -1
    raise OutcomeError(f"direction {direction!r} has no measurable side")


def measure_horizon(
    candles: Sequence[Mapping[str, Any]],
    opened_at_s: int,
    direction: str,
    horizon_minutes: int,
    now_s: int,
    coverage_tolerance: float = DEFAULT_COVERAGE_TOLERANCE,
) -> HorizonOutcome:
    """Measure one horizon. ``candles`` must be ascending by ``time`` seconds."""

    if horizon_minutes <= 0:
        raise OutcomeError("horizon_minutes must be positive")
    sign = _direction_sign(direction)
    end_s = opened_at_s + horizon_minutes * 60

    if now_s < end_s:
        return HorizonOutcome(
            horizon_minutes=horizon_minutes,
            status="pending",
            reason=f"horizon closes in {end_s - now_s}s; not measured early",
        )

    window = [
        c
        for c in candles
        if isinstance(c, Mapping)
        and isinstance(c.get("time"), int)
        and opened_at_s <= c["time"] <= end_s
    ]
    if not window:
        return HorizonOutcome(
            horizon_minutes=horizon_minutes,
            status="insufficient_candles",
            reason="no candles cover this window",
        )

    # Guard against a hole: the observed span must cover most of the horizon.
    observed_span = window[-1]["time"] - window[0]["time"]
    required_span = (end_s - opened_at_s) * coverage_tolerance
    if observed_span < required_span:
        return HorizonOutcome(
            horizon_minutes=horizon_minutes,
            status="insufficient_candles",
            candles_used=len(window),
            reason=(
                f"candles span {observed_span}s of a {end_s - opened_at_s}s horizon; "
                "the gap is reported rather than interpolated"
            ),
        )

    entry = float(window[0]["open"])
    if entry <= 0:
        return HorizonOutcome(
            horizon_minutes=horizon_minutes,
            status="insufficient_candles",
            candles_used=len(window),
            reason="entry price was not positive",
        )
    exit_price = float(window[-1]["close"])
    highest = max(float(c["high"]) for c in window)
    lowest = min(float(c["low"]) for c in window)

    forward = (exit_price - entry) / entry * 100.0
    # Favourable and adverse are relative to the side that was called, so a
    # SHORT that fell is favourable rather than negative.
    up = (highest - entry) / entry * 100.0
    down = (lowest - entry) / entry * 100.0
    favourable = up if sign > 0 else -down
    adverse = -down if sign > 0 else up

    return HorizonOutcome(
        horizon_minutes=horizon_minutes,
        status="measured",
        entry_price=entry,
        exit_price=exit_price,
        forward_return_pct=round(forward, 6),
        signed_return_pct=round(forward * sign, 6),
        max_favourable_pct=round(favourable, 6),
        max_adverse_pct=round(adverse, 6),
        candles_used=len(window),
    )


def measure_opportunity(
    opportunity_id: str,
    symbol: str,
    direction: str,
    opened_at_s: int,
    candles: Sequence[Mapping[str, Any]],
    now_s: int,
    horizons_minutes: Sequence[int] = DEFAULT_HORIZONS_MINUTES,
) -> OpportunityOutcome:
    """Measure every horizon for one opportunity."""

    if not opportunity_id:
        raise OutcomeError("opportunity_id is required")
    return OpportunityOutcome(
        opportunity_id=opportunity_id,
        symbol=symbol,
        direction=direction,
        opened_at_s=opened_at_s,
        horizons=[
            measure_horizon(candles, opened_at_s, direction, horizon, now_s)
            for horizon in horizons_minutes
        ],
    )


def expected_hit_rate(market_up_rate: float, long_share: float) -> float:
    """Hit rate a directionally-biased guesser would achieve by luck alone.

    A LONG is "right" whenever the market rose, a SHORT whenever it fell. So a
    caller who says LONG ``long_share`` of the time, with no skill whatever,
    scores ``long_share * up + (1 - long_share) * (1 - up)``.

    Without this, a sample drawn from one sustained trend reports the trend as
    if it were ability: calling SHORT in a falling market "wins" two thirds of
    the time while knowing nothing.
    """
    return long_share * market_up_rate + (1.0 - long_share) * (1.0 - market_up_rate)


def summarise(outcomes: Sequence[OpportunityOutcome], horizon_minutes: int) -> dict[str, Any]:
    """Aggregate measured outcomes at one horizon into a track record.

    ``hit_rate`` alone is not interpretable. It is reported beside the base rate
    the market itself set over the same windows, and the difference between them
    is the only figure here that gestures at skill — and even then only for this
    sample, in this regime.
    """

    pairs = [
        (outcome, horizon)
        for outcome in outcomes
        for horizon in outcome.horizons
        if horizon.horizon_minutes == horizon_minutes
        and horizon.status == "measured"
        and horizon.signed_return_pct is not None
        and horizon.forward_return_pct is not None
    ]
    if not pairs:
        return {
            "horizon_minutes": horizon_minutes,
            "measured": 0,
            "hit_rate": None,
            "market_up_rate": None,
            "expected_hit_rate": None,
            "skill_vs_baseline": None,
            "mean_signed_return_pct": None,
            "note": "no measured outcomes at this horizon yet",
        }

    measured = [horizon for _, horizon in pairs]
    returns = [h.signed_return_pct for h in measured]
    wins = sum(1 for r in returns if r > 0)
    hit_rate = wins / len(measured)

    # The market's own behaviour over exactly these windows.
    market_moves = [h.forward_return_pct for h in measured]
    up_rate = sum(1 for m in market_moves if m > 0) / len(market_moves)
    long_share = sum(
        1 for outcome, _ in pairs if outcome.direction == "LONG"
    ) / len(pairs)
    baseline = expected_hit_rate(up_rate, long_share)

    return {
        "horizon_minutes": horizon_minutes,
        "measured": len(measured),
        "hit_rate": round(hit_rate, 6),
        "market_up_rate": round(up_rate, 6),
        "long_share": round(long_share, 6),
        "expected_hit_rate": round(baseline, 6),
        # The figure that matters. Near zero means the calls did no better than
        # the direction mix and the market drift already explain.
        "skill_vs_baseline": round(hit_rate - baseline, 6),
        "mean_signed_return_pct": round(sum(returns) / len(returns), 6),
        "mean_market_move_pct": round(sum(market_moves) / len(market_moves), 6),
        "best_pct": round(max(returns), 6),
        "worst_pct": round(min(returns), 6),
        "mean_favourable_pct": round(
            sum(h.max_favourable_pct or 0.0 for h in measured) / len(measured), 6
        ),
        "mean_adverse_pct": round(
            sum(h.max_adverse_pct or 0.0 for h in measured) / len(measured), 6
        ),
        "note": (
            "hit_rate is not interpretable alone. Compare it with "
            "expected_hit_rate, which is what this direction mix would score by "
            "luck given how the market actually moved. A single-regime sample "
            "cannot demonstrate skill."
        ),
    }
