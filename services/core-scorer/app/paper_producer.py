"""Persist regime-backed paper signals and publish them for opportunity building.

A refusal is recorded as carefully as an admission. The dashboard must be able
to say why no opportunity exists for a symbol, so the refusal reasoning is
stored rather than discarded.

Nothing here grants execution authority. A stored signal is paper evidence.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from tradesync_core.paper_signal import PaperSignalDecision

SIGNAL_STREAM = os.getenv("SIGNAL_STREAM", "x:signals.funding")
SIGNAL_AGENT = "regime_paper_scorer"


# How many scoring cycles a side may go un-readmitted before it has lapsed.
# A held side is re-admitted every cycle for as long as it clears the hold
# threshold, so silence across several cycles means it stopped clearing it.
DIRECTION_HOLD_CYCLES = int(os.getenv("DIRECTION_HOLD_CYCLES", "5"))


def direction_hold_max_age_seconds(scoring_interval_seconds: int) -> int:
    """How old the establishing admission may be and still count as held.

    Expressed in cycles rather than as a fixed duration: the bound has to move
    with the scoring cadence, or changing the interval silently changes how
    sticky a direction is.
    """
    if scoring_interval_seconds <= 0:
        raise ValueError("scoring_interval_seconds must be positive")
    return DIRECTION_HOLD_CYCLES * scoring_interval_seconds


async def last_admitted_direction(
    conn, symbol: str, max_age_seconds: int | None = None
) -> str | None:
    """Return the direction ``symbol`` is *currently* holding, if any.

    Hysteresis needs to know which side is held: a held direction only has to
    clear the lower hold threshold, while establishing or reversing one must
    clear the higher entry threshold. Refusals are skipped because they never
    established a side.

    The age bound is the point. Without it this returned the most recent
    admitted direction *ever*, so a side admitted once and then never again
    stayed "held" forever — and the entry threshold, the whole reason
    hysteresis exists, stopped applying to that symbol permanently. After a
    quiet spell or a restart, a score of 0.06 would then be admitted as a
    continuation of a side that had not been current for days.

    A lapsed side returns ``None``, which is the honest answer: nothing is
    held, so the next direction has to earn entry.
    """
    if max_age_seconds is None:
        row = await conn.fetchrow(
            """
            SELECT dir FROM signals
            WHERE agent = $1 AND symbol = $2 AND kind = 'regime_paper_signal'
            ORDER BY created_at DESC LIMIT 1
            """,
            SIGNAL_AGENT,
            symbol,
        )
    else:
        row = await conn.fetchrow(
            """
            SELECT dir FROM signals
            WHERE agent = $1 AND symbol = $2 AND kind = 'regime_paper_signal'
              AND created_at > now() - make_interval(secs => $3::double precision)
            ORDER BY created_at DESC LIMIT 1
            """,
            SIGNAL_AGENT,
            symbol,
            float(max_age_seconds),
        )
    return row["dir"] if row and row["dir"] in ("LONG", "SHORT") else None


async def has_active_opportunity(conn, symbol: str, direction: str) -> bool:
    """Whether an unexpired opportunity already holds this side.

    The producer evaluates every 60s. Without this check each cycle mints a
    fresh opportunity for a position that has not changed, which buries the
    moment the side actually turned under dozens of duplicates.
    """
    row = await conn.fetchrow(
        """
        SELECT 1 FROM opportunities
        WHERE symbol = $1 AND dir = $2
          AND (expires_at IS NULL OR expires_at > now())
        LIMIT 1
        """,
        symbol,
        direction,
    )
    return row is not None


def build_stream_payload(
    decision: PaperSignalDecision,
    signal_id: str,
    created_at: datetime,
) -> dict[str, Any]:
    """Build the envelope the opportunity builder consumes.

    ``score`` is kept on the envelope for the legacy threshold check, and
    ``paper_signal`` carries the evidence that must survive unchanged into the
    opportunity record.
    """

    return {
        "id": signal_id,
        "agent": SIGNAL_AGENT,
        "schema_version": decision.to_dict()["schema_version"],
        "symbol": decision.symbol,
        "timeframe": "1m",
        "score": decision.weighted_score,
        "confidence": decision.data_coverage,
        "direction": decision.direction,
        "evidence_digest": decision.evidence_digest,
        "event_ids": [],
        "created_at": created_at.isoformat(),
        "paper_signal": decision.to_dict(),
    }


async def persist_decision(conn, decision: PaperSignalDecision) -> tuple[str, datetime]:
    """Write one signal row, admitted or refused, with its full evidence.

    ``confidence`` stores data coverage: how much of the rulebook's weight had
    admissible evidence behind it. It is deliberately not a win probability.
    """

    signal_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    await conn.execute(
        """
        INSERT INTO signals (
            id, agent, symbol, timeframe, kind, confidence, dir, features,
            event_ids, created_at, notes
        ) VALUES ($1, $2, $3, '1m', $4, $5, $6, $7, '{}', $8, $9)
        """,
        signal_id,
        SIGNAL_AGENT,
        decision.symbol,
        "regime_paper_signal" if decision.admitted else "regime_paper_refusal",
        max(0.0, min(1.0, decision.data_coverage)),
        decision.direction,
        json.dumps(decision.to_dict()),
        created_at,
        _refusal_note(decision),
    )
    return signal_id, created_at


def _refusal_note(decision: PaperSignalDecision) -> str:
    if decision.admitted:
        return "Admitted paper signal; no execution authority."
    codes = ", ".join(reason["code"] for reason in decision.rejection_reasons)
    return f"No paper opportunity produced. Reasons: {codes}"


async def publish_decision(
    redis_client,
    decision: PaperSignalDecision,
    signal_id: str,
    created_at: datetime,
) -> bool:
    """Publish an admitted decision. Refusals are stored but never published."""

    if not decision.admitted:
        return False
    payload = build_stream_payload(decision, signal_id, created_at)
    await redis_client.xadd(SIGNAL_STREAM, {"data": json.dumps(payload)})
    return True
