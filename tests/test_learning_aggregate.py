"""Verdicts need decisive samples, clustered effective size and an interval that excludes chance."""

from __future__ import annotations

import json

import pytest

from tradesync_core.learning_aggregate import (
    BLOCK,
    FEATURE,
    HELPING,
    HURTING,
    NO_EVIDENCE,
    REGIME,
    VerdictPolicy,
    aggregate,
    aggregate_all,
)
from tradesync_core.learning_scoreboard import scoreboard
from tradesync_core.learning_stats import effective_sample_size, mean_interval, wilson_interval

T0 = 1_788_800_400  # an exact hour boundary


def row(i, *, won, decided=True, direction=None, stance="with", role="directional",
        feature="hl_direct_cvd", regime="rising", spacing_s=3600, horizon=60, net=None):
    direction = direction or ("LONG" if i % 2 == 0 else "SHORT")
    classification = ("clean_win" if won else "wrong_direction") if decided else "no_follow_through"
    verdict = "neutral" if not decided or stance == "none" else ("supported" if (stance == "with") == won else "misled")
    points_long = (stance == "with") == (direction == "LONG")
    contribution = 0.3 if (points_long if role == "directional" else stance == "with") else -0.3
    item = {"id": feature, "role": role, "stance": stance, "verdict": verdict, "contribution": contribution}
    return {
        "horizon_minutes": horizon, "symbol": "BTC-PERP", "direction": direction,
        "opened_at_s": T0 + i * spacing_s, "classification": classification,
        "net_return_pct": net if net is not None else (0.3 if won else (-0.4 if decided else -0.1)),
        "entry_regime": regime, "features": [item], "blocks": [{**item, "id": "price_volatility"}],
    }


def only(groups, key=None):
    chosen = [g for g in groups if key is None or g.key == key]
    assert len(chosen) == 1
    return chosen[0]


def test_wilson_interval_matches_the_textbook_values() -> None:
    low, high = wilson_interval(0.5, 100)
    assert low == pytest.approx(0.40383, abs=1e-5) and high == pytest.approx(0.59617, abs=1e-5)
    assert wilson_interval(0.0, 10)[0] == 0.0 and wilson_interval(1.0, 10)[1] == 1.0
    assert wilson_interval(0.5, 0) is None


def test_effective_size_counts_time_clusters_with_symbols_pooled() -> None:
    assert effective_sample_size([T0 + i * 3600 for i in range(10)], 60) == 10
    assert effective_sample_size([T0 + i for i in range(10)], 60) == 1
    assert effective_sample_size([T0, T0 + 1, T0 + 2, T0 + 3600], 60) == pytest.approx(16 / 10)


def test_mean_interval_uses_the_effective_size() -> None:
    mean, low, high = mean_interval([1.0, 2.0, 3.0], 3)
    assert mean == 2.0 and high - mean == pytest.approx(1.959964 / 3 ** 0.5, abs=1e-6)
    assert mean_interval([1.0], 1) == (1.0, None, None)
    assert mean_interval([], 5) is None


def test_a_reading_that_misleads_consistently_is_hurting() -> None:
    rows = [row(i, won=(i % 5 == 0)) for i in range(120)]  # 80% of stances end misled
    group = only(aggregate(rows, FEATURE))
    assert group.misled_rate == pytest.approx(0.8)
    assert group.chance_misled_rate == pytest.approx(0.5)
    assert group.misled_low > 0.5
    assert group.verdict == HURTING


def test_a_reading_that_is_right_consistently_is_helping() -> None:
    rows = [row(i, won=(i % 5 != 0)) for i in range(120)]
    assert only(aggregate(rows, FEATURE)).verdict == HELPING
    assert only(aggregate(rows, BLOCK)).verdict == HELPING


def test_a_reading_that_always_agrees_with_one_trending_side_has_no_evidence() -> None:
    rows = [row(i, won=(i % 5 != 0), direction="LONG") for i in range(120)]
    group = only(aggregate(rows, FEATURE))
    assert group.chance_misled_rate == pytest.approx(group.misled_rate)
    assert group.verdict == NO_EVIDENCE


def test_clustered_rows_are_not_independent_evidence() -> None:
    rows = [row(i, won=(i % 5 == 0), spacing_s=60) for i in range(120)]
    group = only(aggregate(rows, FEATURE))
    assert group.effective_samples == pytest.approx(2.0)
    assert group.verdict == NO_EVIDENCE


def test_too_few_decisive_results_give_no_verdict() -> None:
    rows = [row(i, won=False) for i in range(30)]
    assert only(aggregate(rows, FEATURE)).verdict == NO_EVIDENCE
    lenient = VerdictPolicy(min_decided=10, min_effective=10)
    assert only(aggregate(rows, FEATURE, lenient)).verdict == HURTING


def test_moves_inside_costs_are_neutral_but_count_in_mean_returns() -> None:
    rows = [row(i, won=False, decided=False) for i in range(10)] + [row(10, won=True)]
    group = only(aggregate(rows, FEATURE))
    assert group.neutral == 10 and group.decided == 1
    assert group.mean_net_return_pct == pytest.approx((10 * -0.1 + 0.3) / 11)


def test_mean_net_is_split_by_whether_the_reading_agreed() -> None:
    rows = [row(i, won=True, stance="with", net=0.2) for i in range(6)]
    rows += [row(i + 6, won=True, stance="against", net=-0.4) for i in range(4)]
    group = only(aggregate(rows, FEATURE))
    assert group.mean_net_agreed_pct == pytest.approx(0.2) and group.agreed == 6
    assert group.mean_net_disagreed_pct == pytest.approx(-0.4) and group.disagreed == 4


def test_roles_are_kept_apart_for_the_same_feature() -> None:
    rows = [row(i, won=True) for i in range(5)] + [row(i + 5, won=True, role="suitability") for i in range(5)]
    groups = aggregate(rows, FEATURE)
    assert sorted(g.role for g in groups) == ["directional", "suitability"]


def test_regime_groups_judge_the_calls_themselves() -> None:
    rows = [row(i, won=(i % 5 == 0), regime="falling") for i in range(120)]
    group = only(aggregate(rows, REGIME), "falling")
    assert group.role is None and group.misled_rate == pytest.approx(0.8)
    assert group.verdict == HURTING


def test_aggregate_all_is_deterministic_and_covers_every_dimension() -> None:
    rows = [row(i, won=(i % 3 == 0)) for i in range(90)]
    first, second = aggregate_all(rows), aggregate_all(list(reversed(rows)))
    assert set(first) == {"feature", "block", "regime", "symbol", "horizon"}
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_the_scoreboard_counts_wins_after_costs_by_horizon_and_day() -> None:
    rows = [row(i, won=(i % 2 == 0), spacing_s=3 * 3600) for i in range(16)]
    rows += [row(i, won=True, decided=False, horizon=15) for i in range(4)]
    board = {entry["horizon_minutes"]: entry for entry in scoreboard(rows)}
    assert board[60]["wins"] == 8 and board[60]["net_hit_rate"] == 0.5
    assert board[60]["classifications"]["clean_win"] == 8
    days = {(T0 + i * 3 * 3600) // 86_400 for i in range(16)}  # 48 hours, UTC days
    assert len(board[60]["daily"]) == len(days)
    assert sum(day["attributions"] for day in board[60]["daily"]) == 16
    assert [d["day"] for d in board[60]["daily"]] == sorted(d["day"] for d in board[60]["daily"])
    assert board[15]["wins"] == 0 and board[15]["classifications"]["no_follow_through"] == 4
