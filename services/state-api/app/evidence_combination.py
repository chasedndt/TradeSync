"""Evidence combination on the attributed outcomes: a research reading, never scoring.

GET /state/research/evidence-combination?horizon=60

Every decision the learning job attributed within its window is reduced to what
combination needs: when it opened, whether the market then rose or fell (the
stored signed return turned back into the market's move by the call's side),
the entry regime, the rulebook's directional score, and each candidate
feature's sign at entry (``opportunity_entry_features``).
``tradesync_core.evidence_combination`` fits each source's likelihood ratios
and their dependence on the older decisions and scores the combined probability
on the newest, against the base rate and the rulebook's calibrated score.

Served from the statistics cache, one reading per horizon, measured in a worker
thread. Read-only: two SELECTs and no write path. No scoring influence, no
rulebook, catalog or weight change, and no promotion.
"""

from __future__ import annotations

import asyncio
import math
from decimal import Decimal
from typing import Any, Iterable, Mapping

from fastapi import APIRouter, HTTPException, Query, Response

from app import learning_job, statistics_cache
from app.regime_lab import default_catalog_path
from app.statistics_cache import StatisticsCache
from tradesync_core.attribution_reason import label_for
from tradesync_core.evidence_combination import SCHEMA_VERSION, assess_combination
from tradesync_core.evidence_combination_data import Decision, call_from_reading
from tradesync_core.feature_evidence import catalog_standing
from tradesync_core.market_features import load_catalog
from tradesync_core.outcomes import DEFAULT_HORIZONS_MINUTES

router = APIRouter(tags=["research"])

DECISIONS_SQL = """
SELECT a.opportunity_id, a.symbol, a.direction, a.opened_at, a.signed_return_pct, a.entry_regime,
       CASE WHEN jsonb_typeof(o.confluence->'directional_score') = 'number'
            THEN (o.confluence->>'directional_score')::double precision END AS directional_score
FROM opportunity_attributions a
JOIN opportunities o ON o.id = a.opportunity_id
WHERE a.horizon_minutes = $1 AND a.opened_at > now() - make_interval(days => $2)
ORDER BY a.opened_at, a.opportunity_id
"""

READINGS_SQL = """
SELECT f.opportunity_id, f.feature_id, f.value
FROM opportunity_entry_features f
JOIN opportunity_attributions a ON a.opportunity_id = f.opportunity_id AND a.horizon_minutes = $1
WHERE a.opened_at > now() - make_interval(days => $2) AND f.value IS NOT NULL
"""

SIDES = {"LONG": 1, "SHORT": -1}
INPUTS = {
    "decisions": "opportunity_attributions, as the opportunity-learning job attributed them",
    "readings": "opportunity_entry_features: each candidate feature's reading at entry",
    "rulebook_score": "opportunities.confluence.directional_score",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def rows_to_decisions(decision_rows: Iterable[Mapping[str, Any]], reading_rows: Iterable[Mapping[str, Any]]) -> list[Decision]:
    """Attributed rows and entry readings joined into decisions; a row with no side or return is skipped."""
    calls: dict[str, dict[str, int]] = {}
    for row in reading_rows:
        call = call_from_reading(_number(row["value"]))
        if call is not None:
            calls.setdefault(str(row["opportunity_id"]), {})[str(row["feature_id"])] = call
    decisions = []
    for row in decision_rows:
        side, signed = SIDES.get(row["direction"]), _number(row["signed_return_pct"])
        if side is None or signed is None:
            continue
        key = str(row["opportunity_id"])
        decisions.append(Decision(
            key=key,
            symbol=str(row["symbol"]),
            opened_at_s=int(row["opened_at"].timestamp()),
            forward_return_pct=signed * side,
            regime=str(row["entry_regime"] or "unknown"),
            calls=calls.get(key, {}),
            rulebook_score=_number(row["directional_score"]),
        ))
    return decisions


def source_details() -> dict[str, Mapping[str, Any]]:
    """Catalog entries by feature id; empty when the catalog cannot be read (labels then fall back to ids)."""
    try:
        return dict(load_catalog(default_catalog_path()).features)
    except Exception:  # labels are presentation; a missing catalog must not block the reading
        return {}


def build_response(
    horizon_minutes: int,
    decision_rows: Iterable[Mapping[str, Any]],
    reading_rows: Iterable[Mapping[str, Any]],
    *,
    cost_pct: float = learning_job.COST_PCT,
    days: int = learning_job.WINDOW_DAYS,
    details: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """CPU-bound and free of I/O apart from reading the catalog file; runs in a worker thread."""
    report = assess_combination(rows_to_decisions(decision_rows, reading_rows), horizon_minutes, cost_pct=cost_pct)
    details = source_details() if details is None else details
    for source in report["sources"]:
        spec = details.get(source["source_id"])
        source["label"] = label_for(source["source_id"])
        source["standing"] = catalog_standing(spec) if spec is not None else "not_in_catalog"
        source["block"] = spec.get("block") if spec is not None else None
    return {**report, "days": days, "inputs": INPUTS}


async def compute_evidence_combination(pool, horizon_minutes: int) -> dict[str, Any]:
    async with pool.acquire() as conn:
        decision_rows = await conn.fetch(DECISIONS_SQL, horizon_minutes, learning_job.WINDOW_DAYS)
        reading_rows = await conn.fetch(READINGS_SQL, horizon_minutes, learning_job.WINDOW_DAYS)
    return await asyncio.to_thread(build_response, horizon_minutes, decision_rows, reading_rows)


def horizon_label(minutes: int) -> str:
    return f"{minutes // 60}h" if minutes % 60 == 0 else f"{minutes}m"


def _cache(horizon_minutes: int) -> StatisticsCache:
    return StatisticsCache(
        f"evidence_combination_{horizon_minutes}m",
        f"The {horizon_label(horizon_minutes)} evidence combination",
        lambda pool, _market: compute_evidence_combination(pool, horizon_minutes),
        SCHEMA_VERSION,
    )


CACHES: dict[int, StatisticsCache] = {horizon: _cache(horizon) for horizon in DEFAULT_HORIZONS_MINUTES}


def register(app, state) -> None:
    for cache in CACHES.values():
        statistics_cache.register(cache, state)

    @router.get("/state/research/evidence-combination")
    async def evidence_combination(response: Response, horizon: int = Query(60)):
        """Served from the statistics cache: 200 with computed_at, or 202 while first measured."""
        cache = CACHES.get(horizon)
        if cache is None:
            allowed = ", ".join(str(h) for h in CACHES)
            raise HTTPException(status_code=422, detail=f"horizon must be one of {allowed} minutes")
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        return cache.respond(state.pool, None, response)

    app.include_router(router)
