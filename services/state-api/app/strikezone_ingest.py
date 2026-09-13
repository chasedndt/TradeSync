"""StrikeZone quant lab ingest: the host bridge posts ledger lines and changed documents here.

Signals are append-only in the lab and stored once. An outcome is updated if
the lab rewrites it. A document replaces the previous copy of its kind. The
bridge sends raw lines; they are normalised here by ``tradesync_core``, so
the rules that decide what a row means live in one place. Nothing posted
here carries authority: the rows are paper-only research.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tradesync_core.strikezone_ledger import normalize_outcome, normalize_signal, parse_ts

router = APIRouter(tags=["strikezone"])

DOCUMENT_KINDS = ("scorecards", "health", "methodology", "assumptions", "fleet_health")
MAX_ROWS_PER_POST = 2000

SIGNAL_FIELDS = (
    "signal_id", "asset", "timeframe", "direction", "strategy_id", "strategy_version", "methodology_version",
    "signal_at", "candle_close_at", "expiry_at", "entry_price", "invalidation_price", "target_price",
    "confidence", "regime", "analysis_eligible", "exclusion_reason",
)
OUTCOME_FIELDS = (
    "outcome_id", "signal_id", "asset", "timeframe", "direction", "methodology_version", "exit_reason", "exit_at",
    "holding_minutes", "entry_fill_price", "exit_fill_price", "quantity", "gross_pnl_usdc", "net_pnl_usdc",
    "fees_usdc", "slippage_usdc", "funding_usdc", "funding_coverage", "correlation_group_id", "analysis_eligible",
)


def _placeholders(fields: tuple[str, ...], casts: dict[str, str] | None = None) -> str:
    casts = casts or {}
    return ", ".join(f"${i}{casts.get(f, '')}" for i, f in enumerate(fields, 1))


SIGNAL_SQL = (
    f"INSERT INTO sz_signals ({', '.join(SIGNAL_FIELDS)}) "
    f"VALUES ({_placeholders(SIGNAL_FIELDS, {'regime': '::jsonb'})}) "
    "ON CONFLICT (signal_id) DO NOTHING"
)
OUTCOME_SQL = (
    f"INSERT INTO sz_outcomes ({', '.join(OUTCOME_FIELDS)}) VALUES ({_placeholders(OUTCOME_FIELDS)}) "
    "ON CONFLICT (outcome_id) DO UPDATE SET "
    + ", ".join(f"{f} = EXCLUDED.{f}" for f in OUTCOME_FIELDS if f != "outcome_id")
    + ", ingested_at = now()"
)
DOCUMENT_SQL = """
INSERT INTO sz_documents (kind, payload, source_updated_at, snapshot_at) VALUES ($1, $2::jsonb, $3, now())
ON CONFLICT (kind) DO UPDATE SET payload = EXCLUDED.payload, source_updated_at = EXCLUDED.source_updated_at, snapshot_at = now()
"""


class LabDocument(BaseModel):
    payload: dict[str, Any]
    source_updated_at: str | None = None


class LabIngest(BaseModel):
    signals: list[dict[str, Any]] = Field(default_factory=list)
    outcomes: list[dict[str, Any]] = Field(default_factory=list)
    documents: dict[str, LabDocument] = Field(default_factory=dict)


def signal_args(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(json.dumps(row[f]) if f == "regime" else row[f] for f in SIGNAL_FIELDS)


def outcome_args(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row[f] for f in OUTCOME_FIELDS)


def register(app, state) -> None:
    @router.post("/state/strikezone/ingest")
    async def ingest(body: LabIngest):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        if len(body.signals) > MAX_ROWS_PER_POST or len(body.outcomes) > MAX_ROWS_PER_POST:
            raise HTTPException(status_code=413, detail=f"at most {MAX_ROWS_PER_POST} rows per post")
        unknown = sorted(set(body.documents) - set(DOCUMENT_KINDS))
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown document kinds: {', '.join(unknown)}")
        signals = [row for row in (normalize_signal(raw) for raw in body.signals) if row]
        outcomes = [row for row in (normalize_outcome(raw) for raw in body.outcomes) if row]
        async with state.pool.acquire() as conn:
            async with conn.transaction():
                if signals:
                    await conn.executemany(SIGNAL_SQL, [signal_args(r) for r in signals])
                if outcomes:
                    await conn.executemany(OUTCOME_SQL, [outcome_args(r) for r in outcomes])
                for kind, document in body.documents.items():
                    await conn.execute(DOCUMENT_SQL, kind, json.dumps(document.payload), parse_ts(document.source_updated_at))
        return {
            "signals": {"received": len(body.signals), "valid": len(signals)},
            "outcomes": {"received": len(body.outcomes), "valid": len(outcomes)},
            "documents": sorted(body.documents),
        }

    app.include_router(router)
