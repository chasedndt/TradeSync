"""The StrikeZone quant lab in Market Command: forward test, ledger, scorecards, health and charts.

Reads what the host bridge stored (see ``strikezone_ingest``) and the charts
it copied to a folder mounted read-only. Everything here is paper-only
research: nothing on these routes can promote a strategy, approve a trade or
reach a wallet.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.strikezone_queries import (
    COUNTS_SQL, CURVE_SQL, FRESHNESS_SQL, LAB_JOBS_SQL, LATEST_SQL, LATEST_TRADES_SQL, LEDGER_SQL, PENDING_SQL,
    RESULTS_SQL, TOTALS_SQL,
)
from tradesync_core.strikezone_ledger import ledger_status, num, planned_reward_risk
from tradesync_core.strikezone_scorecards import assumption_view, cohort_rows, scorecard_rows
from tradesync_core.strikezone_summary import equity_curve, forward_cells, health_view

router = APIRouter(tags=["strikezone"])

CHARTS_DIR = Path(os.getenv("STRIKEZONE_CHARTS_DIR", "/strikezone-charts"))
CHART_NAMES = {"signals": re.compile(r"^sig_[0-9a-f]{24}\.png$"), "outcomes": re.compile(r"^pout_[0-9a-f]{24}\.png$")}
CHART_LIST_TTL_S = 60
PAPER_NOTE = ("Paper-only research from the StrikeZone quant lab in the Hermes fleet. "
              "No record here can promote a strategy, approve a trade or reach a wallet.")
_chart_lists: dict[str, tuple[float, set[str]]] = {}


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _age_minutes(value: Any, now: datetime) -> float | None:
    return round((now - value).total_seconds() / 60, 1) if isinstance(value, datetime) else None


def chart_url(kind: str, ident: str | None) -> str | None:
    """The chart's route when the bridge has copied it; the folder listing is cached for a minute."""
    if not ident:
        return None
    cached = _chart_lists.get(kind)
    if cached is None or time.time() - cached[0] > CHART_LIST_TTL_S:
        try:
            names = set(os.listdir(CHARTS_DIR / kind))
        except OSError:
            names = set()
        cached = (time.time(), names)
        _chart_lists[kind] = cached
    name = f"{ident}.png"
    return f"/state/strikezone/charts/{kind}/{name}" if name in cached[1] else None


async def _document(conn, kind: str) -> tuple[dict[str, Any] | None, datetime | None]:
    row = await conn.fetchrow("SELECT payload, snapshot_at FROM sz_documents WHERE kind = $1", kind)
    if not row:
        return None, None
    payload = _json(row["payload"])
    return (payload if isinstance(payload, dict) else None), row["snapshot_at"]


async def _methodology(conn) -> tuple[str | None, dict[str, Any] | None]:
    doc, _ = await _document(conn, "methodology")
    if doc and doc.get("active_methodology_version"):
        return str(doc["active_methodology_version"]), doc
    row = await conn.fetchrow("SELECT methodology_version FROM sz_signals ORDER BY signal_at DESC LIMIT 1")
    return (row["methodology_version"] if row else None), doc


def ledger_row(r: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    has_outcome = r.get("outcome_id") is not None
    entry, stop, target = num(r.get("entry_price")), num(r.get("invalidation_price")), num(r.get("target_price"))
    return {
        "signal_id": r["signal_id"], "asset": r["asset"], "timeframe": r["timeframe"], "direction": r["direction"],
        "signal_at": _iso(r["signal_at"]), "expiry_at": _iso(r.get("expiry_at")), "confidence": num(r.get("confidence")),
        "entry_price": entry, "invalidation_price": stop, "target_price": target,
        "planned_reward_risk": planned_reward_risk(entry, stop, target),
        "regime": _json(r.get("regime")) or {},
        "status": ledger_status(r["direction"], r.get("expiry_at"), has_outcome, now),
        "chart_url": chart_url("signals", r["signal_id"]) if r["direction"] != "no_trade" else None,
        "outcome": {
            "outcome_id": r["outcome_id"], "exit_reason": r.get("exit_reason"), "exit_at": _iso(r.get("exit_at")),
            "holding_minutes": num(r.get("holding_minutes")), "net_pnl_usdc": num(r.get("net_pnl_usdc")),
            "gross_pnl_usdc": num(r.get("gross_pnl_usdc")), "fees_usdc": num(r.get("fees_usdc")),
            "slippage_usdc": num(r.get("slippage_usdc")), "funding_usdc": num(r.get("funding_usdc")),
            "entry_fill_price": num(r.get("entry_fill_price")), "exit_fill_price": num(r.get("exit_fill_price")),
            "chart_url": chart_url("outcomes", r["outcome_id"]),
        } if has_outcome else None,
    }


def register(app, state) -> None:
    def pool():
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        return state.pool

    @router.get("/state/strikezone/forward-test")
    async def forward_test():
        now = datetime.now(timezone.utc)
        async with pool().acquire() as conn:
            method, methodology = await _methodology(conn)
            assumptions, _ = await _document(conn, "assumptions")
            latest = await conn.fetch(LATEST_SQL, method)
            latest_trades = await conn.fetch(LATEST_TRADES_SQL, method)
            counts = await conn.fetch(COUNTS_SQL, method)
            results = await conn.fetch(RESULTS_SQL, method)
            pending = await conn.fetch(PENDING_SQL, method)
            curve_rows = await conn.fetch(CURVE_SQL, method)
            totals = await conn.fetchrow(TOTALS_SQL, method)
        states: dict[str, int] = {"open": 0, "resolving": 0, "overdue": 0}
        open_counts: dict[tuple[str, str], int] = {}
        for p in pending:
            status = ledger_status("long", p["expiry_at"], False, now)
            states[status] = states.get(status, 0) + 1
            if status == "open":
                key = (p["asset"], p["timeframe"])
                open_counts[key] = open_counts.get(key, 0) + 1
        assets, timeframes, cells = forward_cells(latest, latest_trades, counts, results, open_counts, now)
        totals = dict(totals) if totals else {}
        return {
            "schema_version": "strikezone_forward_test_v1",
            "methodology_version": method,
            "strategy_version": (methodology or {}).get("active_strategy_version"),
            "assets": assets, "timeframes": timeframes, "cells": cells,
            "totals": {
                "signals": int(totals.get("signals") or 0), "trades": int(totals.get("trades") or 0),
                "outcomes": int(totals.get("outcomes") or 0), **states,
                "last_signal_at": _iso(totals.get("last_signal_at")),
                "last_signal_age_minutes": _age_minutes(totals.get("last_signal_at"), now),
                "last_outcome_at": _iso(totals.get("last_outcome_at")),
            },
            "equity": equity_curve((r["exit_at"], r["net_pnl_usdc"]) for r in curve_rows),
            "paper_notional_usdc": num((assumptions or {}).get("paper_notional_usdc")),
            "note": PAPER_NOTE,
        }

    @router.get("/state/strikezone/ledger")
    async def ledger(
        asset: str | None = Query(None, max_length=12),
        timeframe: str | None = Query(None, max_length=6),
        view: str = Query("trades", pattern="^(trades|all|open|resolved|no_trade)$"),
        limit: int = Query(100, ge=1, le=500),
    ):
        now = datetime.now(timezone.utc)
        async with pool().acquire() as conn:
            method, _ = await _methodology(conn)
            rows = await conn.fetch(LEDGER_SQL, method, asset.upper() if asset else None, timeframe, view, limit)
        return {"schema_version": "strikezone_ledger_v1", "methodology_version": method,
                "filters": {"asset": asset, "timeframe": timeframe, "view": view, "limit": limit},
                "rows": [ledger_row(r, now) for r in rows], "note": PAPER_NOTE}

    @router.get("/state/strikezone/scorecards")
    async def scorecards():
        async with pool().acquire() as conn:
            doc, snapshot_at = await _document(conn, "scorecards")
            assumptions, _ = await _document(conn, "assumptions")
        doc = doc or {}
        return {"schema_version": "strikezone_scorecards_v1", "generated_at": doc.get("generated_at_utc"),
                "methodology_version": doc.get("active_methodology_version"), "snapshot_at": _iso(snapshot_at),
                "ranking_policy": doc.get("ranking_policy"), "analysis_summary": doc.get("analysis_summary"),
                "scorecards": scorecard_rows(doc), "regime": cohort_rows(doc),
                "assumptions": assumption_view(assumptions), "note": PAPER_NOTE}

    @router.get("/state/strikezone/health")
    async def lab_health():
        now = datetime.now(timezone.utc)
        async with pool().acquire() as conn:
            health, _ = await _document(conn, "health")
            fleet, _ = await _document(conn, "fleet_health")
            jobs = await conn.fetch(LAB_JOBS_SQL)
            fresh = await conn.fetchrow(FRESHNESS_SQL)
        fresh = dict(fresh) if fresh else {}
        delivered = max((v for v in (fresh.get("last_ingest_at"), fresh.get("last_document_at")) if v), default=None)
        return {**health_view(health, fleet, jobs, now), "schema_version": "strikezone_health_v1",
                "last_signal_at": _iso(fresh.get("last_signal_at")),
                "last_signal_age_minutes": _age_minutes(fresh.get("last_signal_at"), now),
                "bridge_delivered_at": _iso(delivered), "bridge_age_minutes": _age_minutes(delivered, now),
                "note": PAPER_NOTE}

    @router.get("/state/strikezone/charts/{kind}/{filename}")
    async def chart(kind: str, filename: str):
        pattern = CHART_NAMES.get(kind)
        if pattern is None or not pattern.match(filename):
            raise HTTPException(status_code=400, detail="charts are served by exact signal or outcome name only")
        path = CHARTS_DIR / kind / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="chart not copied yet")
        return FileResponse(str(path), media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})

    app.include_router(router)
