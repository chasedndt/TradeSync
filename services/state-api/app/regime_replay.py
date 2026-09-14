"""Challengers judged by replay: the scorer's stored decisions re-decided under new weights.

``POST /state/regime-lab/replay`` takes a window (24 hours, 7 days or 30 days),
the outcome horizon, an optional market and the challenger's five weights. It
reads the paper scorer's recorded decisions in that window, admitted and
refused, with the outcome measured for each one that opened a paper
opportunity, and judges the challenger with ``tradesync_core.replay_judgement``.

Bounded on purpose:

- only the evidence a replay needs is read from each stored decision, never the
  whole recorded payload;
- the decision counts keep one decision per market per sampling bucket (every
  minute over 24 hours, every 10 minutes over 7 days, every 30 minutes over 30
  days), and every decision with a measured outcome is kept regardless;
- the queries carry their own timeout instead of the pool's five seconds, and a
  timeout is named rather than returned as an empty error;
- the replay itself runs in a worker thread.

Refused decisions are kept in full for seven days before retention rolls them
up, so a longer window replays fewer refusals; the response says from when they
are available. Paper only: nothing here can activate a rulebook or place an order.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, Literal, Mapping, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from tradesync_core import normalize_symbol
from tradesync_core.paper_signal import AdmissionPolicy
from tradesync_core.regime_lab import RegimeLabValidationError, challenger_rulebook
from tradesync_core.regime_weights import RegimeRulebook
from tradesync_core.replay import ReplayCase, ReplayError, case_from_stored_evidence
from tradesync_core.replay_judgement import judge_window
from tradesync_core.retention import DEFAULT_REFUSAL_RETENTION_DAYS

SIGNAL_AGENT = "regime_paper_scorer"
SAMPLE_BUCKET_SECONDS = {24: 60, 168: 600, 720: 1800}
QUERY_TIMEOUT_S = 45.0

WINDOW_SQL = """
SELECT count(*) AS decisions,
       count(*) FILTER (WHERE kind = 'regime_paper_refusal') AS refusals,
       min(created_at) AS first_at,
       min(created_at) FILTER (WHERE kind = 'regime_paper_refusal') AS first_refusal_at
FROM signals
WHERE agent = $1
  AND created_at > now() - make_interval(hours => $2::int)
  AND ($3::text IS NULL OR symbol = $3)
"""

CASES_SQL = """
WITH window_signals AS (
    SELECT id, symbol, created_at
    FROM signals
    WHERE agent = $1
      AND created_at > now() - make_interval(hours => $2::int)
      AND ($3::text IS NULL OR symbol = $3)
),
sampled AS (
    SELECT DISTINCT ON (symbol, floor(extract(epoch FROM created_at) / $4::int)) id
    FROM window_signals
    ORDER BY symbol, floor(extract(epoch FROM created_at) / $4::int), created_at DESC
),
measured AS (
    SELECT w.id, o.signed_return_pct, o.forward_return_pct
    FROM window_signals w
    JOIN opportunities opp ON opp.signal_id = w.id
    JOIN opportunity_outcomes o ON o.opportunity_id = opp.id
    WHERE o.horizon_minutes = $5::int
      AND o.status = 'measured'
      AND o.signed_return_pct IS NOT NULL
      AND o.forward_return_pct IS NOT NULL
)
SELECT s.id::text AS id,
       s.symbol,
       s.features -> 'evidence' -> 'contributions' AS contributions,
       s.features -> 'evidence' -> 'directional' AS directional,
       s.features -> 'evidence' ->> 'evaluated_at_ms' AS evaluated_at_ms,
       m.signed_return_pct,
       m.forward_return_pct,
       s.id IN (SELECT id FROM sampled) AS sampled
FROM signals s
LEFT JOIN measured m ON m.id = s.id
WHERE s.id IN (SELECT id FROM sampled UNION SELECT id FROM measured)
ORDER BY s.created_at
"""

# Set by register(): the app's shared state and the Regime Lab engine.
state = None
regime_lab_engine = None


class ReplayRequest(BaseModel):
    """One window of stored decisions, judged under the challenger's weights."""

    hours: Literal[24, 168, 720] = 24
    horizon_minutes: Literal[15, 60, 240] = 60
    symbol: Optional[str] = Field(default=None, max_length=24)
    challenger_weights: Dict[str, float]
    challenger_version: str = Field(default="challenger", min_length=1, max_length=40)


def catalog_summary(engine) -> dict[str, Any]:
    return {
        "catalog_id": engine.catalog.data["catalog_id"],
        "version": engine.catalog.version,
        "digest": engine.catalog.digest,
    }


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def cases_from_rows(rows) -> tuple[list[ReplayCase], set[str], int]:
    """Replay cases, the ids in the decision sample, and how many rows could not be replayed."""
    cases: list[ReplayCase] = []
    sampled: set[str] = set()
    skipped = 0
    for row in rows:
        try:
            evaluated_at = row["evaluated_at_ms"]
            stored = {
                "evidence": {
                    "contributions": _json(row["contributions"]),
                    "directional": _json(row["directional"]),
                    "evaluated_at_ms": int(evaluated_at) if evaluated_at not in (None, "") else 0,
                }
            }
            case = case_from_stored_evidence(
                str(row["id"]),
                row["symbol"],
                stored,
                outcome_signed_return_pct=row["signed_return_pct"],
                market_move_pct=row["forward_return_pct"],
            )
        except (ReplayError, ValueError, TypeError):
            # Evidence recorded before the current schema cannot be replayed
            # faithfully, so it is counted and excluded rather than guessed at.
            skipped += 1
            continue
        cases.append(case)
        if row["sampled"]:
            sampled.add(case.signal_id)
    return cases, sampled, skipped


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def window_description(
    summary: Mapping[str, Any] | None, *, hours: int, horizon_minutes: int, symbol: str | None, skipped: int
) -> dict[str, Any]:
    summary = summary or {}
    return {
        "hours": hours,
        "horizon_minutes": horizon_minutes,
        "symbol": symbol,
        "sample_bucket_seconds": SAMPLE_BUCKET_SECONDS[hours],
        "decisions_in_window": int(summary.get("decisions") or 0),
        "refusals_in_window": int(summary.get("refusals") or 0),
        "first_decision_at": _iso(summary.get("first_at")),
        "refusals_available_since": _iso(summary.get("first_refusal_at")),
        "refusal_retention_days": DEFAULT_REFUSAL_RETENTION_DAYS,
        "skipped_unreplayable": skipped,
    }


async def fetch_window(pool, hours: int, horizon_minutes: int, symbol: str | None):
    try:
        async with pool.acquire() as conn:
            summary = await conn.fetchrow(WINDOW_SQL, SIGNAL_AGENT, hours, symbol, timeout=QUERY_TIMEOUT_S)
            rows = await conn.fetch(
                CASES_SQL, SIGNAL_AGENT, hours, symbol, SAMPLE_BUCKET_SECONDS[hours], horizon_minutes,
                timeout=QUERY_TIMEOUT_S,
            )
    except (asyncio.TimeoutError, TimeoutError):
        raise HTTPException(
            status_code=504,
            detail=(
                f"Reading stored decisions did not finish within {int(QUERY_TIMEOUT_S)} s; "
                "try a shorter window or one market"
            ),
        ) from None
    except Exception as exc:
        if type(exc).__name__ == "QueryCanceledError":
            raise HTTPException(status_code=504, detail="The database cancelled the replay query; try a shorter window") from None
        raise HTTPException(status_code=503, detail=f"Stored decisions could not be read ({type(exc).__name__})") from None
    return summary, rows


async def run_replay(
    pool, engine, *, hours: int, horizon_minutes: int, symbol: str | None, challenger: RegimeRulebook
) -> dict[str, Any]:
    """Judge ``challenger`` over one window of stored decisions; shared by replay and save."""
    summary, rows = await fetch_window(pool, hours, horizon_minutes, symbol)

    def judge() -> tuple[dict[str, Any], int]:
        cases, sampled, skipped = cases_from_rows(rows)
        judgement = judge_window(
            cases, engine.baseline, challenger, AdmissionPolicy(), catalog_summary(engine), sampled_ids=sampled
        )
        return judgement, skipped

    judgement, skipped = await asyncio.to_thread(judge)
    return {
        **judgement,
        "window": window_description(summary, hours=hours, horizon_minutes=horizon_minutes, symbol=symbol, skipped=skipped),
        "execution_authority": False,
    }


def challenger_from_request(engine, weights: Mapping[str, Any], version: str, purpose: str | None = None) -> RegimeRulebook:
    try:
        return challenger_rulebook(engine.baseline, weights, version, purpose)
    except RegimeLabValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def replay_fixed_window(request: ReplayRequest):
    """Judge a challenger over a frozen window of the scorer's recorded decisions.

    Baseline and challenger decide identical stored evidence, so any difference
    is the configuration, not the market having moved.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="PostgreSQL is unavailable; stored decisions cannot be replayed")
    challenger = challenger_from_request(regime_lab_engine, request.challenger_weights, request.challenger_version)
    symbol = normalize_symbol(request.symbol) if request.symbol else None
    return await run_replay(
        state.pool, regime_lab_engine,
        hours=request.hours, horizon_minutes=request.horizon_minutes, symbol=symbol, challenger=challenger,
    )


def register(app, app_state, *, engine) -> None:
    global state, regime_lab_engine
    state, regime_lab_engine = app_state, engine
    app.post("/state/regime-lab/replay", tags=["regime-lab"])(replay_fixed_window)
