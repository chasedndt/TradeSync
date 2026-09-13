"""The harness pass asks once per row, checks every proposal, and defers on failure."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_service_module  # noqa: E402

_h = load_service_module("core_scorer_app", "core-scorer", "claims_harness")
T0 = datetime(2026, 9, 13, 1, 0, tzinfo=timezone.utc)
POST = "Desk view: BTC is bearish below 77.3k into the weekend; ETH constructive."


def _row(qid="q1", content=POST):
    return {"id": qid, "source": "discord", "received_at": T0, "observed_at": T0,
            "payload": {"schema_version": "discord_message_v1", "agent": "sz-market-thesis-desk", "content": content, "embeds": []}}


@pytest.mark.asyncio
async def test_a_verbatim_proposal_becomes_a_claim_and_the_receipt_is_kept() -> None:
    answer = {"content": '[{"symbol": "BTC", "stance": "bearish", "horizon_minutes": 240, "quote": "bearish below 77.3k"}]',
              "receipt": {"content_digest": "abc"}}
    recorded = []

    async def record(conn, qid, extractor, claims, reason, digest):
        recorded.append((qid, extractor, [(c.symbol, c.direction, c.source_id) for c in claims], reason, digest))

    with patch.object(_h, "harness_candidates", AsyncMock(return_value=[_row()])), \
         patch.object(_h, "harness_available", AsyncMock(return_value=True)), \
         patch.object(_h, "ask", AsyncMock(return_value=answer)), \
         patch.object(_h, "record_harness_extraction", side_effect=record), \
         patch.object(_h, "HARNESS_CLAIMS_ENABLED", True):
        counts = await _h.run_harness_pass(MagicMock(), MagicMock())
    assert counts["asked"] == 1 and counts["claims"] == 1
    assert recorded == [("q1", "harness_v1", [("BTC-PERP", "SHORT", "sz-market-thesis-desk")], "", "abc")]


@pytest.mark.asyncio
async def test_an_invented_quote_is_recorded_as_no_claim_with_the_reason() -> None:
    answer = {"content": '[{"symbol": "BTC", "stance": "bullish", "horizon_minutes": 60, "quote": "very bullish"}]', "receipt": {"content_digest": "d"}}
    recorded = []

    async def record(conn, qid, extractor, claims, reason, digest):
        recorded.append((len(claims), reason))

    with patch.object(_h, "harness_candidates", AsyncMock(return_value=[_row()])), \
         patch.object(_h, "harness_available", AsyncMock(return_value=True)), \
         patch.object(_h, "ask", AsyncMock(return_value=answer)), \
         patch.object(_h, "record_harness_extraction", side_effect=record), \
         patch.object(_h, "HARNESS_CLAIMS_ENABLED", True):
        counts = await _h.run_harness_pass(MagicMock(), MagicMock())
    assert counts["no_claim"] == 1 and recorded[0][0] == 0 and "not found verbatim" in recorded[0][1]


@pytest.mark.asyncio
async def test_a_boundary_refusal_is_recorded_and_a_transport_failure_defers() -> None:
    recorded = []

    async def record(conn, qid, extractor, claims, reason, digest):
        recorded.append((qid, reason))

    with patch.object(_h, "harness_candidates", AsyncMock(return_value=[_row("a"), _row("b")])), \
         patch.object(_h, "harness_available", AsyncMock(return_value=True)), \
         patch.object(_h, "ask", AsyncMock(side_effect=[{"refused": True}, None])), \
         patch.object(_h, "record_harness_extraction", side_effect=record), \
         patch.object(_h, "HARNESS_CLAIMS_ENABLED", True):
        counts = await _h.run_harness_pass(MagicMock(), MagicMock())
    assert counts["refused"] == 1 and counts["deferred"] == 1
    assert recorded[0][0] == "a" and recorded[0][1].startswith("harness answer refused at the boundary")  # "b" left for a later pass


@pytest.mark.asyncio
async def test_nothing_is_asked_when_the_harness_is_not_live() -> None:
    ask = AsyncMock()
    with patch.object(_h, "harness_candidates", AsyncMock(return_value=[_row()])), \
         patch.object(_h, "harness_available", AsyncMock(return_value=False)), \
         patch.object(_h, "ask", ask), patch.object(_h, "HARNESS_CLAIMS_ENABLED", True):
        counts = await _h.run_harness_pass(MagicMock(), MagicMock())
    assert counts["asked"] == 0 and ask.await_count == 0


def test_post_text_reads_embeds_like_the_rule_extractor() -> None:
    p = {"schema_version": "discord_message_v1", "content": "a", "embeds": [{"title": "t", "description": "d", "fields": [{"name": "n", "value": "v"}]}]}
    assert _h.post_text(p) == "a\nt\nd\nn: v"
