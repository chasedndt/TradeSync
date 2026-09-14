"""Score one rulebook over held-out stored decisions: admitted, hit rate, mean net return.

Split from ``walk_forward`` so the arithmetic of a single rulebook's replay can
be read, and tested, on its own.
"""

from __future__ import annotations

from typing import Any, Sequence

from .decision_replay import replay_decision
from .learning_stats import Z_95, effective_sample_size, mean_interval, wilson_interval
from .regime_weights import RegimeRulebook
from .replay import ReplayError


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def replay_metrics(
    records: Sequence[Any],
    rulebook: RegimeRulebook,
    horizon_minutes: int,
    cost_pct: float,
    z: float = Z_95,
) -> dict[str, Any]:
    """Replay ``records`` (``walk_forward.DecisionRecord``) under ``rulebook``."""

    times: list[int] = []
    nets: list[float] = []
    longs = refused = flipped = reproduced = unreplayable = 0
    for record in records:
        measured = record.horizons.get(horizon_minutes)
        if measured is None:
            continue
        try:
            decision = replay_decision(record.opportunity_id, record.symbol, record.decision, rulebook)
        except ReplayError:
            unreplayable += 1
            continue
        if not decision.admitted:
            refused += 1
            continue
        stored_long = record.direction == "LONG"
        market_move = measured.signed_return_pct if stored_long else -measured.signed_return_pct
        signed = market_move if decision.direction == "LONG" else -market_move
        nets.append(signed - cost_pct)
        times.append(record.opened_at_s)
        longs += decision.direction == "LONG"
        if decision.direction == record.direction:
            reproduced += 1
        else:
            flipped += 1

    n = len(nets)
    ess = effective_sample_size(times, horizon_minutes) if times else 0.0
    wins = sum(net > 0 for net in nets)
    hit = wins / n if n else None
    hit_interval = wilson_interval(hit, ess, z) if hit is not None and ess > 0 else None
    mean = mean_interval(nets, ess, z)
    considered = n + refused
    return {
        "rulebook_version": rulebook.version,
        "rulebook_digest": rulebook.digest,
        "decisions": considered,
        "admitted": n,
        "refused": refused,
        "flipped": flipped,
        "unreplayable": unreplayable,
        "reproduced_share": _round(reproduced / considered) if considered else None,
        "long_share": _round(longs / n) if n else None,
        "effective_samples": round(ess, 6),
        "net_hit_rate": _round(hit),
        "net_hit_rate_low": _round(hit_interval[0]) if hit_interval else None,
        "net_hit_rate_high": _round(hit_interval[1]) if hit_interval else None,
        "mean_net_return_pct": _round(mean[0]) if mean else None,
        "mean_net_return_low": _round(mean[1]) if mean else None,
        "mean_net_return_high": _round(mean[2]) if mean else None,
    }
