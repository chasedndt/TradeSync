"""A feature earns weight only by out-of-sample skill above chance; drift and noise earn nothing."""

from __future__ import annotations

import random

from tradesync_core.horizon_weights import combined, held_out_skill, relative_lean, state_leans


def test_a_state_that_really_precedes_the_move_earns_weight() -> None:
    rng = random.Random(11)
    states = [rng.choice(("calm", "hot")) for _ in range(3000)]
    forward = [0.01 if s == "calm" else -0.01 for s in states]  # "calm" is always followed by a rise
    skill = held_out_skill(states, forward, steps=1)
    assert skill["status"] == "measured" and skill["hit_rate"] == 1.0
    assert skill["leaning_states"] == {"calm": "up", "hot": "down"}
    assert skill["weight"] > 0.9 and skill["z"] > 5


def test_a_market_that_only_rose_rewards_no_up_call() -> None:
    rng = random.Random(5)
    states = [rng.choice(("a", "b")) for _ in range(2000)]
    forward = [0.004] * 2000  # every window rose: no state rose more often than the base
    skill = held_out_skill(states, forward, steps=1)
    assert skill["weight"] == 0.0 and skill["status"] == "no_leaning_state" and skill["leaning_states"] == {}


def test_uninformative_states_earn_nothing() -> None:
    states = ["same"] * 1200
    forward = [0.01 if t % 2 else -0.01 for t in range(1200)]
    assert held_out_skill(states, forward, steps=1)["weight"] == 0.0


def test_too_little_history_or_too_few_test_windows_weighs_zero() -> None:
    assert held_out_skill(["a"] * 10, [0.01] * 10, steps=1)["status"] == "too_little_history"
    states = ["up"] * 60 + [None] * 200
    forward = [0.01] * 60 + [None] * 200
    assert held_out_skill(states, forward, steps=20)["weight"] == 0.0


def test_state_leans_need_learned_windows_and_an_edge_over_the_base() -> None:
    states = ["x"] * 40 + ["y"] * 40
    forward = [0.01] * 40 + [-0.01] * 40
    assert state_leans(states, forward, list(range(80)), steps=1, base_share=0.5) == {"x": 1, "y": -1}
    assert state_leans(states, forward, list(range(80)), steps=10, base_share=0.5) == {}  # 4 windows each: too few


def test_relative_lean_and_the_weighted_combination() -> None:
    assert relative_lean({"share_up": 0.62, "independent_windows": 20}, 0.55) == 1
    assert relative_lean({"share_up": 0.52, "independent_windows": 20}, 0.55) == 0
    assert relative_lean({"share_up": 0.9, "independent_windows": 3}, 0.5) == 0
    nothing = combined([{"key": "trend", "label": "Trend", "weight": 0.0, "current_lean": 1}], "1 hour")
    assert nothing["lean"] == "unweighted" and "No feature has earned weight" in nothing["sentence"]
    thin = combined([{"key": "range", "label": "Range position", "weight": 0.14, "current_lean": -1}], "1 month")
    assert thin["score"] == -0.14 and thin["lean"] == "balanced"  # one weakly earned feature is not a full-strength lean
    mix = combined([{"key": "trend", "label": "Trend", "weight": 0.5, "current_lean": 1},
                    {"key": "rsi", "label": "RSI", "weight": 0.3, "current_lean": 1},
                    {"key": "drawdown", "label": "Drawdown", "weight": 0.4, "current_lean": -1}], "4 hours")
    assert mix["score"] == 0.333 and mix["lean"] == "up" and mix["earned"] == ["trend", "rsi", "drawdown"]
    assert "Trend 0.50" in mix["sentence"] and "leans higher" in mix["sentence"]
