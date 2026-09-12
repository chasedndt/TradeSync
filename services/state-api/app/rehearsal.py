"""Paper rehearsal: preview, refuse, journal — with the execution gate shut.

``/actions/preview`` consults the global execution gate first, so while
``EXECUTION_ENABLED`` is false it refuses every plan and records nothing. That
is correct for execution and useless for practice. This router runs the same
per-symbol risk rules, prices a simulated fill from the live mark and spread,
and writes the result to its own journal. It has no path to an execution
service: there is nothing in this module that could place an order.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tradesync_core.paper_rehearsal import RehearsalError, simulate_fill
from tradesync_core.risk import RiskGuardian

logger = logging.getLogger("state-api.rehearsal")
router = APIRouter(tags=["rehearsal"])

MARKET_DATA_URL = os.getenv("MARKET_DATA_URL", "http://market-data:8005")
# A fill is priced from a snapshot no older than this; beyond it the mark is
# history, not a price, and the rehearsal is refused rather than back-dated.
MAX_SNAPSHOT_AGE_MS = int(os.getenv("REHEARSAL_MAX_SNAPSHOT_AGE_MS", "30000"))


class RehearseRequest(BaseModel):
    opportunity_id: str
    size_usd: float = Field(..., gt=0, le=1_000_000)


def _row_to_dict(row) -> dict[str, Any]:
    out = dict(row)
    for key in ("plan", "risk_verdict", "fill", "market"):
        if isinstance(out.get(key), str):
            out[key] = json.loads(out[key])
    out["id"] = str(out["id"])
    out["opportunity_id"] = str(out["opportunity_id"])
    out["created_at"] = out["created_at"].isoformat()
    return out


async def _market(symbol: str) -> tuple[Optional[dict[str, Any]], str]:
    """The live snapshot for pricing, or the reason there is none."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{MARKET_DATA_URL}/snapshot/hyperliquid/{symbol}", timeout=3.0)
    except Exception as exc:
        return None, f"market-data unreachable: {type(exc).__name__}"
    if resp.status_code != 200:
        return None, f"market-data answered {resp.status_code} for {symbol}"
    return resp.json(), ""


def register(app, state) -> None:
    """Attach the router to the app with access to the shared DB pool."""

    @router.post("/actions/rehearse")
    async def rehearse(req: RehearseRequest):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        async with state.pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT * FROM paper_rehearsals WHERE opportunity_id = $1", req.opportunity_id
            )
            if existing:
                # A duplicate submission is the same rehearsal, not a second fill.
                return {"duplicate": True, "rehearsal": _row_to_dict(existing)}

            row = await conn.fetchrow("SELECT * FROM opportunities WHERE id = $1", req.opportunity_id)
            if not row:
                raise HTTPException(status_code=404, detail="Opportunity not found")
            opportunity = dict(row)
            symbol = opportunity["symbol"]
            direction = opportunity.get("dir")

            plan = {
                "action": "Simulated market order",
                "symbol": symbol,
                "direction": direction,
                "size_usd": req.size_usd,
                "venue": "hyperliquid",
                "mode": "rehearsal",
            }

            snapshot, why_not = await _market(symbol)
            micro = (snapshot or {}).get("microstructure")
            verdict = RiskGuardian().check(
                symbol=symbol,
                size_usd=req.size_usd,
                opportunity=opportunity,
                phase="rehearsal",
                microstructure=micro,
            )

            status, fill, market = "refused", None, {}
            reason = verdict.model_dump()
            if verdict.allowed:
                if snapshot is None:
                    reason = {**reason, "allowed": False, "reason_code": "MARKET_UNAVAILABLE",
                              "reason": f"Cannot price a fill: {why_not}. Nothing is assumed."}
                else:
                    ts = snapshot.get("ts")
                    # Age from the snapshot's own timestamp: the single-symbol
                    # route does not carry snapshot_age_ms, and a fill must
                    # not be priced from a mark whose age is unknown.
                    age = int(time.time() * 1000) - int(ts) if isinstance(ts, int) else None
                    if age is None:
                        ts = 0  # simulate_fill refuses a non-positive timestamp
                    mark = ((snapshot.get("price") or {}).get("mark_price_usd"))
                    spread = (micro or {}).get("spread_bps") or ((snapshot.get("orderbook") or {}).get("spread_bps"))
                    market = {"mark_price_usd": mark, "spread_bps": spread, "snapshot_ts": ts, "snapshot_age_ms": age}
                    if age is not None and age > MAX_SNAPSHOT_AGE_MS:
                        reason = {**reason, "allowed": False, "reason_code": "MARKET_STALE",
                                  "reason": f"Snapshot is {age / 1000:.0f}s old; a fill is not back-dated."}
                    else:
                        try:
                            fill = simulate_fill(direction, req.size_usd, float(mark or 0), spread, int(ts))
                            status = "rehearsed"
                        except (RehearsalError, TypeError, ValueError) as exc:
                            reason = {**reason, "allowed": False, "reason_code": "UNPRICEABLE", "reason": str(exc)}

            saved = await conn.fetchrow(
                """
                INSERT INTO paper_rehearsals
                    (opportunity_id, symbol, direction, size_usd, status, plan, risk_verdict, fill, market)
                VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb)
                RETURNING *
                """,
                req.opportunity_id, symbol, direction if direction in ("LONG", "SHORT") else "LONG",
                req.size_usd, status, json.dumps(plan), json.dumps(reason),
                json.dumps(fill) if fill else None, json.dumps(market),
            )
            return {"duplicate": False, "rehearsal": _row_to_dict(saved)}

    @router.get("/state/rehearsals")
    async def list_rehearsals(limit: int = 50):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        limit = max(1, min(limit, 200))
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM paper_rehearsals ORDER BY created_at DESC LIMIT $1", limit
            )
            counts = await conn.fetchrow(
                "SELECT count(*) FILTER (WHERE status='rehearsed') rehearsed, "
                "count(*) FILTER (WHERE status='refused') refused FROM paper_rehearsals"
            )
        return {
            "rehearsals": [_row_to_dict(r) for r in rows],
            "counts": dict(counts) if counts else {"rehearsed": 0, "refused": 0},
            "execution_authority": False,
            "note": "Every row is a simulation. No order, wallet or signer is involved.",
        }

    app.include_router(router)
