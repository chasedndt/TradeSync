"""Opportunity lifecycle: an opportunity is live until its TTL passes, then expired.

The fusion engine writes each opportunity with ``status = 'new'`` and an
``expires_at`` (900 s by default). Nothing ever moved a row on, so ``new`` came
to mean "admitted at some point": the Overview listed calls from days ago as
open and the Expired tab matched nothing.

Two parts, which agree by construction because they share one expiry expression:

- **At read.** ``EFFECTIVE_STATUS_SQL`` reports a ``new`` row past its expiry as
  ``expired`` and ``status_filter`` filters on that effective status, so the API
  is right the moment a row expires, whether or not the job has run yet.
- **In storage.** ``expire_pass`` marks those rows ``expired`` once a minute, so
  every other reader of ``opportunities.status`` sees the same lifecycle.

A row without ``expires_at`` (written before TTLs existed) expires
``DEFAULT_TTL_SECONDS`` after it opened.

When nothing is live, ``quiet_summary`` says when the last opportunity was and
what the scorer refused in the recent window, from the signals table.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

DEFAULT_TTL_SECONDS = int(os.getenv("OPPORTUNITY_TTL_SECONDS", "900"))
EXPIRY_INTERVAL_SECONDS = int(os.getenv("OPPORTUNITY_EXPIRY_INTERVAL_SECONDS", "60"))
SCORER_AGENT = "regime_paper_scorer"

EXPIRES_AT_SQL = f"COALESCE(expires_at, snapshot_ts + make_interval(secs => {DEFAULT_TTL_SECONDS}))"
EFFECTIVE_STATUS_SQL = (
    f"CASE status WHEN 'new' THEN CASE WHEN {EXPIRES_AT_SQL} <= now() THEN 'expired' ELSE 'new' END "
    "ELSE status END"
)

REFUSAL_LABELS = {
    "coverage_below_emit_floor": "Too little evidence collected",
    "score_inside_deadband": "Direction too weak to call",
    "directional_coverage_below_floor": "Too few directional readings",
    "no_directional_evidence": "No directional reading available",
    "no_admitted_evidence": "No feature admitted for scoring",
    "paper_risk_fully_capped": "Paper risk cap at zero",
    "evidence_stale": "Evidence too old",
    "evidence_timestamped_in_future": "Evidence timestamped in the future",
    "inadmissible_provenance": "Evidence source not admissible",
}


def status_filter(status: str, params: list) -> str:
    """A WHERE clause on the effective status; appends its parameter to ``params``."""

    params.append(status)
    placeholder = f"${len(params)}"
    if status == "new":
        return f"(status = {placeholder} AND {EXPIRES_AT_SQL} > now())"
    if status == "expired":
        return f"(status = {placeholder} OR (status = 'new' AND {EXPIRES_AT_SQL} <= now()))"
    return f"status = {placeholder}"


async def expire_pass(conn) -> int:
    """Mark every ``new`` opportunity past its expiry as ``expired``; return how many."""

    result = await conn.execute(
        f"UPDATE opportunities SET status = 'expired' WHERE status = 'new' AND {EXPIRES_AT_SQL} <= now()"
    )
    try:
        return int(str(result).rsplit(" ", 1)[-1])
    except ValueError:
        return 0


async def expiry_loop(state) -> None:
    while True:
        try:
            if state.pool:
                async with state.pool.acquire() as conn:
                    expired = await expire_pass(conn)
                if expired:
                    print(f"[Lifecycle] marked {expired} opportunities expired")
        except Exception as exc:  # the next pass retries; the read path is already correct
            print(f"[Lifecycle] expiry pass failed: {type(exc).__name__}: {exc}")
        await asyncio.sleep(EXPIRY_INTERVAL_SECONDS)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


async def quiet_summary(conn, window_minutes: int = 60) -> dict[str, Any]:
    """Live count, the last opportunity, and the window's verdicts and refusal reasons."""

    live = await conn.fetchval(
        f"SELECT count(*) FROM opportunities WHERE status = 'new' AND {EXPIRES_AT_SQL} > now()"
    )
    last = await conn.fetchrow(
        f"SELECT id, symbol, dir, snapshot_ts, {EXPIRES_AT_SQL} AS expires_at "
        "FROM opportunities ORDER BY snapshot_ts DESC LIMIT 1"
    )
    verdicts = await conn.fetchrow(
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE kind = 'regime_paper_signal') AS admitted,
               count(*) FILTER (WHERE kind = 'regime_paper_refusal') AS refused,
               max(created_at) AS last_verdict_at
        FROM signals
        WHERE agent = $1 AND created_at > now() - make_interval(mins => $2)
        """,
        SCORER_AGENT,
        window_minutes,
    )
    reasons = await conn.fetch(
        """
        SELECT reason->>'code' AS code,
               count(DISTINCT s.id) AS refusals,
               (array_agg(reason->>'detail' ORDER BY s.created_at DESC))[1] AS example_detail
        FROM signals s,
             jsonb_array_elements(COALESCE(s.features->'rejection_reasons', '[]'::jsonb)) AS reason
        WHERE s.agent = $1 AND s.kind = 'regime_paper_refusal'
          AND s.created_at > now() - make_interval(mins => $2)
        GROUP BY 1
        ORDER BY 2 DESC, 1
        LIMIT 5
        """,
        SCORER_AGENT,
        window_minutes,
    )
    refused = int((verdicts or {}).get("refused") or 0)
    return {
        "live": int(live or 0),
        "ttl_seconds": DEFAULT_TTL_SECONDS,
        "window_minutes": window_minutes,
        "last_opportunity": (
            {
                "id": str(last["id"]),
                "symbol": last["symbol"],
                "direction": last["dir"],
                "opened_at": _iso(last["snapshot_ts"]),
                "expires_at": _iso(last["expires_at"]),
            }
            if last
            else None
        ),
        "verdicts": {
            "total": int((verdicts or {}).get("total") or 0),
            "admitted": int((verdicts or {}).get("admitted") or 0),
            "refused": refused,
            "last_verdict_at": _iso((verdicts or {}).get("last_verdict_at")),
        },
        "top_refusal_reasons": [
            {
                "code": row["code"],
                "label": REFUSAL_LABELS.get(row["code"], str(row["code"]).replace("_", " ")),
                "refusals": int(row["refusals"]),
                "share_of_refusals": round(int(row["refusals"]) / refused, 4) if refused else None,
                "example_detail": row["example_detail"],
            }
            for row in reasons
        ],
        "note": "A refusal can carry several reasons, so the shares can add up to more than 100%.",
    }
