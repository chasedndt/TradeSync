"""Shared shapes for managed paper entry evidence: the source names, time and JSON helpers, missing markers.

A gathered item is ``{"source", "records", "reason", "coverage"}``; each record has an
``observed_at`` and a ``received_at`` in epoch seconds, and ``tradesync_core.paper_entry_evidence``
applies the entry cut-off to them.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Mapping

TIMEOUT_S = 3.0

SOURCES = {
    "opportunity": "opportunities",
    "scorer_verdict": "signals (regime paper scorer)",
    "features": "market-data /features: latest snapshot, each value at its metric read time",
    "horizon_measurement": "state-api /state/market/horizons",
    "resting_liquidity": "market_depth_snapshots and the entry order book",
    "liquidations": "market_liquidation_events",
    "open_interest": "market_open_interest",
    "funding": "market-data /funding-history (Hyperliquid settled hourly rates)",
    "thesis_edition": "thesis_editions",
}


def epoch(value: Any) -> float | None:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def decoded(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def missing(key: str, reason: str) -> dict[str, Any]:
    return {"source": SOURCES[key], "records": [], "reason": reason}


async def bounded(key: str, coroutine) -> dict[str, Any]:
    """The item a source produced, or a missing marker naming why it could not."""
    try:
        return await asyncio.wait_for(coroutine, TIMEOUT_S + 0.5)
    except Exception as exc:  # the entry records what failed; it never waits on a source
        return missing(key, f"unavailable: {type(exc).__name__}")


def opportunity_item(opportunity: Mapping[str, Any]) -> dict[str, Any]:
    at = epoch(opportunity.get("snapshot_ts"))
    links = decoded(opportunity.get("links")) or {}
    return {"source": SOURCES["opportunity"], "records": [{
        "id": str(opportunity.get("id")), "symbol": opportunity.get("symbol"), "dir": opportunity.get("dir"),
        "timeframe": opportunity.get("timeframe"), "bias": opportunity.get("bias"), "quality": opportunity.get("quality"),
        "status": opportunity.get("status"), "snapshot_ts": iso(opportunity.get("snapshot_ts")),
        "expires_at": iso(opportunity.get("expires_at")), "evidence_digest": links.get("evidence_digest"),
        "signal_id": str(opportunity.get("signal_id") or links.get("signal_id") or "") or None,
        "observed_at": at, "received_at": at, "received_basis": "created by TradeSync at snapshot_ts"}]}


def with_entry_book(item: Mapping[str, Any] | None, book: Mapping[str, Any], received_at: float) -> dict[str, Any]:
    """The resting-liquidity item with the entry order book's walls added as a record."""
    result = dict(item or missing("resting_liquidity", "no recorded book for this market before entry"))
    poll = book.get("poll_ts")
    record = {"id": "entry_book", "book": "hyperliquid_l2_book", "mid": book.get("mid_price"), "walls": book.get("walls"),
              "imbalance_1pct": book.get("imbalance_1pct"), "depth": book.get("depth"),
              "observed_at": poll / 1000 if isinstance(poll, (int, float)) else None, "received_at": received_at}
    result["records"] = [*result.get("records", []), record]
    result["reason"] = None
    return result
