import pytest

from app.feature_extractor import extract_feature_observations, load_sampling_intervals
from app.return_1h import attach_derived_features, derive_return_1h_pct


HOUR_MS = 60 * 60 * 1000


def _snapshot(ts: int, mark: float) -> dict:
    return {
        "venue": "hyperliquid",
        "symbol": "BTC-PERP",
        "ts": ts,
        "price": {"mark_price_usd": mark},
    }


def test_return_1h_uses_anchor_at_or_before_the_one_hour_target():
    now = 1767297600000
    history = [
        {"ts": now - HOUR_MS - 30_000, "value": 100.0},
        {"ts": now - HOUR_MS + 30_000, "value": 999.0},
        {"ts": now - 60_000, "value": 111.0},
    ]
    observation = derive_return_1h_pct(_snapshot(now, 101.0), history)
    assert observation is not None
    # The 999.0 point sits after t-1h and must not become the comparator.
    assert observation["comparator"]["anchor_value"] == 100.0
    assert observation["value"] == pytest.approx(1.0)
    assert observation["feature_id"] == "hl_return_1h_pct"


def test_return_1h_prefers_the_newest_admissible_anchor():
    now = 1767297600000
    history = [
        {"ts": now - HOUR_MS - 200_000, "value": 50.0},
        {"ts": now - HOUR_MS - 10_000, "value": 200.0},
    ]
    observation = derive_return_1h_pct(_snapshot(now, 220.0), history)
    assert observation["comparator"]["anchor_value"] == 200.0
    assert observation["value"] == pytest.approx(10.0)


def test_return_1h_suppressed_when_the_gap_exceeds_the_tolerance():
    now = 1767297600000
    history = [{"ts": now - HOUR_MS - (10 * 60 * 1000), "value": 100.0}]
    assert derive_return_1h_pct(_snapshot(now, 101.0), history) is None


def test_return_1h_suppressed_without_history():
    now = 1767297600000
    assert derive_return_1h_pct(_snapshot(now, 101.0), []) is None


def test_return_1h_suppressed_when_history_is_all_newer_than_the_target():
    now = 1767297600000
    history = [{"ts": now - 120_000, "value": 100.0}]
    assert derive_return_1h_pct(_snapshot(now, 101.0), history) is None


def test_return_1h_rejects_non_positive_or_non_finite_inputs():
    now = 1767297600000
    zero_anchor = [{"ts": now - HOUR_MS, "value": 0.0}]
    assert derive_return_1h_pct(_snapshot(now, 101.0), zero_anchor) is None

    good_anchor = [{"ts": now - HOUR_MS, "value": 100.0}]
    missing_price = {
        "venue": "hyperliquid",
        "symbol": "BTC-PERP",
        "ts": now,
        "price": {},
    }
    assert derive_return_1h_pct(missing_price, good_anchor) is None
    assert derive_return_1h_pct(_snapshot(0, 101.0), good_anchor) is None


def test_return_1h_ignores_malformed_history_points():
    now = 1767297600000
    history = [
        "not-a-point",
        {"ts": None, "value": 100.0},
        {"ts": now - HOUR_MS, "value": "abc"},
        {"ts": now - HOUR_MS - 5_000, "value": 100.0},
    ]
    observation = derive_return_1h_pct(_snapshot(now, 102.0), history)
    assert observation["comparator"]["anchor_value"] == 100.0


def test_return_1h_is_negative_when_price_fell():
    now = 1767297600000
    history = [{"ts": now - HOUR_MS, "value": 100.0}]
    observation = derive_return_1h_pct(_snapshot(now, 97.5), history)
    assert observation["value"] == pytest.approx(-2.5)


def test_catalog_now_samples_the_return_feature():
    intervals = load_sampling_intervals()
    assert intervals["hl_return_1h_pct"] == 60000


def test_attach_derived_writes_the_return_onto_the_snapshot():
    now = 1767297600000
    snapshot = _snapshot(now, 101.0)
    history = [{"ts": now - HOUR_MS, "value": 100.0}]
    attached = attach_derived_features(snapshot, history)
    derived = attached["derived"]["return_1h_pct"]
    assert derived["value"] == pytest.approx(1.0)
    assert derived["comparator"]["anchor_value"] == 100.0


def test_attach_derived_leaves_the_snapshot_alone_without_an_anchor():
    now = 1767297600000
    snapshot = _snapshot(now, 101.0)
    assert "derived" not in attach_derived_features(snapshot, [])


def test_extractor_reads_the_attached_return_without_touching_history():
    now = 1767297600000
    snapshot = _snapshot(now, 101.0)
    attach_derived_features(snapshot, [{"ts": now - HOUR_MS, "value": 100.0}])
    values = {item["feature_id"]: item["value"] for item in
              extract_feature_observations(snapshot)}
    assert values["hl_return_1h_pct"] == pytest.approx(1.0)


def test_extractor_omits_the_return_when_nothing_was_derived():
    now = 1767297600000
    observations = extract_feature_observations(_snapshot(now, 101.0))
    assert "hl_return_1h_pct" not in {o["feature_id"] for o in observations}
