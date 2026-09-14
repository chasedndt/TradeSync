"""The opportunity-learning job: attribute measured outcomes, then propose weights.

Runs as a state-api background loop (app/background.py) on two cadences:

- every ``ATTRIBUTION_INTERVAL_SECONDS`` (10 min) it attributes each measured
  outcome that has no attribution or a stale one, in batches. The first run
  backfills history; later runs pick up only what changed. With nothing new the
  candidate query is empty and nothing is written, and a repeated write lands on
  the same (opportunity, horizon) row.
- every ``PROPOSAL_INTERVAL_SECONDS`` (6 h) it runs the walk-forward over the
  learning window and stores a proposal when one is produced. It never adopts.

Attribution and walk-forward are CPU work, so they run in a worker thread. One
lock serialises the loop and the on-demand "generate" action.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any

from tradesync_core.attribution import AttributionError, MeasuredHorizon, attribute_outcome
from tradesync_core.decision_contributions import contributions_from_decision
from tradesync_core.learning_proposal import proposal_version
from tradesync_core.outcome_classification import DEFAULT_ROUND_TRIP_COST_PCT, ClassificationError
from tradesync_core.regime_weights import RegimeRulebook
from tradesync_core.walk_forward import WalkForwardConfig, run_walk_forward

from app import learning_store as store
from app import rulebook_activation as activation

ATTRIBUTION_INTERVAL_SECONDS = int(os.getenv("LEARNING_ATTRIBUTION_INTERVAL_SECONDS", "600"))
PROPOSAL_INTERVAL_SECONDS = int(os.getenv("LEARNING_PROPOSAL_INTERVAL_SECONDS", "21600"))
COST_PCT = float(os.getenv("LEARNING_ROUND_TRIP_COST_PCT", str(DEFAULT_ROUND_TRIP_COST_PCT)))
TARGET_HORIZON_MINUTES = int(os.getenv("LEARNING_TARGET_HORIZON_MINUTES", "60"))
WINDOW_DAYS = int(os.getenv("LEARNING_WINDOW_DAYS", "14"))
BATCH = int(os.getenv("LEARNING_ATTRIBUTION_BATCH", "500"))
MAX_BATCHES = int(os.getenv("LEARNING_ATTRIBUTION_MAX_BATCHES", "40"))
STARTUP_DELAY_SECONDS = int(os.getenv("LEARNING_STARTUP_DELAY_SECONDS", "90"))

lock = asyncio.Lock()
last_runs: dict[str, dict[str, Any]] = {}


def _record(kind: str, outcome: dict[str, Any]) -> None:
    last_runs[kind] = {**outcome, "at": datetime.now(timezone.utc).isoformat()}


def attribute_rows(rows: list[dict[str, Any]], cost_pct: float) -> tuple[list[tuple], int]:
    """Candidate rows -> (attribution, opened_at, measured_at) triples; each decision split once."""

    decisions: dict[str, tuple[dict, Any]] = {}
    out, skipped = [], 0
    for row in rows:
        key = str(row["opportunity_id"])
        if key not in decisions:
            decision = store.as_json(row["confluence"]) or {}
            decisions[key] = (decision, contributions_from_decision(decision))
        decision, parts = decisions[key]
        try:
            attribution = attribute_outcome(
                opportunity_id=key, symbol=row["symbol"], direction=row["direction"],
                opened_at_s=int(row["opened_at"].timestamp()), decision=decision,
                measured=MeasuredHorizon(int(row["horizon_minutes"]), float(row["signed_return_pct"]),
                                         row["max_favourable_pct"], row["max_adverse_pct"]),
                entry_regime=row["regime"], cost_pct=cost_pct, contributions=parts,
            )
        except (AttributionError, ClassificationError):
            skipped += 1
            continue
        out.append((attribution.to_dict(), row["opened_at"], row["measured_at"]))
    return out, skipped


async def run_attribution_pass(pool, cost_pct: float = COST_PCT, batch: int = BATCH,
                               max_batches: int = MAX_BATCHES) -> dict[str, int]:
    attributed = skipped = batches = 0
    for _ in range(max_batches):
        async with pool.acquire() as conn:
            rows = await store.attribution_candidates(conn, cost_pct, batch)
        if not rows:
            break
        results, bad = await asyncio.to_thread(attribute_rows, rows, cost_pct)
        async with pool.acquire() as conn:
            async with conn.transaction():
                for attribution, opened_at, measured_at in results:
                    await store.upsert_attribution(conn, attribution, opened_at, measured_at)
        attributed, skipped, batches = attributed + len(results), skipped + bad, batches + 1
        if len(rows) < batch or not results:
            break
    return {"attributed": attributed, "skipped": skipped, "batches": batches}


async def run_proposal_pass(pool, baseline: RegimeRulebook, *, horizon: int = TARGET_HORIZON_MINUTES,
                            days: int = WINDOW_DAYS, cost_pct: float = COST_PCT,
                            created_by: str = "learning-job", now: datetime | None = None) -> dict[str, Any]:
    """Walk-forward over the window under the active rulebook; store a proposal if one is produced."""

    async with pool.acquire() as conn:
        active = await activation.read_active(conn, baseline)
        records = await store.decision_records(conn, days)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M")
    version = proposal_version(active.rulebook.version, stamp)
    config = WalkForwardConfig(horizon_minutes=horizon, cost_pct=cost_pct)
    result = await asyncio.to_thread(run_walk_forward, records, active.rulebook, version, config)
    summary = {"decisions": len(records), "horizon_minutes": horizon, "parent_version": active.rulebook.version,
               "reason": result.reason, "window": result.evidence.get("window")}
    if result.proposal is None:
        return {**summary, "proposal_id": None}
    proposal = result.proposal
    async with pool.acquire() as conn:
        async with conn.transaction():
            proposal_id = await store.insert_proposal(conn, {
                "rulebook_id": proposal.rulebook_id, "rulebook_horizon": proposal.data["horizon"],
                "target_horizon_minutes": horizon, "parent_version": active.rulebook.version,
                "parent_digest": active.rulebook.digest, "version": proposal.version,
                "config_digest": proposal.digest, "config": proposal.data, "hypothesis": proposal.data["purpose"],
                "weights": result.change, "evidence": {**result.evidence, "parent_source": active.source},
                "replay": result.replay, "cost_pct": cost_pct, "created_by": created_by,
            })
    return {**summary, "proposal_id": proposal_id, "version": proposal.version,
            "assessment": result.replay.get("assessment")}


async def learning_loop(state, baseline: RegimeRulebook) -> None:
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    last_proposal = None
    while True:
        if state.pool:
            try:
                async with lock:
                    stats = await run_attribution_pass(state.pool)
                _record("attribution", stats)
                if stats["attributed"]:
                    print(f"[Learning] attributed {stats['attributed']} measured horizons")
            except Exception as exc:  # e.g. migration 028 not yet applied; retried next cycle
                _record("attribution", {"error": f"{type(exc).__name__}: {exc}"})
                print(f"[Learning] attribution pass failed: {type(exc).__name__}: {exc}")
            if last_proposal is None or time.monotonic() - last_proposal >= PROPOSAL_INTERVAL_SECONDS:
                last_proposal = time.monotonic()
                try:
                    async with lock:
                        outcome = await run_proposal_pass(state.pool, baseline)
                    _record("proposal", outcome)
                    print(f"[Learning] proposal pass: {outcome.get('proposal_id') or outcome['reason']}")
                except Exception as exc:
                    _record("proposal", {"error": f"{type(exc).__name__}: {exc}"})
                    print(f"[Learning] proposal pass failed: {type(exc).__name__}: {exc}")
        await asyncio.sleep(ATTRIBUTION_INTERVAL_SECONDS)
