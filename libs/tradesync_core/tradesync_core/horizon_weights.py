"""The weight a feature earns out of sample, and the lean the earned weights add up to.

Each feature's states are learned on the older 70% of its history: a state
leans up when the windows that followed it ended higher more often than all
windows of that period did, by at least five points, over at least eight
non-overlapping windows. The newer 30% is the test. Each non-overlapping test
window that starts in a leaning state is a hit when the price moved the way
the state leaned. Skill is the hit rate above what those same predictions would
score by chance given the test period's own share of rising windows, so a
market that simply went up does not reward every "up" call.

A feature earns weight only when its skill is at least one standard error
above chance, and the weight shrinks when there are few test windows. A feature
that earned nothing weighs nothing, however today's record reads. The combined
lean is the weighted mean of the earned features' current leans.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Mapping, Sequence

from .horizon_stats import independent_windows

SPLIT = 0.7
EDGE = 0.05
MIN_LEARNED_WINDOWS = 8
MIN_TEST_WINDOWS = 12
MIN_Z = 1.0
SHRINK = 30
FULL_WEIGHT = 1.0
COMBINED_LEAN = 0.2


def share_up(forward: Sequence[float | None], indices: Sequence[int]) -> float | None:
    values = [forward[t] for t in indices if forward[t] is not None]
    return sum(1 for v in values if v > 0) / len(values) if values else None


def state_leans(states: Sequence[str | None], forward: Sequence[float | None], indices: Sequence[int],
                steps: int, base_share: float) -> dict[str, int]:
    """+1 / -1 for each state whose following windows rose more / less often than the base by EDGE."""
    by_state: dict[str, list[int]] = defaultdict(list)
    for t in indices:
        by_state[str(states[t])].append(t)
    leans: dict[str, int] = {}
    for state, idx in by_state.items():
        if independent_windows(idx, steps) < MIN_LEARNED_WINDOWS:
            continue
        share = sum(1 for t in idx if (forward[t] or 0) > 0) / len(idx)
        if share - base_share >= EDGE:
            leans[state] = 1
        elif share - base_share <= -EDGE:
            leans[state] = -1
    return leans


def held_out_skill(states: Sequence[str | None], forward: Sequence[float | None], steps: int, split: float = SPLIT) -> dict[str, Any]:
    usable = [t for t in range(len(states)) if states[t] is not None and forward[t] is not None]
    result: dict[str, Any] = {"status": "too_little_history", "learned_windows": 0, "test_windows": 0, "hit_rate": None,
                              "chance": None, "skill": None, "z": None, "edge_pct": None, "weight": 0.0, "leaning_states": {}}
    if len(usable) < 2 * MIN_TEST_WINDOWS:
        return result
    cut = usable[int(len(usable) * split)]
    learn = [t for t in usable if t + steps <= cut]  # learning windows end before the test begins
    test = [t for t in usable if t >= cut]
    learn_base = share_up(forward, learn)
    if not learn or learn_base is None:
        return result
    leans = state_leans(states, forward, learn, steps, learn_base)
    picked: list[int] = []
    next_free = -1
    for t in test:
        if t >= next_free and str(states[t]) in leans:
            picked.append(t)
            next_free = t + steps
    result.update(learned_windows=independent_windows(learn, steps), test_windows=len(picked),
                  leaning_states={s: ("up" if v > 0 else "down") for s, v in sorted(leans.items())})
    if len(picked) < MIN_TEST_WINDOWS:
        result["status"] = "too_few_test_windows" if leans else "no_leaning_state"
        return result
    n = len(picked)
    hits = sum(1 for t in picked if (forward[t] or 0) * leans[str(states[t])] > 0)
    test_up = share_up(forward, test) or 0.0
    up_calls = sum(1 for t in picked if leans[str(states[t])] > 0) / n
    chance = test_up * up_calls + (1 - test_up) * (1 - up_calls)
    hit_rate = hits / n
    skill = hit_rate - chance
    se = math.sqrt(chance * (1 - chance) / n) if 0 < chance < 1 else 0.0
    z = skill / se if se > 0 else 0.0
    weight = min(1.0, 2 * skill) * n / (n + SHRINK) if z >= MIN_Z and skill > 0 else 0.0
    edge = sum((forward[t] or 0) * leans[str(states[t])] for t in picked) / n
    result.update(status="measured", hit_rate=round(hit_rate, 3), chance=round(chance, 3), skill=round(skill, 3),
                  z=round(z, 2), edge_pct=round(edge * 100, 3), weight=round(weight, 3))
    return result


def relative_lean(record: Mapping[str, Any], base_share: float | None) -> int:
    """Today's state against all windows: +1 when it rose more often by EDGE, -1 when less, 0 otherwise or when thin."""
    if base_share is None or record.get("share_up") is None or (record.get("independent_windows") or 0) < MIN_LEARNED_WINDOWS:
        return 0
    diff = float(record["share_up"]) - base_share
    return 1 if diff >= EDGE else -1 if diff <= -EDGE else 0


def combined(features: Sequence[Mapping[str, Any]], horizon_label: str) -> dict[str, Any]:
    """Net earned weight pointing one way, over at least one full unit of weight.

    Dividing by the earned total alone would let a single weakly earned feature
    read as a full-strength lean; the floor of ``FULL_WEIGHT`` keeps thin
    evidence reading as thin.
    """
    earned = [f for f in features if float(f.get("weight") or 0) > 0]
    total = sum(float(f["weight"]) for f in earned)
    if total <= 0:
        return {"score": None, "lean": "unweighted", "total_weight": 0.0, "earned": [],
                "sentence": f"No feature has earned weight out of sample over {horizon_label}, so nothing is combined."}
    score = sum(float(f["weight"]) * int(f.get("current_lean") or 0) for f in earned) / max(total, FULL_WEIGHT)
    lean = "up" if score >= COMBINED_LEAN else "down" if score <= -COMBINED_LEAN else "balanced"
    names = ", ".join(f"{f['label']} {float(f['weight']):.2f}" for f in sorted(earned, key=lambda f: -float(f["weight"])))
    words = {"up": "leans higher", "down": "leans lower", "balanced": "is balanced"}[lean]
    return {"score": round(score, 3), "lean": lean, "total_weight": round(total, 3), "earned": [f["key"] for f in earned],
            "sentence": f"Weighted by what each feature earned out of sample ({names}), the reading over {horizon_label} {words} ({score:+.2f})."}
