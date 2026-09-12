"""The claims job records every extraction once and measures claims like opportunities."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_service_module  # noqa: E402

from tradesync_core.outcomes import HorizonOutcome, OpportunityOutcome  # noqa: E402

_job = load_service_module("core_scorer_app", "core-scorer", "claims_job")
_outcome_job = load_service_module("core_scorer_app", "core-scorer", "outcome_job")
T0 = datetime(2026, 9, 12, 19, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_extraction_records_claims_and_no_claims_exactly_once() -> None:
    rows = [
        {"id": "a", "source": "discord", "received_at": T0, "observed_at": None,
         "payload": {"schema_version": "discord_message_v1", "agent": "desk", "content": "BTC bearish below 77k", "embeds": []}},
        {"id": "b", "source": "chaseos", "received_at": T0, "observed_at": T0,
         "payload": {"schema_version": "hermes_job_output_v1", "agent": "resolver", "content": '{"status": "pass"}'}},
    ]
    recorded = []

    async def record(conn, qid, extractor, claims, reason):
        recorded.append((qid, extractor, [c.symbol + ":" + c.direction for c in claims], reason))

    with patch.object(_job, "unextracted_rows", AsyncMock(return_value=rows)), \
         patch.object(_job, "record_extraction", side_effect=record):
        counts = await _job.run_extraction_pass(MagicMock())
    assert counts == {"rows": 2, "claims": 1, "no_claim": 1}
    assert recorded[0] == ("a", "rule_v1", ["BTC-PERP:SHORT"], "")
    assert recorded[1][0] == "b" and recorded[1][2] == [] and recorded[1][3]


@pytest.mark.asyncio
async def test_measurement_uses_the_outcome_jobs_fetch_and_guards_and_stores_per_claim() -> None:
    pending = [{"id": "c1", "symbol": "BTC-PERP", "direction": "SHORT", "claimed_at": T0}]
    candles = [{"time": int(T0.timestamp()) + i * 60, "open": 100 - i * 0.01, "high": 100, "low": 99, "close": 100 - i * 0.01, "volume": 1}
               for i in range(-70, 300)]
    span = _outcome_job.FetchRange((int(T0.timestamp()) - 4000) * 1000, (int(T0.timestamp()) + 20000) * 1000)
    sc = _outcome_job.SymbolCandles(candles, [span], [], [])
    stored = []

    async def store(conn, outcome, symbol, direction):
        stored.append((outcome.opportunity_id, symbol, direction, [h.status for h in outcome.horizons]))

    with patch.object(_job, "pending_claims", AsyncMock(return_value=pending)), \
         patch.object(_job, "fetch_candles_for", AsyncMock(return_value=sc)), \
         patch.object(_job, "store_claim_outcome", side_effect=store), \
         patch.object(_job.time, "time", return_value=T0.timestamp() + 20000):
        counts = await _job.run_measurement_pass(MagicMock(), MagicMock())
    assert counts["claims"] == 1 and counts["measured"] == 3
    assert stored[0][:3] == ("c1", "BTC-PERP", "SHORT") and stored[0][3] == ["measured"] * 3
