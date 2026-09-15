"""Synthetic decisions with a known structure, for the evidence-combination tests."""

from __future__ import annotations

from typing import Mapping

from tradesync_core.evidence_combination_data import Decision

# An exact hour (and four-hour) boundary, so hourly decisions fall one per 60-minute cluster.
T0 = 1_788_796_800
HOUR = 3600


def decision(
    index: int,
    rose: bool,
    calls: Mapping[str, int] | None = None,
    *,
    regime: str = "rising",
    score: float | None = None,
    spacing_s: int = HOUR,
    move: float = 0.3,
    symbol: str = "BTC-PERP",
) -> Decision:
    return Decision(
        key=f"d{index:05d}",
        symbol=symbol,
        opened_at_s=T0 + index * spacing_s,
        forward_return_pct=move if rose else -move,
        regime=regime,
        calls=dict(calls or {}),
        rulebook_score=score,
    )


def skilled_call(index: int) -> tuple[bool, int]:
    """(rose, call): the market alternates; the call is right in 80% of rises and 60% of falls.

    So P(up call | rose) = 0.8 and P(up call | fell) = 0.4: a plain LR of 2 for an up call.
    """
    rose = index % 2 == 0
    right = index % 10 < 7
    direction = 1 if rose else -1
    return rose, direction if right else -direction


def uninformative_call(index: int) -> int:
    """Up in exactly half the rises and half the falls: no information at all."""
    return 1 if (index // 2) % 2 == 0 else -1
