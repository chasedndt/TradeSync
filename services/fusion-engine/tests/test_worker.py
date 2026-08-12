"""
Tests for fusion-engine worker — Phase 3F-1: exposure data wiring.

Focus areas:
  - fetch_exposure_data: correct structure on success
  - fetch_exposure_data: safe fallback (returns None) on all failure modes
  - process_message: passes exposure_data to compute_enhanced_score when available
  - process_message: falls back to None and still creates opportunity when positions unavailable
"""

import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_positions_response(positions: list) -> MagicMock:
    """Build a mock httpx response for /state/positions."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = positions
    return resp


def make_error_response(status_code: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {}
    return resp


SAMPLE_POSITIONS = [
    {
        "venue": "hyperliquid",
        "symbol": "BTC-PERP",
        "side": "LONG",
        "size_usd": 15000.0,
        "entry_price": 93000.0,
        "mark_price": 93500.0,
        "pnl_usd": 80.0,
        "leverage": 3.0,
        "timestamp": datetime.utcnow().isoformat(),
    },
    {
        "venue": "drift",
        "symbol": "ETH-PERP",
        "side": "SHORT",
        "size_usd": 5000.0,
        "entry_price": 2500.0,
        "mark_price": 2480.0,
        "pnl_usd": 40.0,
        "leverage": 2.0,
        "timestamp": datetime.utcnow().isoformat(),
    },
]


# ---------------------------------------------------------------------------
# fetch_exposure_data: happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_exposure_data_success():
    """Returns correct by_symbol and margin_utilization on 200 response."""
    from app.worker import fetch_exposure_data

    mock_resp = make_positions_response(SAMPLE_POSITIONS)

    with patch("app.worker.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await fetch_exposure_data("BTC-PERP")

    assert result is not None
    assert result["by_symbol"]["BTC-PERP"] == 15000.0
    assert result["by_symbol"]["ETH-PERP"] == 5000.0
    # total_notional=20000, account_equity=50000 → 20000/50000 = 0.4
    assert abs(result["margin_utilization"] - 0.4) < 0.001


@pytest.mark.asyncio
async def test_fetch_exposure_data_empty_positions():
    """Returns zero-exposure dict (not None) when no positions exist."""
    from app.worker import fetch_exposure_data

    mock_resp = make_positions_response([])

    with patch("app.worker.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await fetch_exposure_data("BTC-PERP")

    assert result is not None
    assert result["by_symbol"] == {}
    assert result["margin_utilization"] == 0.0


@pytest.mark.asyncio
async def test_fetch_exposure_data_multiple_venues_same_symbol():
    """size_usd is summed across venues for the same symbol."""
    from app.worker import fetch_exposure_data

    positions = [
        {"symbol": "BTC-PERP", "size_usd": 10000.0},
        {"symbol": "BTC-PERP", "size_usd": 5000.0},  # same symbol, second venue
    ]
    mock_resp = make_positions_response(positions)

    with patch("app.worker.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await fetch_exposure_data("BTC-PERP")

    assert result["by_symbol"]["BTC-PERP"] == 15000.0


@pytest.mark.asyncio
async def test_fetch_exposure_data_margin_utilization_capped_at_one():
    """margin_utilization never exceeds 1.0 even if notional > account equity."""
    from app.worker import fetch_exposure_data

    positions = [{"symbol": "BTC-PERP", "size_usd": 200000.0}]
    mock_resp = make_positions_response(positions)

    with patch("app.worker.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await fetch_exposure_data("BTC-PERP")

    assert result["margin_utilization"] == 1.0


# ---------------------------------------------------------------------------
# fetch_exposure_data: failure / fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_exposure_data_http_error_returns_none():
    """Returns None when /state/positions returns a non-200 status."""
    from app.worker import fetch_exposure_data

    mock_resp = make_error_response(503)

    with patch("app.worker.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await fetch_exposure_data("BTC-PERP")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_exposure_data_timeout_returns_none():
    """Returns None when the HTTP request raises any exception (timeout, connection error)."""
    from app.worker import fetch_exposure_data

    with patch("app.worker.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("connection timeout"))
        mock_client_cls.return_value = mock_client

        result = await fetch_exposure_data("BTC-PERP")

    assert result is None


# ---------------------------------------------------------------------------
# process_message: exposure data wiring
# ---------------------------------------------------------------------------

def make_signal_payload(symbol="BTC-PERP", score=3.0, event_ids=None):
    return json.dumps({
        "id": "sig-001",
        "symbol": symbol,
        "score": score,
        "confidence": 0.7,
        "direction": "LONG",
        "timeframe": "1m",
        "event_ids": event_ids or ["evt-001"],
    })


@pytest.mark.asyncio
async def test_process_message_passes_exposure_data_to_scorer():
    """When fetch_exposure_data succeeds, compute_enhanced_score receives the data."""
    from app import worker

    exposure = {"by_symbol": {"BTC-PERP": 12000.0}, "margin_utilization": 0.24}
    fake_score = MagicMock()
    fake_score.score_breakdown.final_score = 3.5
    fake_score.to_dict.return_value = {}

    msg_data = {"data": make_signal_payload()}

    with patch.object(worker, "fetch_market_snapshot", new=AsyncMock(return_value=None)), \
         patch.object(worker, "fetch_exposure_data", new=AsyncMock(return_value=exposure)), \
         patch.object(worker.enhanced_scorer, "compute_enhanced_score", return_value=fake_score) as mock_scorer, \
         patch.object(worker.redis_client.client, "xack", new=AsyncMock()), \
         patch("app.worker.db") as mock_db:

        mock_db.insert_opportunity = AsyncMock(return_value="opp-123")
        await worker.process_message("msg-001", msg_data)

    # The scorer must have been called with the exposure_data we provided.
    mock_scorer.assert_called_once()
    call_kwargs = mock_scorer.call_args.kwargs
    assert call_kwargs.get("exposure_data") == exposure, (
        "compute_enhanced_score must receive the fetched exposure_data, not None"
    )


@pytest.mark.asyncio
async def test_process_message_falls_back_to_none_when_positions_unavailable():
    """When fetch_exposure_data returns None, scorer is called with exposure_data=None
    and opportunity creation still succeeds."""
    from app import worker

    fake_score = MagicMock()
    fake_score.score_breakdown.final_score = 2.8
    fake_score.to_dict.return_value = {}

    msg_data = {"data": make_signal_payload()}

    with patch.object(worker, "fetch_market_snapshot", new=AsyncMock(return_value=None)), \
         patch.object(worker, "fetch_exposure_data", new=AsyncMock(return_value=None)), \
         patch.object(worker.enhanced_scorer, "compute_enhanced_score", return_value=fake_score) as mock_scorer, \
         patch.object(worker.redis_client.client, "xack", new=AsyncMock()), \
         patch("app.worker.db") as mock_db:

        mock_db.insert_opportunity = AsyncMock(return_value="opp-456")
        await worker.process_message("msg-002", msg_data)

    # Scorer is called with exposure_data=None — exposure penalty is 0, not an error.
    mock_scorer.assert_called_once()
    call_kwargs = mock_scorer.call_args.kwargs
    assert call_kwargs.get("exposure_data") is None

    # Opportunity was still created despite no exposure data.
    mock_db.insert_opportunity.assert_called_once()


@pytest.mark.asyncio
async def test_process_message_exposure_data_symbol_key_matches_normalized_symbol():
    """The symbol passed to fetch_exposure_data is the normalized form."""
    from app import worker

    fake_score = MagicMock()
    fake_score.score_breakdown.final_score = 2.5
    fake_score.to_dict.return_value = {}

    # Unnormalized symbol in the signal payload
    msg_data = {"data": make_signal_payload(symbol="BTC")}

    captured_symbol = []

    async def capture_fetch(symbol):
        captured_symbol.append(symbol)
        return None

    with patch.object(worker, "fetch_market_snapshot", new=AsyncMock(return_value=None)), \
         patch.object(worker, "fetch_exposure_data", new=capture_fetch), \
         patch.object(worker.enhanced_scorer, "compute_enhanced_score", return_value=fake_score), \
         patch.object(worker.redis_client.client, "xack", new=AsyncMock()), \
         patch("app.worker.db") as mock_db:

        mock_db.insert_opportunity = AsyncMock(return_value="opp-789")
        await worker.process_message("msg-003", msg_data)

    # normalize_symbol("BTC") → "BTC-PERP" per tradesync_core contract
    assert len(captured_symbol) == 1
    assert captured_symbol[0] == "BTC-PERP"


@pytest.mark.asyncio
async def test_process_message_below_threshold_does_not_fetch_exposure():
    """Signals below OPPORTUNITY_THRESHOLD are skipped before any upstream fetch."""
    from app import worker

    msg_data = {"data": make_signal_payload(score=0.5)}  # below threshold of 2.0

    mock_fetch = AsyncMock(return_value=None)

    with patch.object(worker, "fetch_exposure_data", new=mock_fetch), \
         patch.object(worker.redis_client.client, "xack", new=AsyncMock()):
        await worker.process_message("msg-004", msg_data)

    # Should not have fetched exposure for a sub-threshold signal.
    mock_fetch.assert_not_called()
