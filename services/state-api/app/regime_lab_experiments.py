"""Draft Regime Lab experiments, stored with the replay judgement they were saved on.

A saved experiment is immutable and has no activation path. It keeps the
baseline and challenger configurations (each stored once, by digest), the
operator's hypothesis, the replay window and horizon it was judged over, and
that judgement. Listing returns each draft with its weights and the headline
counts of its judgement.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from tradesync_core.regime_weights import RegimeRulebook

LIST_SQL = """
select e.id, e.name, e.status, e.hypothesis, e.evaluation_plan, e.results, e.created_at,
       champion.version as baseline_version,
       challenger.version as challenger_version,
       challenger.config -> 'blocks' as challenger_blocks
from regime_experiments e
join regime_rulebooks champion on champion.id = e.champion_rulebook_id
join regime_rulebooks challenger on challenger.id = e.challenger_rulebook_id
order by e.created_at desc
limit $1
"""

INSERT_RULEBOOK_SQL = """
insert into regime_rulebooks (
  rulebook_id, version, schema_version, status, environment, horizon,
  config_digest, config, created_by
) values ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)
on conflict (config_digest) do nothing
returning id
"""

INSERT_EXPERIMENT_SQL = """
insert into regime_experiments (
  name, status, horizon, champion_rulebook_id, challenger_rulebook_id,
  hypothesis, evaluation_plan, results
) values ($1,'draft',$2,$3::uuid,$4::uuid,$5,$6::jsonb,$7::jsonb)
returning id
"""


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def ensure_rulebook(conn, rulebook: RegimeRulebook, created_by: str) -> str:
    """The stored id of ``rulebook``, inserted once by configuration digest."""
    row = await conn.fetchrow(
        INSERT_RULEBOOK_SQL,
        rulebook.rulebook_id,
        rulebook.version,
        rulebook.data["schema_version"],
        rulebook.data["status"],
        rulebook.data["environment"],
        rulebook.data["horizon"],
        rulebook.digest,
        json.dumps(rulebook.data),
        created_by,
    )
    if row:
        return str(row["id"])
    existing = await conn.fetchrow("select id from regime_rulebooks where config_digest=$1", rulebook.digest)
    if not existing:
        raise RuntimeError("rulebook insert did not return or resolve an ID")
    return str(existing["id"])


def evaluation_plan(replay: Mapping[str, Any]) -> dict[str, Any]:
    window = replay.get("window") or {}
    return {
        "method": "stored_decision_replay",
        "window_hours": window.get("hours"),
        "horizon_minutes": window.get("horizon_minutes"),
        "symbol": window.get("symbol"),
        "mode": "paper_shadow",
    }


async def persist_experiment(
    conn,
    baseline: RegimeRulebook,
    challenger: RegimeRulebook,
    *,
    name: str,
    hypothesis: str,
    replay: Mapping[str, Any],
    created_by: str = "local-operator",
) -> str:
    """Store one immutable draft with its replay judgement; return its id."""
    baseline_id = await ensure_rulebook(conn, baseline, created_by)
    challenger_id = await ensure_rulebook(conn, challenger, created_by)
    row = await conn.fetchrow(
        INSERT_EXPERIMENT_SQL,
        name,
        baseline.data["horizon"],
        baseline_id,
        challenger_id,
        hypothesis,
        json.dumps(evaluation_plan(replay)),
        json.dumps({"replay": dict(replay)}),
    )
    return str(row["id"])


def experiment_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    """One saved draft as the Regime Lab lists it; drafts saved before replay judging have no replay."""
    plan = _json(row["evaluation_plan"]) or {}
    results = _json(row["results"]) or {}
    blocks = _json(row["challenger_blocks"]) or {}
    replay = results.get("replay") if isinstance(results, Mapping) else None
    created = row["created_at"]
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "status": row["status"],
        "hypothesis": row["hypothesis"],
        "created_at": created.isoformat() if created is not None else None,
        "baseline_version": row["baseline_version"],
        "challenger_version": row["challenger_version"],
        "weights": {block: detail.get("weight") for block, detail in blocks.items() if isinstance(detail, Mapping)},
        "window_hours": plan.get("window_hours"),
        "horizon_minutes": plan.get("horizon_minutes"),
        "symbol": plan.get("symbol"),
        "replay": {key: replay.get(key) for key in ("decisions", "outcomes", "window")} if isinstance(replay, Mapping) else None,
    }
