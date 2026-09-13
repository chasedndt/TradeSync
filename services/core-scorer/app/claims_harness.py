"""Ask the advisory harness what a post said, when the rule extractor could not tell.

Runs inside the claims job after rule extraction. For each row the rule
reader abstained on, the harness is asked through state-api's boundary
(``POST /state/agents/harness/ask``), which files the harness's own answer in
quarantine and refuses any answer that reaches for authority. The answer is
then parsed and checked by ``tradesync_core.claim_proposals``: a proposal
becomes a claim only if its quote appears verbatim in the post. The claim
belongs to the post's source; the harness is the reader.

Bounded on purpose. One ask takes tens of seconds, so a pass handles a few
rows and the backlog drains over hours rather than saturating the runtime.
Off when the harness is not configured, and every failure leaves the row
un-asked for a later pass rather than marking it done.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from tradesync_core.claim_extraction import NoClaim
from tradesync_core.claim_proposals import EXTRACTOR, INTENT, parse_proposals, proposal_prompt

from .claims_store import harness_candidates, record_harness_extraction

STATE_API_URL = os.getenv("STATE_API_URL", "http://state-api:8000").rstrip("/")
HARNESS_CLAIMS_ENABLED = os.getenv("HARNESS_CLAIMS_ENABLED", "true").strip().lower() == "true"
HARNESS_ROWS_PER_PASS = int(os.getenv("HARNESS_ROWS_PER_PASS", "4"))
ASK_TIMEOUT_S = float(os.getenv("HARNESS_ASK_TIMEOUT_S", "180"))


def post_text(payload: dict[str, Any]) -> str:
    """The same text the rule extractor read, so quotes can be checked against it."""
    if payload.get("schema_version") == "discord_message_v1":
        parts = [str(payload.get("content") or "")]
        for e in payload.get("embeds") or []:
            parts.extend(str(e.get(k) or "") for k in ("title", "description"))
            parts.extend(f"{f.get('name')}: {f.get('value')}" for f in e.get("fields") or [])
        return "\n".join(p for p in parts if p)
    return str(payload.get("content") or "")


async def harness_available(client: httpx.AsyncClient) -> bool:
    try:
        r = await client.get(f"{STATE_API_URL}/state/agents/harness/status", timeout=10.0)
        return r.status_code == 200 and r.json().get("status") == "live"
    except (httpx.HTTPError, ValueError):
        return False


async def ask(client: httpx.AsyncClient, prompt: str) -> dict[str, Any] | None:
    """One boundary-checked ask. None on transport failure; a refusal is an answer."""
    try:
        r = await client.post(
            f"{STATE_API_URL}/state/agents/harness/ask",
            json={"intent": INTENT, "prompt": prompt},
            timeout=ASK_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        print(f"[Claims/harness] ask failed: {type(exc).__name__}")
        return None
    if r.status_code == 422:
        # The harness reached for authority; state-api already filed the refusal.
        return {"refused": True, "detail": r.text[:200]}
    if r.status_code != 200:
        print(f"[Claims/harness] ask HTTP {r.status_code}")
        return None
    try:
        return r.json()
    except ValueError:
        return None


async def run_harness_pass(conn, client: httpx.AsyncClient) -> dict[str, int]:
    counts = {"asked": 0, "claims": 0, "no_claim": 0, "refused": 0, "deferred": 0}
    if not HARNESS_CLAIMS_ENABLED:
        return counts
    rows = await harness_candidates(conn, HARNESS_ROWS_PER_PASS)
    if not rows or not await harness_available(client):
        return counts
    for row in rows:
        payload = row["payload"]
        text = post_text(payload)
        agent = str(payload.get("agent") or row["source"])
        answer = await ask(client, proposal_prompt(agent, text))
        if answer is None:
            counts["deferred"] += 1
            continue
        counts["asked"] += 1
        qid = str(row["id"])
        if answer.get("refused"):
            detail = str(answer.get("detail") or "")[:160]
            await record_harness_extraction(conn, qid, EXTRACTOR, [], f"harness answer refused at the boundary: {detail}", None)
            counts["refused"] += 1
            continue
        claimed_at_ms = int((row["observed_at"] or row["received_at"]).timestamp() * 1000)
        result = parse_proposals(
            str(answer.get("content") or ""), source=row["source"], source_id=agent, text=text, claimed_at_ms=claimed_at_ms,
        )
        digest = (answer.get("receipt") or {}).get("content_digest")
        if isinstance(result, NoClaim):
            await record_harness_extraction(conn, qid, EXTRACTOR, [], result.reason, digest)
            counts["no_claim"] += 1
        else:
            await record_harness_extraction(conn, qid, EXTRACTOR, result, "", digest)
            counts["claims"] += len(result)
    return counts
