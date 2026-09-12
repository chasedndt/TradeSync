"""The Thesis endpoint: the SOP's minimum valid thesis, assembled from evidence.

Slice 6 of the 2026-09-09 review sequence. ``GET /state/thesis?symbol=``
gathers what the system has measured for one symbol — the latest paper
verdict and its contributors, the entry-time regime, venue candles for anchor
levels, the evidence cards, the skill gate, the economic calendar and the
execution gate — and hands it to ``tradesync_core.thesis.build_thesis``.
The assembly is pure and tested; this module only fetches.

The direction is the paper signal's own. Confidence is coverage. Every line
names its source and age. Nothing here drafts prose with a model, and
nothing here can act.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Awaitable, Callable, Mapping

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.evidence_cards import compute_evidence_cards
from app.skill_gate import compute_skill_gate
from tradesync_core.thesis import build_thesis

router = APIRouter(tags=["thesis"])

CANDLE_INTERVAL = "15m"
CANDLE_BUCKET_S = 900
CANDLE_LIMIT = 100  # a day of 15m buckets plus slack

LATEST_SIGNAL_SQL = """
SELECT features, created_at FROM signals
WHERE symbol = $1 AND kind IN ('regime_paper_signal', 'regime_paper_refusal')
ORDER BY created_at DESC LIMIT 1
"""

ACTIVE_OPPORTUNITY_SQL = """
SELECT confluence, snapshot_ts, expires_at FROM opportunities
WHERE symbol = $1 AND status = 'new' AND dir IN ('LONG', 'SHORT')
  AND (expires_at IS NULL OR expires_at > now())
ORDER BY snapshot_ts DESC LIMIT 1
"""

LATEST_REGIME_SQL = """
SELECT r.regime, r.trailing_return_pct, r.lookback_minutes, r.computed_at
FROM opportunity_entry_regimes r
JOIN opportunities o ON o.id = r.opportunity_id
WHERE o.symbol = $1
ORDER BY o.snapshot_ts DESC LIMIT 1
"""


def execution_enabled() -> bool:
    return os.getenv("EXECUTION_ENABLED", "false").strip().lower() == "true"


def _read_from_decision(decision: Mapping[str, Any], fallback_at_ms: int, source: str) -> dict[str, Any]:
    """The paper read carried by a stored decision (a signal row or an opportunity's confluence)."""
    evidence = decision.get("evidence") or {}
    directional = evidence.get("directional") or {}
    admitted = bool(decision.get("admitted"))
    return {
        "direction": decision.get("direction") if admitted else "NONE",
        "admitted": admitted,
        "data_coverage": decision.get("data_coverage"),
        "directional_score": decision.get("directional_score"),
        "evaluated_at_ms": evidence.get("evaluated_at_ms") or fallback_at_ms,
        "contributors": list(directional.get("contributors") or []),
        "read_source": source,
    }


def _json(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else dict(value or {})


async def _latest_signal(conn, symbol: str) -> dict[str, Any] | None:
    """The current paper read: the live opportunity if one is open, else the latest verdict.

    The producer records a verdict every cycle and refuses whenever the side
    has not changed and the previous opportunity is still live, so the newest
    signal row is usually a refusal *while a read is still active*. The
    opportunity, with its expiry, is what says whether a read is current.
    """
    active = await conn.fetchrow(ACTIVE_OPPORTUNITY_SQL, symbol)
    if active:
        return _read_from_decision(
            _json(active["confluence"]), int(active["snapshot_ts"].timestamp() * 1000), "active paper opportunity"
        )
    row = await conn.fetchrow(LATEST_SIGNAL_SQL, symbol)
    if not row:
        return None
    return _read_from_decision(_json(row["features"]), int(row["created_at"].timestamp() * 1000), "latest verdict")


async def _latest_regime(conn, symbol: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(LATEST_REGIME_SQL, symbol)
    if not row:
        return None
    return {
        "regime": row["regime"],
        "trailing_return_pct": row["trailing_return_pct"],
        "lookback_minutes": row["lookback_minutes"],
        "computed_at_ms": int(row["computed_at"].timestamp() * 1000),
    }


async def _market(client: httpx.AsyncClient, base: str, path: str) -> dict[str, Any] | None:
    try:
        response = await client.get(f"{base}{path}", timeout=15.0)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        return None


Evidence = Callable[[str, str], Awaitable[tuple[list[dict[str, Any]], dict[str, Any]]]]


async def _no_evidence(venue: str, symbol: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return [], {}


async def gather_inputs(
    pool,
    symbol: str,
    market_data_url: str,
    calendar: Callable[[], Awaitable[dict[str, Any]]],
    evidence: Evidence = _no_evidence,
) -> dict[str, Any]:
    """Every input the assembler needs, fetched concurrently where independent."""
    async with pool.acquire() as conn:
        signal, regime = await _latest_signal(conn, symbol), await _latest_regime(conn, symbol)
    async with httpx.AsyncClient(trust_env=False) as client:
        candles, snapshots, gate, cards, context, live = await asyncio.gather(
            _market(client, market_data_url, f"/candles/hyperliquid/{symbol}?interval={CANDLE_INTERVAL}&limit={CANDLE_LIMIT}"),
            _market(client, market_data_url, "/snapshots"),
            compute_skill_gate(pool, symbol),
            compute_evidence_cards(pool, symbol),
            calendar(),
            evidence("hyperliquid", symbol),
        )
    feature_results = list(live[0]) if live else []
    snapshot = next((s for s in (snapshots or {}).get("snapshots", []) if s.get("symbol") == symbol), None)
    calendar_data = ((context or {}).get("providers") or {}).get("calendar") or {}
    events = (calendar_data.get("data") or {}).get("events") or []
    return {
        "signal": signal,
        "regime": regime,
        "candles": (candles or {}).get("candles") or [],
        "observation_age_ms": (snapshot or {}).get("snapshot_age_ms"),
        "source_status": {
            "status": "live" if snapshot and snapshot.get("snapshot_age_ms") is not None else "unavailable",
            "provider": "market-data",
            "venue": "hyperliquid",
        },
        "gate": gate.get("verdict") if gate else None,
        "cards": (cards or {}).get("cards") or [],
        "events": events,
        "contributors": (signal or {}).get("contributors") or [],
        "feature_results": feature_results,
    }


def register(
    app,
    state,
    *,
    market_data_url: str,
    calendar: Callable[[], Awaitable[dict[str, Any]]],
    evidence: Evidence = _no_evidence,
) -> None:
    @router.get("/state/thesis")
    async def thesis(symbol: str = Query("BTC-PERP")):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        inputs = await gather_inputs(state.pool, symbol, market_data_url, calendar, evidence)
        return build_thesis(
            symbol=symbol,
            now_ms=int(time.time() * 1000),
            regime=inputs["regime"],
            signal=inputs["signal"],
            source_status=inputs["source_status"],
            observation_age_ms=inputs["observation_age_ms"],
            candles=inputs["candles"],
            bucket_s=CANDLE_BUCKET_S,
            contributors=inputs["contributors"],
            cards=inputs["cards"],
            gate=inputs["gate"],
            events=inputs["events"],
            execution_enabled=execution_enabled(),
            feature_results=inputs["feature_results"],
        )

    app.include_router(router)
