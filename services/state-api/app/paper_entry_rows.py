"""Entry evidence read from TradeSync's own tables, each row bounded by ``as_of`` and carrying when it was stored.

- scorer verdict: the ``signals`` row the opportunity links to (``created_at``), or the
  opportunity's own confluence when that row is gone;
- resting liquidity: the latest recorded aggregated book (``recorded_at``) and its walls near price;
- liquidations received in the hour before entry (``received_at``, first receipt);
- open interest: the latest recorded reading and the one an hour before it (``recorded_at``);
- thesis edition: the latest generated before entry. Its row keeps no insert time, so
  it counts as received when read here, the latest it can have arrived.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from app.paper_entry_facts import SOURCES, TIMEOUT_S, decoded, epoch, iso, missing
from tradesync_core.liquidity_heatmap import walls

LIQUIDATION_WINDOW_S = 3600
LIQUIDATION_ROWS = 500
RESTING_SIG_FIGS = 3


async def scorer_verdict(conn, opportunity: Mapping[str, Any]) -> dict[str, Any]:
    links = decoded(opportunity.get("links")) or {}
    signal_id = opportunity.get("signal_id") or links.get("signal_id")
    row = None
    if signal_id:
        row = await conn.fetchrow("SELECT id, created_at, agent, kind, confidence, dir, features FROM signals WHERE id=$1",
                                  uuid.UUID(str(signal_id)), timeout=TIMEOUT_S)
    verdict = decoded(row["features"]) if row else decoded(opportunity.get("confluence"))
    if not isinstance(verdict, dict) or not verdict:
        return missing("scorer_verdict", "no scorer verdict recorded for this opportunity")
    evidence = verdict.get("evidence") if isinstance(verdict.get("evidence"), dict) else {}
    created = epoch(row["created_at"]) if row else epoch(opportunity.get("snapshot_ts"))
    evaluated = evidence.get("evaluated_at_ms")
    return {"source": SOURCES["scorer_verdict"] if row else "opportunities.confluence", "records": [{
        "id": str(row["id"]) if row else None, "agent": row["agent"] if row else None,
        "kind": row["kind"] if row else None, "confidence": row["confidence"] if row else None,
        "admitted": verdict.get("admitted"), "direction": verdict.get("direction"),
        "weighted_score": verdict.get("weighted_score"), "directional_score": verdict.get("directional_score"),
        "data_coverage": verdict.get("data_coverage"), "directional_coverage": verdict.get("directional_coverage"),
        "rejection_reasons": verdict.get("rejection_reasons"), "risk_caps_applied": evidence.get("risk_caps_applied"),
        "missing_blocks": evidence.get("missing_blocks"), "catalog_version": evidence.get("catalog_version"),
        "rulebook_version": evidence.get("rulebook_version"), "evidence_digest": verdict.get("evidence_digest"),
        "contributing_features": [
            {"feature_id": f.get("feature_id"), "block": f.get("block"), "score": f.get("score"),
             "provenance": f.get("provenance"), "data_quality": f.get("data_quality"),
             "observed_at": f["observed_at_ms"] / 1000 if isinstance(f.get("observed_at_ms"), (int, float)) else None}
            for f in verdict.get("contributing_features") or [] if isinstance(f, dict)],
        "observed_at": evaluated / 1000 if isinstance(evaluated, (int, float)) else created, "received_at": created}]}


async def resting_liquidity(conn, symbol: str, as_of: float) -> dict[str, Any]:
    row = await conn.fetchrow(
        "SELECT observed_at, recorded_at, mid_price, bids, asks FROM market_depth_snapshots "
        "WHERE symbol=$1 AND n_sig_figs=$2 AND recorded_at <= to_timestamp($3) ORDER BY observed_at DESC LIMIT 1",
        symbol, RESTING_SIG_FIGS, as_of, timeout=TIMEOUT_S)
    if row is None or not row["mid_price"]:
        return missing("resting_liquidity", "no recorded book for this market before entry")
    return {"source": SOURCES["resting_liquidity"], "records": [{
        "id": "recorded_book", "book": "market_depth_snapshots", "n_sig_figs": RESTING_SIG_FIGS, "mid": row["mid_price"],
        "walls": walls(decoded(row["bids"]), decoded(row["asks"]), row["mid_price"]),
        "observed_at": epoch(row["observed_at"]), "observed_basis": "the minute the book was read, rounded down",
        "received_at": epoch(row["recorded_at"])}],
        "coverage": ("Largest resting bid below and ask above price within 5% in the latest recorded book aggregated to "
                     "3 significant figures, and the walls in the entry book. Orders can be cancelled: not executable "
                     "depth and not liquidation levels.")}


async def liquidations(conn, symbol: str, as_of: float) -> dict[str, Any]:
    rows = await conn.fetch(
        "SELECT source, event_id, event_time, received_at, position_side, price, size, notional_usd, price_kind "
        "FROM market_liquidation_events WHERE symbol=$1 AND event_time >= to_timestamp($2) AND received_at <= to_timestamp($3) "
        "ORDER BY event_time DESC LIMIT $4", symbol, as_of - LIQUIDATION_WINDOW_S, as_of, LIQUIDATION_ROWS, timeout=TIMEOUT_S)
    records = [{"id": f"{r['source']}:{r['event_id']}", "venue": r["source"], "side": r["position_side"], "price": r["price"],
                "size": r["size"], "notional_usd": r["notional_usd"], "price_kind": r["price_kind"],
                "observed_at": epoch(r["event_time"]), "received_at": epoch(r["received_at"])} for r in rows]
    return {"source": SOURCES["liquidations"], "records": records,
            "reason": None if records else "no liquidation received in the hour before entry",
            "coverage": (f"Liquidations received from Bybit and Binance USDT-M in the hour before entry, at most {LIQUIDATION_ROWS}, "
                         "recorded once a minute; not every market is covered by both. Hyperliquid publishes no market-wide "
                         "liquidation feed. Empty is not zero liquidations.")}


async def open_interest(conn, symbol: str, as_of: float) -> dict[str, Any]:
    query = ("SELECT observed_at, recorded_at, open_interest_usd, mark_price, oracle_price, funding_rate, oracle_premium_bps, "
             "volume_24h_usd FROM market_open_interest WHERE symbol=$1 AND recorded_at <= to_timestamp($2) AND observed_at <= $3 "
             "ORDER BY observed_at DESC LIMIT 1")
    latest = await conn.fetchrow(query, symbol, as_of, datetime.fromtimestamp(as_of, timezone.utc), timeout=TIMEOUT_S)
    if latest is None:
        return missing("open_interest", "no open interest recorded for this market before entry")
    earlier = await conn.fetchrow(query, symbol, as_of, latest["observed_at"] - timedelta(hours=1), timeout=TIMEOUT_S)
    records = [{"id": reading, "reading": reading, "open_interest_usd": r["open_interest_usd"], "mark_price": r["mark_price"],
                "oracle_price": r["oracle_price"], "predicted_funding_rate": r["funding_rate"],
                "oracle_premium_bps": r["oracle_premium_bps"], "volume_24h_usd": r["volume_24h_usd"],
                "observed_at": epoch(r["observed_at"]), "received_at": epoch(r["recorded_at"])}
               for reading, r in (("latest", latest), ("an hour earlier", earlier)) if r is not None]
    return {"source": SOURCES["open_interest"], "records": records,
            "coverage": "Hyperliquid open interest, mark, oracle and predicted funding, recorded once a minute."}


async def thesis_edition(conn, symbol: str, as_of: float) -> dict[str, Any]:
    row = await conn.fetchrow("SELECT id, edition, generated_at, trigger, headline, verdicts, schema_version FROM thesis_editions "
                              "WHERE generated_at <= to_timestamp($1) ORDER BY generated_at DESC LIMIT 1", as_of, timeout=TIMEOUT_S)
    read_at = time.time()
    if row is None:
        return missing("thesis_edition", "no thesis edition generated before entry")
    verdicts = decoded(row["verdicts"]) or {}
    return {"source": SOURCES["thesis_edition"], "records": [{
        "id": str(row["id"]), "edition": row["edition"], "generated_at": iso(row["generated_at"]), "trigger": row["trigger"],
        "headline": row["headline"], "verdict": verdicts.get(symbol), "schema_version": row["schema_version"],
        "observed_at": epoch(row["generated_at"]), "received_at": read_at,
        "received_basis": "read by the paper engine; an edition row keeps no insert time"}]}
