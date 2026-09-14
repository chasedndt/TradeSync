"""The opportunities list, /state/opportunities, and its lifecycle summary.

Status is reported and filtered as it is *now*: a ``new`` opportunity past its
TTL is ``expired`` (app/opportunity_lifecycle.py). The legacy /opps alias in
main.py calls the handler that ``register`` returns.
"""

import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app import background
from app.opportunity_lifecycle import (
    EFFECTIVE_STATUS_SQL,
    EXPIRES_AT_SQL,
    expiry_loop,
    quiet_summary,
    status_filter,
)
from tradesync_core import normalize_symbol

router = APIRouter()


def register(app, state, response_model):
    """Attach the route and return its handler for the legacy alias."""

    @router.get("/state/opportunities", response_model=List[response_model])
    async def get_opportunities(
        symbol: Optional[str] = None,
        status: str = "new",
        limit: int = Query(20, le=100)
    ):
        """Fetch opportunities."""
        if symbol:
            symbol = normalize_symbol(symbol)

        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")

        # "all" is a wildcard, not a stored status. Comparing it literally matched
        # no row and silently returned an empty list, which the Cockpit rendered as
        # "no scored opportunities available" even when opportunities existed.
        filters = []
        params: list = []
        if symbol:
            params.append(symbol)
            filters.append(f"symbol = ${len(params)}")
        if status and status.lower() != "all":
            # On the effective status, so "new" excludes rows past their TTL
            # and "expired" includes them before the expiry job has run.
            filters.append(status_filter(status, params))
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)

        try:
            async with state.pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                        SELECT id, symbol, timeframe, bias, quality, dir,
                               {EFFECTIVE_STATUS_SQL} AS status, snapshot_ts,
                               {EXPIRES_AT_SQL} AS expires_at, links, confluence
                        FROM opportunities
                        {where}
                        ORDER BY snapshot_ts DESC
                        LIMIT ${len(params)}
                    """,
                    *params,
                )

                return [
                    {
                        "id": str(r["id"]),
                        "symbol": r["symbol"],
                        "timeframe": r["timeframe"],
                        "bias": r["bias"],
                        "quality": r["quality"],
                        "dir": r["dir"],
                        "status": r["status"],
                        "snapshot_ts": r["snapshot_ts"],
                        "expires_at": r.get("expires_at"),
                        "links": json.loads(r["links"]) if isinstance(r["links"], str) else r["links"],
                        # Phase 3C: Include confluence with score_breakdown, execution_risk, warnings
                        "confluence": json.loads(r["confluence"]) if isinstance(r["confluence"], str) else (r["confluence"] or {})
                    }
                    for r in rows
                ]
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/state/opportunities/lifecycle")
    async def get_opportunity_lifecycle(window_minutes: int = Query(60, ge=5, le=1440)):
        """Live count, the last opportunity, and what the scorer refused in the window."""
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        async with state.pool.acquire() as conn:
            return await quiet_summary(conn, window_minutes)

    # Keeps stored status in step with the read path; see app/opportunity_lifecycle.py.
    background.add("opportunity_expiry", lambda: expiry_loop(state))

    app.include_router(router)
    return get_opportunities
