"""Database access for opportunity learning: attributions, decision records, proposals.

Kept apart from the job and the routes so the queries that decide "what still
needs attributing" and "what the walk-forward learns from" can be read alone.
"""

from __future__ import annotations

import json
from typing import Any

from tradesync_core.attribution import SCHEMA_VERSION as ATTRIBUTION_SCHEMA, MeasuredHorizon
from tradesync_core.walk_forward import DecisionRecord


def as_json(value: Any) -> Any:
    """asyncpg returns jsonb as text unless a codec is set."""
    return json.loads(value) if isinstance(value, (str, bytes)) else value


# A measured outcome needs (re-)attributing when it has no attribution, when it
# was re-measured after the attribution, when its entry regime arrived later,
# or when the cost or attribution schema changed.
CANDIDATES_SQL = """
SELECT x.opportunity_id, x.horizon_minutes, x.symbol, x.direction, x.opened_at, x.measured_at,
       x.signed_return_pct, x.max_favourable_pct, x.max_adverse_pct,
       o.confluence, r.regime
FROM opportunity_outcomes x
JOIN opportunities o ON o.id = x.opportunity_id
LEFT JOIN opportunity_entry_regimes r ON r.opportunity_id = x.opportunity_id
LEFT JOIN opportunity_attributions a
       ON a.opportunity_id = x.opportunity_id AND a.horizon_minutes = x.horizon_minutes
WHERE x.status = 'measured' AND x.signed_return_pct IS NOT NULL
  AND x.direction IN ('LONG', 'SHORT')
  AND (a.opportunity_id IS NULL
       OR a.outcome_measured_at < x.measured_at
       OR a.cost_pct <> $1
       OR a.schema_version <> $2
       OR (a.entry_regime = 'unknown' AND r.regime IS NOT NULL AND r.regime <> 'unknown'))
ORDER BY x.opened_at ASC, x.opportunity_id, x.horizon_minutes
LIMIT $3
"""

UPSERT_SQL = """
INSERT INTO opportunity_attributions (
    opportunity_id, horizon_minutes, symbol, direction, opened_at, classification, reason,
    signed_return_pct, net_return_pct, cost_pct, max_favourable_pct, max_adverse_pct,
    entry_regime, features, blocks, rulebook_version, rulebook_digest,
    outcome_measured_at, schema_version, attributed_at
) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, $15::jsonb,
          $16, $17, $18, $19, now())
ON CONFLICT (opportunity_id, horizon_minutes) DO UPDATE SET
    classification = EXCLUDED.classification, reason = EXCLUDED.reason,
    signed_return_pct = EXCLUDED.signed_return_pct, net_return_pct = EXCLUDED.net_return_pct,
    cost_pct = EXCLUDED.cost_pct, max_favourable_pct = EXCLUDED.max_favourable_pct,
    max_adverse_pct = EXCLUDED.max_adverse_pct, entry_regime = EXCLUDED.entry_regime,
    features = EXCLUDED.features, blocks = EXCLUDED.blocks,
    rulebook_version = EXCLUDED.rulebook_version, rulebook_digest = EXCLUDED.rulebook_digest,
    outcome_measured_at = EXCLUDED.outcome_measured_at, schema_version = EXCLUDED.schema_version,
    attributed_at = now()
"""


async def attribution_candidates(conn, cost_pct: float, batch: int) -> list[dict[str, Any]]:
    rows = await conn.fetch(CANDIDATES_SQL, cost_pct, ATTRIBUTION_SCHEMA, batch)
    return [dict(row) for row in rows]


async def upsert_attribution(conn, attribution: dict[str, Any], opened_at, measured_at) -> None:
    await conn.execute(
        UPSERT_SQL,
        attribution["opportunity_id"], attribution["horizon_minutes"], attribution["symbol"],
        attribution["direction"], opened_at, attribution["classification"], attribution["reason"],
        attribution["signed_return_pct"], attribution["net_return_pct"], attribution["cost_pct"],
        attribution["max_favourable_pct"], attribution["max_adverse_pct"], attribution["entry_regime"],
        json.dumps(attribution["features"]), json.dumps(attribution["blocks"]),
        attribution["rulebook_version"], attribution["rulebook_digest"], measured_at,
        attribution["schema_version"],
    )


async def decision_records(conn, days: int) -> list[DecisionRecord]:
    """Every measured opportunity in the window, with its stored decision and outcomes."""

    rows = await conn.fetch(
        """
        SELECT o.id, o.symbol, o.dir, o.snapshot_ts, o.confluence, r.regime,
               x.horizon_minutes, x.signed_return_pct, x.max_favourable_pct, x.max_adverse_pct
        FROM opportunities o
        JOIN opportunity_outcomes x ON x.opportunity_id = o.id
        LEFT JOIN opportunity_entry_regimes r ON r.opportunity_id = o.id
        WHERE o.dir IN ('LONG', 'SHORT') AND x.status = 'measured' AND x.signed_return_pct IS NOT NULL
          AND o.snapshot_ts > now() - make_interval(days => $1)
        ORDER BY o.snapshot_ts, o.id, x.horizon_minutes
        """,
        days,
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row["id"])
        entry = grouped.setdefault(key, {"row": row, "horizons": {}})
        entry["horizons"][int(row["horizon_minutes"])] = MeasuredHorizon(
            int(row["horizon_minutes"]), float(row["signed_return_pct"]),
            row["max_favourable_pct"], row["max_adverse_pct"],
        )
    return [
        DecisionRecord(
            opportunity_id=key, symbol=entry["row"]["symbol"], direction=entry["row"]["dir"],
            opened_at_s=int(entry["row"]["snapshot_ts"].timestamp()),
            decision=as_json(entry["row"]["confluence"]) or {},
            entry_regime=entry["row"]["regime"] or "unknown", horizons=entry["horizons"],
        )
        for key, entry in grouped.items()
    ]


def attribution_row(row: Any) -> dict[str, Any]:
    """A stored attribution in the shape the aggregation functions read."""

    out = dict(row)
    out["opportunity_id"] = str(out["opportunity_id"])
    out["opened_at_s"] = int(out["opened_at"].timestamp())
    out["opened_at"] = out["opened_at"].isoformat()
    for key in ("outcome_measured_at", "attributed_at"):
        if out.get(key) is not None:
            out[key] = out[key].isoformat()
    out["features"] = as_json(out.get("features")) or []
    out["blocks"] = as_json(out.get("blocks")) or []
    return out


async def attributions_since(conn, days: int, horizon: int | None = None) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT * FROM opportunity_attributions
        WHERE opened_at > now() - make_interval(days => $1) AND ($2::int IS NULL OR horizon_minutes = $2)
        ORDER BY opened_at, opportunity_id, horizon_minutes
        """,
        days, horizon,
    )
    return [attribution_row(row) for row in rows]


async def insert_proposal(conn, proposal: dict[str, Any]) -> str:
    """Supersede the open proposal for this rulebook, then insert the new one. Call in a transaction."""

    await conn.execute(
        """
        UPDATE learning_proposals SET status = 'superseded', decided_at = now(), decided_by = 'learning-job',
               decision_note = 'superseded by a newer proposal'
        WHERE rulebook_id = $1 AND status = 'proposed'
        """,
        proposal["rulebook_id"],
    )
    return str(await conn.fetchval(
        """
        INSERT INTO learning_proposals (rulebook_id, rulebook_horizon, target_horizon_minutes, parent_version,
            parent_digest, version, config_digest, config, hypothesis, weights, evidence, replay, cost_pct, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10::jsonb, $11::jsonb, $12::jsonb, $13, $14)
        RETURNING id
        """,
        proposal["rulebook_id"], proposal["rulebook_horizon"], proposal["target_horizon_minutes"],
        proposal["parent_version"], proposal["parent_digest"], proposal["version"], proposal["config_digest"],
        json.dumps(proposal["config"]), proposal["hypothesis"], json.dumps(proposal["weights"]),
        json.dumps(proposal["evidence"]), json.dumps(proposal["replay"]), proposal["cost_pct"],
        proposal.get("created_by", "learning-job"),
    ))


def proposal_row(row: Any) -> dict[str, Any]:
    out = dict(row)
    for key in ("id", "activation_id"):
        if out.get(key) is not None:
            out[key] = str(out[key])
    for key in ("config", "weights", "evidence", "replay"):
        out[key] = as_json(out.get(key))
    for key in ("created_at", "decided_at", "reverted_at"):
        if out.get(key) is not None:
            out[key] = out[key].isoformat()
    return out
