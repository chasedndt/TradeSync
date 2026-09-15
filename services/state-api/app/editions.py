"""Thesis editions: every tracked symbol's thesis plus the market outlook, frozen on a schedule.

Three editions a day, on the StrikeZone cadence in London time (NY premarket
12:00, NY midday 17:30, session handoff 23:30), plus a regeneration whenever
the operator asks for one (a black-swan move, a mid-session reset), with the
reason recorded. Building one takes minutes, so it runs as a background job;
the list endpoint reports its stage.

An edition holds the per-symbol theses, the outlook (breadth, lead reads,
this week's events with their measured reaction and recent articles), the
written text and spoken script, and an advisory briefing Hermes drafts
through the harness boundary. Media renderers attach narration and video
afterwards.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import agent_connector, background
from app.event_outlook import articles_for, ensure_profiles, events_from_context
from app.thesis import CANDLE_BUCKET_S, Evidence, _no_evidence, execution_enabled, gather_inputs
from tradesync_core.market_outlook import compose_outlook
from tradesync_core.outlook_render import outlook_narration, outlook_text
from tradesync_core.thesis import build_thesis
from tradesync_core.thesis_edition import EDITIONS, compose
from tradesync_core.state_api_access import operator_headers

router = APIRouter(tags=["thesis"])

EDITIONS_DIR = Path(os.getenv("EDITIONS_DIR", "/editions"))
SELF_URL = os.getenv("STATE_API_SELF_URL", "http://localhost:8000").rstrip("/")
BRIEFING_TIMEOUT_S = float(os.getenv("THESIS_BRIEFING_TIMEOUT_S", "300"))


class MediaAttach(BaseModel):
    kind: str
    filename: str


def _edition_tz():
    """The edition clock. Falls back to UTC, loudly, where no IANA database is installed."""
    name = os.getenv("THESIS_EDITION_TZ", "Europe/London")
    try:
        return ZoneInfo(name)
    except Exception:
        print(f"[Editions] timezone {name!r} unavailable (no tzdata); editions run on UTC")
        return timezone.utc


EDITION_TZ = _edition_tz()
EDITION_SCHEDULE = os.getenv("THESIS_EDITION_SCHEDULE", "ny-premarket=12:00,ny-midday=17:30,session-handoff=23:30")
EDITIONS_ENABLED = os.getenv("THESIS_EDITIONS_ENABLED", "true").strip().lower() == "true"

_job: dict[str, Any] = {"running": False, "stage": "", "edition": None, "reason": "", "trigger": None,
                        "started_at": None, "finished_at": None, "last_error": None, "last_id": None}


def parse_schedule(raw: str) -> list[tuple[str, int, int]]:
    out = []
    for entry in (p.strip() for p in raw.split(",") if p.strip()):
        name, _, hhmm = entry.partition("=")
        hh, _, mm = hhmm.partition(":")
        if name in EDITIONS and hh.isdigit() and mm.isdigit():
            out.append((name, int(hh), int(mm)))
    return out


async def tracked_symbols(market_data_url: str) -> list[str]:
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.get(f"{market_data_url}/snapshots", timeout=15.0)
            r.raise_for_status()
            return [s["symbol"] for s in r.json().get("snapshots", []) if s.get("venue") == "hyperliquid"]
    except (httpx.HTTPError, ValueError, KeyError):
        return []


async def hermes_briefing(outlook: dict[str, Any]) -> dict[str, Any]:
    """An advisory briefing drafted by Hermes from the measured outlook, filed in quarantine."""
    if not agent_connector.configured():
        return {"status": "not_configured"}
    facts = {
        "breadth": outlook["breadth"]["summary"],
        "lead_reads": outlook["leads"],
        "events": [{"title": e["title"], "when_minutes": e["minutes_until"], "impact": e["impact"], "measured": e["guidance"]}
                   for e in outlook["key_events"]],
        "notes": outlook["notes"],
    }
    prompt = (
        "Write a private trader briefing from the measured facts below. Plain prose, at most 220 words, four short "
        "paragraphs: the overall read of the market; what to watch this week and how each scheduled event has moved the "
        "market before; how to handle risk around those events; and what would change the read. Use only these facts. "
        "Do not invent prices, events or probabilities. Do not output JSON.\n\nFACTS:\n" + json.dumps(facts, default=str)[:12000]
    )
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=BRIEFING_TIMEOUT_S, trust_env=False) as client:
            r = await client.post(f"{SELF_URL}/state/agents/harness/ask", json={"intent": "summarise", "prompt": prompt},
                                  headers=operator_headers())
    except httpx.HTTPError as exc:
        return {"status": "unavailable", "detail": type(exc).__name__}
    if r.status_code == 422:
        return {"status": "refused", "detail": str(r.json().get("detail", ""))[:300]}
    if r.status_code != 200:
        return {"status": "unavailable", "detail": f"HTTP {r.status_code}"}
    body = r.json()
    return {"status": "ok", "content": body.get("content", ""), "model": body.get("model"),
            "elapsed_ms": int((time.monotonic() - started) * 1000), "receipt": body.get("receipt"),
            "authority": "advisory_only", "source": "Hermes gateway via the harness boundary"}


async def build_edition(pool, market_data_url: str, calendar, evidence: Evidence, edition: str, trigger: str, reason: str = "") -> dict[str, Any]:
    stage = lambda s: _job.update(stage=s)  # noqa: E731
    symbols = await tracked_symbols(market_data_url)
    if not symbols:
        raise RuntimeError("no tracked symbols from market-data")
    now = datetime.now(timezone.utc)
    theses: dict[str, dict[str, Any]] = {}
    for i, symbol in enumerate(symbols, 1):
        stage(f"assembling {symbol} ({i}/{len(symbols)})")
        inputs = await gather_inputs(pool, symbol, market_data_url, calendar, evidence)
        theses[symbol] = build_thesis(
            symbol=symbol, now_ms=int(time.time() * 1000), regime=inputs["regime"], signal=inputs["signal"],
            source_status=inputs["source_status"], observation_age_ms=inputs["observation_age_ms"],
            candles=inputs["candles"], bucket_s=CANDLE_BUCKET_S, contributors=inputs["contributors"],
            cards=inputs["cards"], gate=inputs["gate"], events=inputs["events"],
            execution_enabled=execution_enabled(), feature_results=inputs["feature_results"], sources=inputs["sources"],
        )
    stage("measuring event reactions")
    events = events_from_context(await calendar())
    profiles, window = await ensure_profiles(market_data_url)
    stage("reading recent coverage")
    articles = await articles_for(events)
    outlook = compose_outlook(theses, events, profiles, articles, now, window)
    composed = compose(edition, now, theses, symbols)
    text_lines = composed["text"].split("\n")
    text = "\n".join(text_lines[:4] + outlook_text(outlook) + text_lines[4:])
    spoken = composed["narration"].split("\n")
    narration = "\n".join(spoken[:2] + outlook_narration(outlook) + spoken[2:])
    headline = f"{outlook['breadth']['lean'].upper()} · " + composed["headline"]
    stage("Hermes drafting the briefing")
    briefing = await hermes_briefing(outlook)
    stage("saving")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO thesis_editions (edition, generated_at, symbols, theses, headline, text, narration, verdicts, trigger,
                                         outlook, briefing, reason)
            VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6, $7, $8::jsonb, $9, $10::jsonb, $11::jsonb, $12) RETURNING id
            """,
            edition, now, json.dumps(composed["symbols"]), json.dumps(theses), headline, text, narration,
            json.dumps(composed["verdicts"]), trigger, json.dumps(outlook, default=str), json.dumps(briefing, default=str), reason,
        )
    return {"id": str(row["id"]), "edition": edition, "headline": headline}


def _j(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _row_to_edition(r, with_theses: bool) -> dict[str, Any]:
    out = {
        "id": str(r["id"]), "edition": r["edition"], "generated_at": r["generated_at"].isoformat(),
        "symbols": _j(r["symbols"]), "headline": r["headline"], "text": r["text"], "narration": r["narration"],
        "verdicts": _j(r["verdicts"]), "media": _j(r["media"]), "trigger": r["trigger"], "schema_version": r["schema_version"],
        "outlook": _j(r["outlook"]), "briefing": _j(r["briefing"]), "reason": r["reason"],
    }
    if with_theses:
        out["theses"] = _j(r["theses"])
    return out


def next_fire(now: datetime, schedule: list[tuple[str, int, int]]) -> tuple[str, datetime]:
    local = now.astimezone(EDITION_TZ)
    candidates = []
    for name, hh, mm in schedule:
        at = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if at <= local:
            at += timedelta(days=1)
        candidates.append((at, name))
    at, name = min(candidates)
    return name, at.astimezone(timezone.utc)


def register(app, state, *, market_data_url: str, calendar: Callable[[], Awaitable[dict[str, Any]]], evidence: Evidence = _no_evidence) -> None:
    async def run_job(edition: str, trigger: str, reason: str) -> None:
        _job.update(running=True, stage="starting", edition=edition, reason=reason, trigger=trigger,
                    started_at=datetime.now(timezone.utc).isoformat(), finished_at=None, last_error=None)
        try:
            result = await build_edition(state.pool, market_data_url, calendar, evidence, edition, trigger, reason)
            _job["last_id"] = result["id"]
        except Exception as exc:  # reported on the list endpoint; the next run still fires
            _job["last_error"] = f"{type(exc).__name__}: {exc}"[:300]
            print(f"[Editions] {edition} failed: {_job['last_error']}")
        finally:
            _job.update(running=False, stage="", finished_at=datetime.now(timezone.utc).isoformat())

    @router.get("/state/thesis/editions")
    async def list_editions(limit: int = Query(10, ge=1, le=50)):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        async with state.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM thesis_editions ORDER BY generated_at DESC LIMIT $1", limit)
        schedule = parse_schedule(EDITION_SCHEDULE)
        name, at = next_fire(datetime.now(timezone.utc), schedule) if schedule else (None, None)
        return {"schema_version": "thesis_editions_v2", "editions": [_row_to_edition(r, False) for r in rows],
                "generation": dict(_job),
                "schedule": {"timezone": str(EDITION_TZ), "entries": EDITION_SCHEDULE, "enabled": EDITIONS_ENABLED,
                             "next": {"edition": name, "at": at.isoformat() if at else None}}}

    @router.get("/state/thesis/editions/{edition_id}")
    async def get_edition(edition_id: str):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        async with state.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM thesis_editions WHERE id = $1::uuid", edition_id)
        if not row:
            raise HTTPException(status_code=404, detail="no such edition")
        return _row_to_edition(row, True)

    @router.post("/state/thesis/editions/{edition_id}/media")
    async def attach_media(edition_id: str, body: MediaAttach):
        """The host renderer names the file it produced; only a bare filename is recorded."""
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        if body.kind not in ("audio", "video", "subtitles", "slides") or "/" in body.filename or "\\" in body.filename or ".." in body.filename:
            raise HTTPException(status_code=400, detail="kind must be audio|video|subtitles|slides and filename a bare name")
        async with state.pool.acquire() as conn:
            n = await conn.execute("UPDATE thesis_editions SET media = media || $2::jsonb WHERE id = $1::uuid",
                                   edition_id, json.dumps({body.kind: body.filename}))
        if not n.endswith("1"):
            raise HTTPException(status_code=404, detail="no such edition")
        return {"id": edition_id, "attached": {body.kind: body.filename}}

    @router.get("/state/thesis/editions/{edition_id}/media/{filename}")
    async def serve_media(edition_id: str, filename: str):
        if "/" in filename or "\\" in filename or ".." in filename or ".." in edition_id or "/" in edition_id:
            raise HTTPException(status_code=400, detail="bare names only")
        path = EDITIONS_DIR / edition_id / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="no such media file")
        media_type = {".mp3": "audio/mpeg", ".mp4": "video/mp4", ".srt": "text/plain", ".png": "image/png"}.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(str(path), media_type=media_type, filename=filename)

    @router.post("/state/thesis/editions/generate")
    async def generate(edition: str = Query("manual"), reason: str = Query("", max_length=200)):
        """Start a regeneration in the background; the list endpoint reports its stage."""
        if edition not in EDITIONS:
            raise HTTPException(status_code=400, detail=f"edition must be one of {', '.join(EDITIONS)}")
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        if _job["running"]:
            return {"status": "already_running", "generation": dict(_job)}
        asyncio.create_task(run_job(edition, "operator", reason.strip()))
        await asyncio.sleep(0)
        return {"status": "started", "generation": dict(_job)}

    async def scheduler():
        schedule = parse_schedule(EDITION_SCHEDULE)
        if not EDITIONS_ENABLED or not schedule:
            return
        while True:
            name, at = next_fire(datetime.now(timezone.utc), schedule)
            await asyncio.sleep(max(1.0, (at - datetime.now(timezone.utc)).total_seconds()))
            if state.pool and not _job["running"]:
                await run_job(name, "schedule", "")
            await asyncio.sleep(61)

    background.add("thesis_editions", scheduler)

    app.include_router(router)
