"""The entry-feature recorder writes once, marks absence explicitly, and defers on failure."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_service_module  # noqa: E402

_feat = load_service_module("core_scorer_app", "core-scorer", "outcome_features")

NOW_S = 1_800_000_000
OPP = "22222222-2222-2222-2222-222222222222"


def _row(opened_s: int, symbol: str = "BTC-PERP"):
    return {"id": OPP, "symbol": symbol, "snapshot_ts": datetime.fromtimestamp(opened_s, tz=timezone.utc)}


SPECS = {
    "tone": {"unit": "tone_score", "fresh_after_ms": 1_800_000, "provenance": "context_only",
             "source_authority": "context_only", "scoring_eligible": False},
    "prem": {"unit": "basis_points", "fresh_after_ms": 15_000, "provenance": "derived",
             "source_authority": "external_reference_venue", "scoring_eligible": True},
}


def _conn():
    conn = MagicMock()
    conn.execute = AsyncMock()
    return conn


@pytest.mark.asyncio
async def test_present_and_absent_readings_are_both_written_and_scoring_flag_is_recorded() -> None:
    opened_s = NOW_S - 3600
    series = {"tone": [{"ts": (opened_s - 60) * 1000, "value": -0.4}], "prem": []}

    async def fake_fetch(client, symbol, feature_id):
        return series[feature_id]

    conn = _conn()
    with patch.object(_feat, "missing_feature_opportunities", AsyncMock(return_value=[_row(opened_s)])), \
         patch.object(_feat, "load_candidates", return_value=("1.7.0", SPECS)), \
         patch.object(_feat, "fetch_series", side_effect=fake_fetch):
        counts = await _feat.record_entry_features(conn, 10, NOW_S)

    assert counts == {"present": 1, "absent": 1, "deferred": 0}
    writes = {c.args[2]: c.args for c in conn.execute.call_args_list}
    tone, prem = writes["tone"], writes["prem"]
    assert tone[4] == -0.4 and tone[12] == ""
    assert prem[4] is None and "before entry" in prem[12]
    assert tone[10] is False and prem[10] is True  # scoring_eligible_at_entry
    assert tone[11] == "1.7.0"


@pytest.mark.asyncio
async def test_an_unreadable_series_defers_the_whole_opportunity_not_half_of_it() -> None:
    async def fake_fetch(client, symbol, feature_id):
        return [{"ts": NOW_S * 1000 - 1000, "value": 1.0}] if feature_id == "tone" else None

    conn = _conn()
    with patch.object(_feat, "missing_feature_opportunities", AsyncMock(return_value=[_row(NOW_S - 60)])), \
         patch.object(_feat, "load_candidates", return_value=("1.7.0", SPECS)), \
         patch.object(_feat, "fetch_series", side_effect=fake_fetch):
        counts = await _feat.record_entry_features(conn, 10, NOW_S)

    assert counts["deferred"] == 1 and conn.execute.await_count == 0


@pytest.mark.asyncio
async def test_an_entry_older_than_the_store_is_closed_out_as_expired_without_a_fetch() -> None:
    fetch = AsyncMock()
    conn = _conn()
    with patch.object(_feat, "missing_feature_opportunities", AsyncMock(return_value=[_row(NOW_S - 10 * 86_400)])), \
         patch.object(_feat, "load_candidates", return_value=("1.7.0", SPECS)), \
         patch.object(_feat, "fetch_series", fetch):
        counts = await _feat.record_entry_features(conn, 10, NOW_S)

    assert counts == {"present": 0, "absent": 2, "deferred": 0}
    assert fetch.await_count == 0
    assert all(c.args[12] == _feat.EXPIRED for c in conn.execute.call_args_list)


@pytest.mark.asyncio
async def test_a_series_is_fetched_once_per_symbol_and_feature_across_the_batch() -> None:
    fetch = AsyncMock(return_value=[{"ts": (NOW_S - 100) * 1000, "value": 0.1}])
    rows = [_row(NOW_S - 50), {**_row(NOW_S - 40), "id": "33333333-3333-3333-3333-333333333333"}]
    with patch.object(_feat, "missing_feature_opportunities", AsyncMock(return_value=rows)), \
         patch.object(_feat, "load_candidates", return_value=("1.7.0", SPECS)), \
         patch.object(_feat, "fetch_series", fetch):
        await _feat.record_entry_features(_conn(), 10, NOW_S)
    assert fetch.await_count == 2  # two features, one symbol, two opportunities


def test_the_live_catalog_yields_the_six_directional_candidates() -> None:
    version, specs = _feat.load_candidates()
    assert version
    assert "gdelt_news_tone" in specs and "funding_spread_vs_binance_bps" in specs
    assert "coinbase_premium_bps" in specs and "hl_mark_price_usd" not in specs
