"""The paper track record by horizon, net of costs, overall and day by day.

A call counts as a win only when it finished beyond the round-trip cost in its
own direction, so this hit rate is lower than a raw "went the right way" rate
and is the one a trader could have banked. Intervals use the time-clustered
effective sample size (``tradesync_core.learning_stats``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .learning_stats import Z_95, effective_sample_size, mean_interval, wilson_interval
from .outcome_classification import CLASSIFICATIONS, WINS

DAY_S = 86_400


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _summary(rows: Sequence[Mapping[str, Any]], horizon: int, z: float) -> dict[str, Any]:
    n = len(rows)
    ess = effective_sample_size([int(r["opened_at_s"]) for r in rows], horizon)
    wins = sum(r["classification"] in WINS for r in rows)
    hit = wins / n if n else None
    hit_interval = wilson_interval(hit, ess, z) if hit is not None and ess > 0 else None
    mean = mean_interval([float(r["net_return_pct"]) for r in rows], ess, z)
    return {
        "attributions": n,
        "effective_samples": _round(ess),
        "wins": wins,
        "net_hit_rate": _round(hit),
        "net_hit_rate_low": _round(hit_interval[0]) if hit_interval else None,
        "net_hit_rate_high": _round(hit_interval[1]) if hit_interval else None,
        "mean_net_return_pct": _round(mean[0]) if mean else None,
        "mean_net_return_low": _round(mean[1]) if mean else None,
        "mean_net_return_high": _round(mean[2]) if mean else None,
    }


def scoreboard(rows: Sequence[Mapping[str, Any]], z: float = Z_95) -> list[dict[str, Any]]:
    """One entry per horizon: totals, class counts, and a daily series (UTC days)."""

    by_horizon: dict[int, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_horizon.setdefault(int(row["horizon_minutes"]), []).append(row)

    board = []
    for horizon in sorted(by_horizon):
        items = by_horizon[horizon]
        days: dict[int, list[Mapping[str, Any]]] = {}
        for row in items:
            days.setdefault(int(row["opened_at_s"]) // DAY_S, []).append(row)
        daily = []
        for day in sorted(days):
            summary = _summary(days[day], horizon, z)
            daily.append(
                {
                    "day": datetime.fromtimestamp(day * DAY_S, tz=timezone.utc).date().isoformat(),
                    "attributions": summary["attributions"],
                    "net_hit_rate": summary["net_hit_rate"],
                    "mean_net_return_pct": summary["mean_net_return_pct"],
                }
            )
        board.append(
            {
                "horizon_minutes": horizon,
                **_summary(items, horizon, z),
                "classifications": {
                    label: sum(r["classification"] == label for r in items) for label in CLASSIFICATIONS
                },
                "daily": daily,
            }
        )
    return board
