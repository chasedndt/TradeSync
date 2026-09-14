"""Simulate a paper fill for a rehearsed opportunity, with its costs stated.

A rehearsal answers "what would this plan have cost and returned if filled
now", using the live mark and spread, and writes the answer to a journal. It is
not an order. Nothing here can reach an execution service, a wallet or a
signer; the function takes numbers and returns numbers.

Costs are not optional. A rehearsal that ignored fees and spread would be a
gross number dressed as a result — the same mistake the skill gate guards
against. Every fill carries the fee schedule it used and where that schedule
came from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeeSchedule:
    """Venue fees as fractions of notional, with their source stated."""

    taker_fee: float
    maker_fee: float  # negative means a rebate
    source: str
    read_on: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "taker_fee": self.taker_fee,
            "maker_fee": self.maker_fee,
            "source": self.source,
            "read_on": self.read_on,
        }


# Hyperliquid perpetuals, base tier, from the venue's own fee page. Referral
# and volume tiers lower these; the base tier is the conservative choice.
HYPERLIQUID_BASE_FEES = FeeSchedule(
    taker_fee=0.00045,
    maker_fee=0.00015,
    source="https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees",
    read_on="2026-09-14",
)


class RehearsalError(ValueError):
    """Raised for inputs that cannot produce an honest fill."""


def simulate_fill(
    direction: str,
    size_usd: float,
    mark_price: float,
    spread_bps: float | None,
    observed_at_ms: int,
    fees: FeeSchedule = HYPERLIQUID_BASE_FEES,
) -> dict[str, Any]:
    """A market-order fill at the mark, crossing half the spread, paying taker.

    The half-spread is the cost of crossing from mid to the touch; a missing
    spread is refused rather than assumed zero, because zero slippage is a
    claim about the book that the caller did not measure.
    """
    if direction not in ("LONG", "SHORT"):
        raise RehearsalError(f"direction {direction!r} has no side to fill")
    if not (size_usd > 0):
        raise RehearsalError("size_usd must be positive")
    if not (mark_price > 0):
        raise RehearsalError("mark_price must be positive")
    if spread_bps is None or spread_bps < 0:
        raise RehearsalError("spread_bps is required; a fill cannot assume a free crossing")
    if not isinstance(observed_at_ms, int) or observed_at_ms <= 0:
        raise RehearsalError("observed_at_ms must be a positive epoch in milliseconds")

    half_spread = mark_price * (spread_bps / 10_000) / 2
    fill_price = mark_price + half_spread if direction == "LONG" else mark_price - half_spread
    quantity = size_usd / fill_price
    fee_usd = size_usd * fees.taker_fee
    slippage_usd = quantity * half_spread

    return {
        "direction": direction,
        "size_usd": round(size_usd, 6),
        "mark_price": mark_price,
        "fill_price": round(fill_price, 8),
        "quantity": round(quantity, 10),
        "half_spread_bps": round(spread_bps / 2, 6),
        "slippage_usd": round(slippage_usd, 8),
        "fee_usd": round(fee_usd, 8),
        "entry_cost_usd": round(slippage_usd + fee_usd, 8),
        # What the position must move, in the called direction, before the
        # entry costs alone are covered — before any exit cost.
        "breakeven_move_pct": round((slippage_usd + fee_usd) / size_usd * 100, 6),
        "observed_at_ms": observed_at_ms,
        "fees": fees.to_dict(),
        "simulated": True,
        "note": "Simulated market fill. No order was placed; no wallet or signer exists.",
    }
