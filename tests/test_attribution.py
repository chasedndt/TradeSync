"""One measured call is split into feature and block contributions, judged, and explained."""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from learning_fixtures import stored_decision  # noqa: E402

from tradesync_core.attribution import (  # noqa: E402
    MISLED,
    NEUTRAL,
    SUPPORTED,
    AttributionError,
    MeasuredHorizon,
    attribute_outcome,
)
from tradesync_core.decision_contributions import DIRECTIONAL, SUITABILITY, contributions_from_decision  # noqa: E402


def attribute(decision, signed, mfe=0.3, mae=0.05, direction="LONG", regime="rising", cost=0.12):
    return attribute_outcome(
        opportunity_id="opp-1", symbol="BTC-PERP", direction=direction, opened_at_s=1_788_800_000,
        decision=decision, measured=MeasuredHorizon(60, signed, mfe, mae), entry_regime=regime, cost_pct=cost,
    )


def by_id(items):
    return {item["id"]: item for item in items}


def test_directional_shares_add_up_to_the_directional_score() -> None:
    parts = contributions_from_decision(stored_decision(ret=0.01, cvd=0.47))
    directional = [f for f in parts.features if f.role == DIRECTIONAL]
    assert sum(f.contribution for f in directional) == pytest.approx(0.24)
    assert {f.key: f.contribution for f in directional}["hl_direct_cvd"] == pytest.approx(0.235)


def test_suitability_shares_add_up_to_their_blocks_share_of_suitability() -> None:
    parts = contributions_from_decision(stored_decision(spread=-0.6, depth=0.2))
    liquidity = [f for f in parts.features if f.role == SUITABILITY]
    coverage = 0.3 + 0.125
    expected_block_share = 0.125 * -0.2 / coverage
    assert sum(f.contribution for f in liquidity) == pytest.approx(expected_block_share)
    blocks = {b.key: b for b in parts.blocks}
    assert blocks["liquidity"].contribution == pytest.approx(expected_block_share)
    assert blocks["price_volatility"].role == DIRECTIONAL
    assert blocks["price_volatility"].contribution == pytest.approx(0.24)
    assert "positioning" not in blocks  # no evidence, no stance


def test_recorded_feature_weights_scale_directional_shares() -> None:
    parts = contributions_from_decision(stored_decision(ret=0.3, cvd=0.6, cvd_weight=2.0))
    shares = {f.key: f.contribution for f in parts.features if f.role == DIRECTIONAL}
    assert shares["hl_direct_cvd"] == pytest.approx(2 * 0.6 / 3)
    assert shares["hl_return_1h_pct"] == pytest.approx(0.3 / 3)


def test_a_clean_long_win_credits_readings_that_pointed_up() -> None:
    result = attribute(stored_decision(), signed=0.5, mfe=0.6, mae=0.05)
    features = by_id(result.features)
    assert result.classification == "clean_win"
    assert features["hl_direct_cvd"]["verdict"] == SUPPORTED
    assert features["hl_depth_25bp_usd"]["verdict"] == SUPPORTED  # favourable, and it paid
    assert features["hl_spread_bps"]["verdict"] == MISLED  # unfavourable, yet it paid
    assert "Supported by CVD order flow (pointed up)" in result.reason
    assert result.reason.endswith("Entry regime: rising.")


def test_a_long_loss_names_the_readings_that_misled_it() -> None:
    result = attribute(stored_decision(), signed=-0.4, mfe=0.05, mae=0.5)
    features = by_id(result.features)
    assert result.classification == "wrong_direction"
    assert result.outcome.net_return_pct == pytest.approx(-0.52)
    assert features["hl_direct_cvd"]["verdict"] == MISLED
    assert features["hl_spread_bps"]["verdict"] == SUPPORTED  # it warned
    assert "Misled by CVD order flow (pointed up)" in result.reason
    assert "while price fell" in result.reason


def test_a_reversed_short_says_price_rose() -> None:
    decision = stored_decision(direction="SHORT", ret=-0.01, cvd=-0.47)
    result = attribute(decision, signed=-0.3, mfe=0.3, mae=0.5, direction="SHORT", regime="falling")
    assert result.classification == "reversed"
    assert by_id(result.features)["hl_direct_cvd"]["verdict"] == MISLED
    assert "then reversed" in result.reason and "while price rose" in result.reason
    assert "CVD order flow (pointed down)" in result.reason


def test_a_move_inside_costs_is_neutral_for_every_reading() -> None:
    result = attribute(stored_decision(), signed=0.05)
    assert result.classification == "no_follow_through"
    assert {item["verdict"] for item in result.features + result.blocks} == {NEUTRAL}
    assert "did not cover costs" in result.reason
    assert result.reason.split(". ")[1][0].isupper()


def test_a_win_after_drawdown_mentions_the_drawdown() -> None:
    result = attribute(stored_decision(), signed=0.3, mfe=0.4, mae=0.6)
    assert result.classification == "win_after_drawdown"
    assert "0.60% drawdown, deeper than the win" in result.reason


def test_costs_are_recorded_and_configurable() -> None:
    result = attribute(stored_decision(), signed=0.25, cost=0.3)
    assert result.outcome.cost_pct == 0.3
    assert result.outcome.net_return_pct == pytest.approx(-0.05)
    assert result.classification == "no_follow_through"


def test_missing_evidence_and_regime_are_stated_not_guessed() -> None:
    result = attribute({}, signed=-0.5, regime=None)
    assert result.features == () and result.blocks == ()
    assert "No feature evidence was stored with this decision." in result.reason
    assert result.reason.endswith("Entry regime unknown.")
    assert result.entry_regime == "unknown"


def test_every_sentence_avoids_retired_wording() -> None:
    cases = [(0.5, 0.6, 0.05), (0.3, 0.4, 0.6), (-0.4, 0.05, 0.5), (-0.3, 0.3, 0.5), (0.05, 0.1, 0.1)]
    for signed, mfe, mae in cases:
        reason = attribute(stored_decision(), signed, mfe, mae).reason.lower()
        for word in ("simulat", "dry run", "dry_run", "demo", "observe mode"):
            assert word not in reason


def test_a_call_without_a_side_is_refused() -> None:
    with pytest.raises(AttributionError):
        attribute(stored_decision(), signed=0.1, direction="NONE")


def test_attribution_is_deterministic_and_serialisable() -> None:
    first = attribute(stored_decision(), signed=-0.4, mfe=0.05, mae=0.5).to_dict()
    second = attribute(stored_decision(), signed=-0.4, mfe=0.05, mae=0.5).to_dict()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["schema_version"] == "opportunity_attribution_v1"
    assert first["rulebook_version"] == "1.0.0"
