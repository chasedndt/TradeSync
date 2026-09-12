"""Evidence cards: what each candidate feature has earned, measured the same way.

Slice 5 of the 2026-09-09 review sequence. One card per implemented
directional feature in the catalog, scoring or context-only alike. A card
says how often the feature had a reading at entry, whether its sign called
the forward return better than a biased guesser at each horizon, in either
polarity, and whether any of that survived the hold-out. Every cell on every
card is Holm-adjusted together with every other, and with the same costs as
the skill gate.

This endpoint never changes the catalog. "Earned" is what the evidence
supports; granting ``scoring_eligible`` is an operator decision recorded in
the catalog and its change record.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.regime_lab import default_catalog_path
from app.skill_gate import COSTS
from tradesync_core.entry_features import candidate_features
from tradesync_core.feature_evidence import (
    FeatureOutcomeRow,
    assess_feature_cards,
    catalog_standing,
)
from tradesync_core.market_features import load_catalog
from tradesync_core.outcomes import DEFAULT_HORIZONS_MINUTES

router = APIRouter(tags=["outcomes"])

COVERAGE_SQL = """
SELECT feature_id,
       count(*) FILTER (WHERE value IS NOT NULL) AS present,
       count(*) FILTER (WHERE value IS NULL) AS absent
FROM opportunity_entry_features
WHERE ($1::text IS NULL OR symbol = $1)
GROUP BY feature_id
"""

ROWS_SQL = """
SELECT f.feature_id, x.symbol, x.opened_at, x.horizon_minutes, x.forward_return_pct, f.value
FROM opportunity_outcomes x
JOIN opportunity_entry_features f ON f.opportunity_id = x.opportunity_id
WHERE x.status = 'measured' AND x.forward_return_pct IS NOT NULL AND f.value IS NOT NULL
  AND ($1::text IS NULL OR x.symbol = $1)
"""

PENDING_SQL = """
SELECT count(*) FROM opportunities o
WHERE o.dir IN ('LONG','SHORT')
  AND NOT EXISTS (SELECT 1 FROM opportunity_entry_features f WHERE f.opportunity_id = o.id)
"""


def rows_to_feature_outcomes(rows) -> list[FeatureOutcomeRow]:
    return [
        FeatureOutcomeRow(
            feature_id=r["feature_id"],
            symbol=r["symbol"],
            opened_at_s=int(r["opened_at"].timestamp()),
            horizon_minutes=int(r["horizon_minutes"]),
            forward_return_pct=float(r["forward_return_pct"]),
            value=float(r["value"]),
        )
        for r in rows
    ]


def build_response(
    symbol: str | None,
    catalog_version: str,
    specs: dict[str, dict[str, Any]],
    rows: list[FeatureOutcomeRow],
    coverage: dict[str, dict[str, int]],
    pending: int,
    draws: int = 400,
) -> dict[str, Any]:
    feature_ids = list(specs.keys())
    cards, cells_assessed = assess_feature_cards(rows, feature_ids, costs=COSTS, draws=draws)
    out = []
    for card in cards:
        spec = specs.get(card.feature_id, {})
        d = card.to_dict()
        cov = coverage.get(card.feature_id, {"present": 0, "absent": 0})
        d.update(
            {
                "standing": catalog_standing(spec),
                "block": spec.get("block"),
                "unit": spec.get("unit"),
                "provenance": spec.get("provenance"),
                "source_authority": spec.get("source_authority"),
                "decision_role": spec.get("decision_role"),
                "entries_with_reading": int(cov["present"]),
                "entries_without_reading": int(cov["absent"]),
                "next_step": _next_step(card.earned, catalog_standing(spec)),
            }
        )
        out.append(d)
    return {
        "schema_version": "evidence_cards_v1",
        "symbol": symbol,
        "catalog_version": catalog_version,
        "horizons": list(DEFAULT_HORIZONS_MINUTES),
        "polarities": ["as_read", "inverted"],
        "cards": out,
        "cells_assessed_together": cells_assessed,
        "entries_pending": pending,
        "costs": {
            "round_trip_fee_pct": COSTS.round_trip_fee_pct,
            "spread_pct": COSTS.spread_pct,
            "slippage_pct": COSTS.slippage_pct,
            "total_pct": COSTS.total_pct,
            "source": COSTS.source,
        },
        "note": (
            "Each feature's sign at entry is scored as a directional call against the "
            "forward return, in both polarities. Cells across every card are Holm-adjusted "
            "together. 'earned' means positive skill that also held out of sample. Nothing "
            "here changes the catalog: a weight is granted only by operator decision."
        ),
    }


def _next_step(earned: bool, standing: str) -> str:
    if earned and standing == "context_only":
        return "operator may admit to scoring (catalog scoring_eligible) with a change record"
    if earned:
        return "admitted weight is supported by the evidence so far"
    if standing == "scoring":
        return "admitted weight is NOT yet supported by the evidence; review before relying on it"
    return "stays context-only; keeps recording"


async def compute_evidence_cards(pool, symbol: str | None) -> dict[str, Any]:
    """The full evidence-card reading; shared by the endpoint and the thesis."""
    catalog = load_catalog(default_catalog_path())
    specs = {f: catalog.features[f] for f in candidate_features(catalog.features)}
    async with pool.acquire() as conn:
        rows = await conn.fetch(ROWS_SQL, symbol)
        cov_rows = await conn.fetch(COVERAGE_SQL, symbol)
        pending = await conn.fetchval(PENDING_SQL)
    coverage = {r["feature_id"]: {"present": r["present"], "absent": r["absent"]} for r in cov_rows}
    return build_response(
        symbol, catalog.version, specs, rows_to_feature_outcomes(rows), coverage, int(pending or 0)
    )


def register(app, state) -> None:
    @router.get("/state/outcomes/evidence-cards")
    async def evidence_cards(symbol: str | None = None):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        return await compute_evidence_cards(state.pool, symbol)

    app.include_router(router)
