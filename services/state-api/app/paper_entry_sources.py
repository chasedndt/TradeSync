"""What a managed paper entry considers, gathered before its entry quote, each fact with its observed and received times.

Every source is bounded and independent: a slow or failed one becomes a missing
marker with its reason, never a dependency for opening. Rows from TradeSync's own
tables come from ``paper_entry_rows``; answers over HTTP, gathered here, carry the time
this service received them.

``as_of`` bounds every database query, so a replay at a past entry reads only rows
stored by then; answers fetched now were received now and fall after such an entry,
where ``tradesync_core.paper_entry_evidence`` excludes them.

The Bybit receipt and Hyperliquid book-history snapshots (``external_context``) keep
their earlier shape, which the source comparison reads.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Mapping

import httpx

from app import paper_entry_rows as rows
from app.entry_context import book_snapshot, liquidation_snapshot
from app.horizons import PARTS
from app.paper_entry_facts import SOURCES, TIMEOUT_S, bounded, epoch, missing, opportunity_item, with_entry_book

__all__ = ["gather", "with_entry_book"]

FUNDING_WINDOW_S = 24 * 3600


async def features(client: httpx.AsyncClient, market_data_url: str, symbol: str) -> dict[str, Any]:
    response = await client.get(f"{market_data_url}/features/hyperliquid/{symbol}")
    received = time.time()
    response.raise_for_status()
    records = [{"id": row.get("source_event_id"), "feature_id": row.get("feature_id"), "value": row.get("value"),
                "timeframe": row.get("timeframe"), "observed_at": row["observed_at_ms"] / 1000, "received_at": received}
               for row in response.json().get("observations") or []
               if isinstance(row, dict) and isinstance(row.get("observed_at_ms"), (int, float))]
    return {"source": SOURCES["features"], "records": records, "reason": None if records else "no feature observations in the latest snapshot"}


async def horizon_measurement(client: httpx.AsyncClient, self_url: str, symbol: str) -> dict[str, Any]:
    response = await client.get(f"{self_url}/state/market/horizons", params={"symbol": symbol})
    received = time.time()
    if response.status_code in (409, 502, 503):
        return missing("horizon_measurement", f"no measurement available (HTTP {response.status_code})")
    response.raise_for_status()
    page = response.json()
    outlook = page.get("outlook") or {}
    records = []
    for part, measured_at in (page.get("computed_at") or {}).items():
        reads = [{"key": h.get("key"), "label": h.get("label"), "band": h.get("band"), "available": h.get("available"),
                  "lean": h.get("lean"), "trend": (h.get("trend") or {}).get("state"),
                  "momentum": (h.get("momentum") or {}).get("state"), "implied_range": h.get("implied_range")}
                 for h in outlook.get("horizons") or [] if h.get("interval") in PARTS.get(part, ())]
        bands = {read["band"] for read in reads}
        records.append({"id": part, "part": part, "measured_at": measured_at, "observed_at": epoch(measured_at),
                        "received_at": received, "horizons": reads,
                        "bands": [b for b in outlook.get("bands") or [] if b.get("band") in bands]})
    reason = "; ".join((page.get("errors") or {}).values()) or None
    return {"source": SOURCES["horizon_measurement"], "records": records,
            "reason": reason or (None if records else "no measurement yet for this market")}


async def funding_rows(client: httpx.AsyncClient, market_data_url: str, symbol: str, as_of: float) -> dict[str, Any]:
    response = await client.get(f"{market_data_url}/funding-history/hyperliquid/{symbol}",
                                params={"start_ms": int((as_of - FUNDING_WINDOW_S) * 1000), "end_ms": int(as_of * 1000)})
    received = time.time()
    response.raise_for_status()
    records = [{"id": str(int(row[0])), "funding_rate": row[1], "premium": row[2] if len(row) > 2 else None,
                "observed_at": float(row[0]), "received_at": received}
               for row in response.json().get("rows") or []
               if isinstance(row, list) and len(row) >= 2 and all(isinstance(v, (int, float)) for v in row[:2])]
    return {"source": SOURCES["funding"], "records": records,
            "reason": None if records else "no settled funding rows in the day before entry",
            "coverage": "Settled hourly rates for the 24 hours before entry."}


async def external_context(client: httpx.AsyncClient, market_data_url: str, symbol: str) -> dict[str, Any]:
    """Bybit liquidation receipts and Hyperliquid book history, each cut off when it was received."""
    async def get(path: str) -> Any:
        response = await client.get(market_data_url + path)
        response.raise_for_status()
        return response.json()

    try:
        payload = await asyncio.wait_for(get("/liquidation-context/" + symbol), timeout=TIMEOUT_S)
        cutoff = time.time()
        if payload.get("symbol") != symbol or payload.get("venue") != "bybit":
            raise ValueError("Context source or symbol mismatch")
        bybit = liquidation_snapshot(payload, cutoff)
    except Exception as exc:
        bybit = {"status": "unavailable", "reason": type(exc).__name__, "cutoff": time.time(), "events": [],
                 "authority": "context_only", "scoring_influence": False}
    try:
        history = await asyncio.wait_for(get("/book-history/" + symbol), timeout=TIMEOUT_S)
        book_history = book_snapshot(history, time.time(), symbol)
    except Exception as exc:
        book_history = {"status": "unavailable", "reason": type(exc).__name__, "cutoff": time.time(), "samples": [],
                        "authority": "context_only", "scoring_influence": False}
    return {"bybit_liquidations": bybit, "hyperliquid_book_history": book_history}


async def gather(pool, market_data_url: str, self_url: str, opportunity: Mapping[str, Any],
                 *, as_of: float | None = None) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Every evidence item and the external context for ``opportunity``, database rows bounded by ``as_of``."""
    as_of = time.time() if as_of is None else as_of
    symbol = opportunity["symbol"]
    items: dict[str, dict[str, Any]] = {"opportunity": opportunity_item(opportunity)}
    async with httpx.AsyncClient(timeout=TIMEOUT_S, trust_env=False) as client:
        answers = asyncio.gather(
            bounded("features", features(client, market_data_url, symbol)),
            bounded("horizon_measurement", horizon_measurement(client, self_url, symbol)),
            bounded("funding", funding_rows(client, market_data_url, symbol, as_of)),
            external_context(client, market_data_url, symbol))
        try:
            async with pool.acquire() as conn:
                items["scorer_verdict"] = await bounded("scorer_verdict", rows.scorer_verdict(conn, opportunity))
                items["resting_liquidity"] = await bounded("resting_liquidity", rows.resting_liquidity(conn, symbol, as_of))
                items["liquidations"] = await bounded("liquidations", rows.liquidations(conn, symbol, as_of))
                items["open_interest"] = await bounded("open_interest", rows.open_interest(conn, symbol, as_of))
                items["thesis_edition"] = await bounded("thesis_edition", rows.thesis_edition(conn, symbol, as_of))
        finally:
            items["features"], items["horizon_measurement"], items["funding"], context = await answers
    return items, context
