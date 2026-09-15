"""The positioning candidate analysis: the declared readings, and the live rules they mirror."""

from __future__ import annotations

import importlib
import math
import sys
import types
from pathlib import Path

import pytest

from tradesync_core.edge_evidence import CostAssumptions
from tradesync_core.feature_evidence import FeatureOutcomeRow
from tradesync_core.market_features import load_catalog

ROOT = Path(__file__).resolve().parents[1]
if "positioning_tool" not in sys.modules:
    _package = types.ModuleType("positioning_tool")
    _package.__path__ = [str(ROOT / "tools" / "positioning")]
    sys.modules["positioning_tool"] = _package
candidates = importlib.import_module("positioning_tool.candidates")
readings = importlib.import_module("positioning_tool.readings")
assess = importlib.import_module("positioning_tool.assess")

CATALOG = load_catalog(ROOT / "config" / "features" / "market-feature-catalog-v1.json")
DECLARATION = (ROOT / "docs" / "research" / "2026-09-15_positioning-candidates.md").read_text(encoding="utf-8")
COSTS = CostAssumptions(round_trip_fee_pct=0.09, spread_pct=0.02, slippage_pct=0.01, source="test")


def _declared():
    return {r.reading_id: r for r in candidates.declared_readings(CATALOG.features)}


def test_the_twenty_declared_readings_are_the_ones_in_the_committed_declaration():
    declared = _declared()
    assert len(declared) == 20
    assert len(declared) * 3 * 2 == assess.DECLARED_CELLS
    for reading_id in declared:
        assert f"`{reading_id}`" in DECLARATION
    assert {r.reading_id for r in declared.values() if r.admissible} == {r for r in declared if r.endswith(":z")}


def test_z_parameters_come_from_the_catalog_except_the_two_declared_gaps():
    declared = _declared()
    as_tuple = lambda r: (r.z_method, r.z_lookback, r.z_minimum)  # noqa: E731
    assert as_tuple(declared["hl_funding_hourly_rate:z"]) == ("robust_zscore", 168, 30)
    assert as_tuple(declared["hl_open_interest_4h_pct:z"]) == ("ordinary_zscore", 168, 30)
    assert as_tuple(declared["liq_map_skew_3pct:z"]) == ("robust_zscore", 288, 48)
    assert as_tuple(declared["binance_open_interest_usd:z"]) == ("robust_zscore", 240, 20)
    assert as_tuple(declared["hl_funding_apr_24h:z"]) == ("robust_zscore", 24, 12)


def test_proxy_seconds_are_placed_at_their_last_millisecond():
    assert readings.proxy_points([[10, 1.0], [5, 2.0]]) == [{"ts": 5999, "value": 2.0}, {"ts": 10999, "value": 1.0}]


def test_an_entry_value_never_comes_from_after_entry_or_beyond_the_feature_tolerance():
    spec = CATALOG.features["hl_open_interest_4h_pct"]  # 30 s fresh + 300 s sampling
    series = readings.Series([{"ts": 1_000_000, "value": 1.0}, {"ts": 1_200_000, "value": 2.0}, {"ts": 1_400_001, "value": 3.0}])
    assert series.at_entry("hl_open_interest_4h_pct", 1_400_000, spec) == (1_200_000, 2.0)
    assert series.at_entry("hl_open_interest_4h_pct", 1_400_001 + 330_000, spec) == (1_400_001, 3.0)
    assert series.at_entry("hl_open_interest_4h_pct", 1_400_001 + 330_001, spec) is None


def test_the_z_reading_uses_only_earlier_samples_and_needs_its_minimum():
    series = readings.Series([{"ts": t, "value": v} for t, v in [(1, 1.0), (2, 2.0), (3, 4.0), (4, 100.0)]])
    history = [1.0, 2.0, 4.0]
    mean = sum(history) / 3
    sd = math.sqrt(sum((x - mean) ** 2 for x in history) / 2)
    assert readings.z_reading(series, 4, 10.0, "ordinary_zscore", 5, 3) == pytest.approx((10.0 - mean) / sd)
    assert readings.z_reading(series, 4, 10.0, "ordinary_zscore", 5, 4) is None
    flat = readings.Series([{"ts": t, "value": 5.0} for t in range(1, 6)])
    assert readings.z_reading(flat, 6, 5.0, "robust_zscore", 5, 3) is None


def test_the_four_hour_change_needs_a_base_at_least_three_and_a_half_hours_back():
    hour = 3_600_000
    t = 10 * hour
    series = readings.Series([{"ts": t - 5 * hour + k * 600_000, "value": 100.0 + k} for k in range(31)])
    # Earliest sample at or after t-4h is at exactly t-4h, k = 6.
    assert readings.change_4h(series, t, 130.0) == pytest.approx((130.0 - 106.0) / 106.0 * 100)
    short = readings.Series([{"ts": t - 3 * hour + k * 600_000, "value": 100.0} for k in range(19)])
    assert readings.change_4h(short, t, 110.0) is None


def test_readings_come_from_the_entry_record_or_the_store_and_the_price_product_needs_the_return():
    declared = _declared()
    wanted = [declared["hl_open_interest_4h_pct:raw"], declared["hl_open_interest_4h_pct:with_price"], declared["binance_funding_rate_8h:raw"]]
    entry = readings.Entry("opp-1", "BTC-PERP", 10_000_000)
    store = {"hl_open_interest_4h_pct": readings.Series([{"ts": 9_900_000, "value": 2.0}]),
             "binance_funding_rate_8h": readings.Series([{"ts": 9_990_000, "value": 0.5}])}
    recorded = {"binance_funding_rate_8h": (9_999_000, 0.0001), "hl_return_1h_pct": (9_999_500, -0.4)}
    values = readings.signed_readings(entry, wanted, recorded, store, CATALOG.features)
    assert values == {"hl_open_interest_4h_pct:raw": 2.0, "hl_open_interest_4h_pct:with_price": pytest.approx(-0.8),
                      "binance_funding_rate_8h:raw": 0.0001}
    without_price = readings.signed_readings(entry, wanted, {"binance_funding_rate_8h": (9_999_000, 0.0001)}, store, CATALOG.features)
    assert "hl_open_interest_4h_pct:with_price" not in without_price


def test_rows_are_one_per_reading_and_outcome_and_abstains_are_counted_per_entry():
    declared = _declared()
    wanted = [declared["hl_open_interest_4h_pct:raw"]]
    store = {"BTC-PERP": {"hl_open_interest_4h_pct": readings.Series([{"ts": 9_900_000, "value": 0.0}])}}
    outcomes = [{"opportunity_id": "opp-1", "symbol": "BTC-PERP", "horizon_minutes": h, "opened_at_s": 10_000,
                 "entry_ms": 10_000_000, "forward_return_pct": 0.3} for h in (15, 60)]
    rows, coverage = assess.build_rows(outcomes, {}, store, wanted, CATALOG.features)
    assert len(rows) == 2 and coverage["opportunities"] == 1
    assert coverage["readings"]["hl_open_interest_4h_pct:raw"]["abstained"] == 1


def test_the_holm_bar_and_the_windows_it_implies_match_the_declaration():
    z = assess.holm_first_z()
    assert z == pytest.approx(3.53, abs=0.01)
    assert assess.windows_needed(0.10) == math.ceil((z / 0.2) ** 2)
    assert assess.windows_needed(0.05) == math.ceil((z / 0.1) ** 2)


def test_reasons_name_every_declared_failure_that_applies():
    base = {"measured": 50, "independent_pooled": 20, "positive_skill": False, "holdout_skill": None, "mean_net_return_pct": -0.1}
    assert assess.reasons({**base, "measured": 0}, 311) == ["no observations"]
    assert assess.reasons(base, 311) == ["too few independent windows", "no positive skill", "negative after costs"]
    held_out_badly = {**base, "independent_pooled": 400, "positive_skill": True, "holdout_skill": -0.02, "mean_net_return_pct": 0.05}
    assert assess.reasons(held_out_badly, 311) == ["failed hold-out"]


def test_only_an_earned_z_reading_with_an_edge_after_costs_is_admitted():
    """A contrarian series that is right every time, with plenty of independent windows."""
    declared = _declared()
    wanted = [declared["hl_funding_hourly_rate:z"], declared["hl_funding_hourly_rate:raw"]]
    rows = []
    for k in range(400):
        value = 1.0 if k % 2 else -1.0
        forward = -0.5 * value  # the market goes against the reading
        for reading in wanted:
            rows.append(FeatureOutcomeRow(reading.reading_id, "BTC-PERP", 1_000_000 + k * 900, 15, forward, value))
    coverage = {"opportunities": 400, "readings": {r.reading_id: {"entries": 400, "abstained": 0, "first_entry_s": 0, "last_entry_s": 0} for r in wanted}}
    result = assess.assess(rows, wanted, coverage, COSTS, draws=50)
    assert result["decision"]["admitted"] == ["hl_funding_hourly_rate:z 15m inverted"]
    assert result["decision"]["earned_not_admissible"] == ["hl_funding_hourly_rate:raw 15m inverted"]
